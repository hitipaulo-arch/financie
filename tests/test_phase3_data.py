"""Testes de regressão da Fase 3 — integridade de dados e migrações.

Cobre o que mudou de comportamento:
  - dinheiro em NUMERIC em vez de FLOAT (e quantidade em NUMERIC(20,8))
  - validação de entrada no schema, igual no POST e no PUT
  - resumo com parcelas limitadas no tempo
  - agregações feitas no banco
  - deduplicação do sync respeitando soft delete
  - banco mal configurado falha alto (sem fallback para :memory:)
  - cadeia de migrações Alembic funcional e portátil

Para rodar:
    pytest tests/test_phase3_data.py -v
"""
from __future__ import annotations

import calendar
import os
import re
import sqlite3
from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.test_phase1_security import build_app, csrf_headers, login

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALEMBIC_DIR = os.path.join(ROOT, "alembic")
VERSIONS = os.path.join(ALEMBIC_DIR, "versions")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def env_app(tmp_path):
    """App em modo desenvolvimento com banco próprio por teste."""
    backend, app = build_app({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'fase3.db'}",
        "APP_ENV": "development",
        "ENABLE_DEV_LOGIN": "true",
    })
    app.config["TESTING"] = True
    return backend, app


@pytest.fixture
def client(env_app):
    backend, app = env_app
    c = app.test_client()
    c.post("/auth/dev-login", json={"user_id": "u1"})
    return c


@pytest.fixture
def auth(client):
    """Headers CSRF prontos para escrita."""
    return csrf_headers(client)


def meses_atras(n: int) -> date:
    """Data de n meses atrás, sem depender de dateutil."""
    hoje = date.today()
    ano, mes = hoje.year, hoje.month - n
    while mes <= 0:
        mes += 12
        ano -= 1
    dia = min(hoje.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def strings_de_codigo(caminho: str) -> list:
    """String literals de um arquivo .py, EXCLUINDO docstrings.

    As docstrings desta fase citam de propósito o código errado que foi removido
    (ex.: o fallback para banco em memória e a consulta a `sqlite_master`) para
    explicar por que a mudança foi feita. O que estes testes precisam garantir é
    que nenhum *código executável* volte a conter aquilo — varrer o arquivo cru
    confundiria explicação com implementação.
    """
    import ast

    arvore = ast.parse(open(caminho, encoding="utf-8").read())
    docstrings = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            corpo = getattr(no, "body", [])
            if (corpo and isinstance(corpo[0], ast.Expr)
                    and isinstance(corpo[0].value, ast.Constant)
                    and isinstance(corpo[0].value.value, str)):
                docstrings.add(id(corpo[0].value))
    return [
        no.value for no in ast.walk(arvore)
        if isinstance(no, ast.Constant) and isinstance(no.value, str)
        and id(no) not in docstrings
    ]


def alembic_cfg() -> Config:
    cfg = Config(os.path.join(ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", ALEMBIC_DIR)
    return cfg


def criar_transacao_direto(backend, app, user_id, amount, tipo="expense", quando=None):
    """Insere pelo ORM, sem passar por HTTP (evita o rate limit em testes de volume)."""
    with app.app_context():
        sess = backend.get_session_local()()
        txn = backend.Transaction(
            user_id=user_id, description="item", amount=amount,
            type=tipo, date=quando or date.today(),
        )
        sess.add(txn)
        sess.commit()
        return txn.id


# ---------------------------------------------------------------------------
# Dinheiro: NUMERIC em vez de FLOAT
# ---------------------------------------------------------------------------
def test_colunas_monetarias_sao_numeric(env_app):
    """FLOAT é binário: 0.1 não tem representação exata e somar centavos deriva."""
    backend, _ = env_app
    esperados = [
        (backend.Transaction, "amount", (14, 2)),
        (backend.Installment, "monthly_value", (14, 2)),
    ]
    for modelo, coluna, (precisao, escala) in esperados:
        tipo = modelo.__table__.c[coluna].type
        assert isinstance(tipo, sa.Numeric), f"{coluna} deveria ser Numeric, é {type(tipo).__name__}"
        assert not isinstance(tipo, sa.Float), f"{coluna} ainda é Float"
        assert (tipo.precision, tipo.scale) == (precisao, escala)


def test_quantidade_de_ativo_tem_8_casas(env_app):
    """Quantidade/cotação NÃO pode usar 2 casas: 0.00012345 BTC viraria zero.

    Este teste existe porque a primeira versão desta fase aplicou NUMERIC(14,2)
    em investments.amount por engano — o que zeraria qualquer posição fracionada
    de cripto sem nenhum erro.
    """
    backend, _ = env_app
    for coluna in ("amount", "purchase_price", "current_price"):
        tipo = backend.Investment.__table__.c[coluna].type
        assert isinstance(tipo, sa.Numeric), coluna
        assert tipo.scale == 8, f"{coluna} precisa de 8 casas, tem {tipo.scale}"


def test_soma_no_banco_volta_decimal_exata(env_app):
    """O SUM de centavos volta como Decimal exato, não como float derivado."""
    backend, app = env_app
    for _ in range(30):
        criar_transacao_direto(backend, app, "u1", Decimal("0.07"))

    with app.app_context():
        sess = backend.get_session_local()()
        soma = sess.query(sa.func.sum(backend.Transaction.amount)).scalar()

    assert isinstance(soma, Decimal), f"SUM voltou {type(soma).__name__}, esperado Decimal"
    assert soma == Decimal("2.10"), f"30 x 0.07 deveria ser 2.10 exato, veio {soma}"


def test_funcao_money_normaliza_decimal_e_float(env_app):
    """jsonify não serializa Decimal: sem money() o endpoint daria 500 só no PostgreSQL."""
    backend, _ = env_app
    assert backend.money(Decimal("123.456")) == 123.46
    assert backend.money(Decimal("0.1")) == 0.1
    assert backend.money(0.1 + 0.2) == 0.3
    assert backend.money(None) == 0.0
    assert backend.money("nao-e-numero") == 0.0
    assert isinstance(backend.money(Decimal("1.5")), float)


def test_fracao_de_cripto_sobrevive_ao_crud(client, auth):
    """Ponta a ponta: cadastrar 0.00012345 BTC e ler de volta sem perder a fração."""
    criada = client.post("/api/users/u1/investments", json={
        "name": "Bitcoin", "asset_type": "crypto", "amount": 0.00012345,
        "purchase_price": 60000.0, "current_price": 65000.0,
        "purchase_date": "2026-01-10", "status": "active",
    }, headers=auth)
    assert criada.status_code == 201, criada.get_data(as_text=True)
    assert criada.get_json()["amount"] == pytest.approx(0.00012345)

    lida = client.get("/api/users/u1/investments").get_json()["items"][0]
    assert lida["amount"] == pytest.approx(0.00012345), (
        "a quantidade fracionada foi arredondada — dinheiro/quantidade usam escalas diferentes"
    )


# ---------------------------------------------------------------------------
# Validação de entrada
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("amount", [0, -1, -9999, 0.001])
def test_valor_nao_positivo_e_rejeitado_no_post(client, auth, amount):
    """Antes o POST aceitava amount <= 0 e o resumo do usuário virava ficção."""
    resp = client.post("/api/users/u1/transactions", json={
        "description": "teste", "amount": amount, "type": "expense",
    }, headers=auth)
    assert resp.status_code == 400, f"amount={amount} deveria ser rejeitado"
    assert "amount" in resp.get_json()["details"]


@pytest.mark.parametrize("amount", [0, -50])
def test_post_e_put_validam_amount_igualmente(client, auth, amount):
    """A divergência era o bug: PUT rejeitava amount<=0, POST aceitava."""
    criada = client.post("/api/users/u1/transactions", json={
        "description": "original", "amount": 100, "type": "expense",
    }, headers=auth)
    txn_id = criada.get_json()["id"]

    resp = client.put(f"/api/users/u1/transactions/{txn_id}",
                      json={"amount": amount}, headers=auth)
    assert resp.status_code == 400

    # e o valor original permanece intacto
    assert client.get("/api/users/u1/transactions").get_json()["items"][0]["amount"] == 100


def test_descricao_acima_do_limite_da_coluna_e_rejeitada(client, auth):
    """String(255): o SQLite aceitava 5.000 caracteres, o PostgreSQL daria 500."""
    longo = "x" * 256
    resp = client.post("/api/users/u1/transactions", json={
        "description": longo, "amount": 10, "type": "expense",
    }, headers=auth)
    assert resp.status_code == 400
    assert "description" in resp.get_json()["details"]

    no_limite = "y" * 255
    ok = client.post("/api/users/u1/transactions", json={
        "description": no_limite, "amount": 10, "type": "expense",
    }, headers=auth)
    assert ok.status_code == 201, ok.get_data(as_text=True)


@pytest.mark.parametrize("campo,tamanho", [("name", 257), ("notes", 1025)])
def test_limites_dos_campos_de_investimento(client, auth, campo, tamanho):
    payload = {
        "name": "ok", "asset_type": "stocks", "amount": 1, "purchase_price": 10,
        "purchase_date": "2026-01-10", "status": "active",
    }
    payload[campo] = "z" * tamanho
    assert client.post("/api/users/u1/investments", json=payload,
                       headers=auth).status_code == 400


@pytest.mark.parametrize("total_months", [0, -3])
def test_total_months_precisa_ser_positivo(client, auth, total_months):
    resp = client.post("/api/users/u1/installments", json={
        "description": "tv", "monthly_value": 100, "total_months": total_months,
    }, headers=auth)
    assert resp.status_code == 400
    assert "total_months" in resp.get_json()["details"]


def test_monthly_value_nao_positivo_e_rejeitado(client, auth):
    resp = client.post("/api/users/u1/installments", json={
        "description": "tv", "monthly_value": 0, "total_months": 10,
    }, headers=auth)
    assert resp.status_code == 400


def test_put_rejeita_campo_desconhecido(client, auth):
    """Antes campo desconhecido era ignorado em silêncio — erro de digitação
    parecia funcionar."""
    criada = client.post("/api/users/u1/transactions", json={
        "description": "x", "amount": 10, "type": "expense",
    }, headers=auth)
    txn_id = criada.get_json()["id"]

    resp = client.put(f"/api/users/u1/transactions/{txn_id}",
                      json={"ammount": 20}, headers=auth)  # typo
    assert resp.status_code == 400


def test_put_aplica_os_campos_que_o_frontend_envia(client, auth):
    """Regressão: a tela de edição de investimento mandava asset_type, amount,
    purchase_price e purchase_date; o PUT descartava os quatro e respondia 200."""
    criada = client.post("/api/users/u1/investments", json={
        "name": "Tesla", "asset_type": "stocks", "amount": 10,
        "purchase_price": 200, "purchase_date": "2026-01-10", "status": "active",
    }, headers=auth)
    inv_id = criada.get_json()["id"]

    resp = client.put(f"/api/users/u1/investments/{inv_id}", json={
        "name": "Tesla Inc", "asset_type": "reit", "amount": 25,
        "purchase_price": 180.5, "purchase_date": "2026-02-20",
        "status": "active", "current_price": 190, "target_return": 12,
        "notes": "revisado",
    }, headers=auth)
    assert resp.status_code == 200, resp.get_data(as_text=True)

    corpo = resp.get_json()
    assert corpo["name"] == "Tesla Inc"
    assert corpo["asset_type"] == "reit", "asset_type foi descartado em silêncio"
    assert corpo["amount"] == 25, "amount foi descartado em silêncio"
    assert corpo["purchase_price"] == 180.5, "purchase_price foi descartado"
    assert corpo["purchase_date"] == "2026-02-20", "purchase_date foi descartado"
    assert corpo["notes"] == "revisado"


def test_put_nao_permite_transferir_o_registro_para_outro_usuario(client, auth):
    """`user_id` existe no schema (o POST precisa dele), então sem a whitelist do
    apply_update um PUT poderia mover o registro para outra conta."""
    criada = client.post("/api/users/u1/transactions", json={
        "description": "meu", "amount": 10, "type": "expense",
    }, headers=auth)
    txn_id = criada.get_json()["id"]

    resp = client.put(f"/api/users/u1/transactions/{txn_id}",
                      json={"user_id": "invasor", "description": "alterado"},
                      headers=auth)
    assert resp.status_code == 200
    assert resp.get_json()["user_id"] == "u1", "o dono do registro foi alterado"

    # e o outro usuário não enxerga a transação
    login(client, "invasor")
    itens = client.get("/api/users/invasor/transactions").get_json()["items"]
    assert itens == []


# ---------------------------------------------------------------------------
# Resumo: parcelas limitadas no tempo
# ---------------------------------------------------------------------------
def test_parcela_encerrada_nao_pesa_no_resumo(client, auth):
    """O bug: o resumo somava TODAS as parcelas cadastradas, para sempre. Uma
    compra em 12x feita há três anos continuava contando como despesa do mês."""
    antiga = meses_atras(13)
    client.post("/api/users/u1/installments", json={
        "description": "tv já quitada", "monthly_value": 500,
        "total_months": 12, "date_added": antiga.isoformat(),
    }, headers=auth)

    resumo = client.get("/api/users/u1/summary").get_json()
    assert resumo["expenses_parcelas"] == 0, "parcela encerrada ainda era somada"
    assert resumo["parcelas_encerradas"] == 1
    assert resumo["parcelas_ativas"] == 0


def test_parcela_em_andamento_pesa_no_resumo(client, auth):
    client.post("/api/users/u1/installments", json={
        "description": "notebook", "monthly_value": 350.5,
        "total_months": 12, "date_added": meses_atras(2).isoformat(),
    }, headers=auth)

    resumo = client.get("/api/users/u1/summary").get_json()
    assert resumo["expenses_parcelas"] == pytest.approx(350.5)
    assert resumo["parcelas_ativas"] == 1
    assert resumo["expenses_total"] == pytest.approx(350.5)


def test_limite_exato_do_prazo_da_parcela(client, auth):
    """12 meses corridos em 12 parcelas: a última já venceu, não conta mais."""
    client.post("/api/users/u1/installments", json={
        "description": "limite", "monthly_value": 100,
        "total_months": 12, "date_added": meses_atras(12).isoformat(),
    }, headers=auth)
    assert client.get("/api/users/u1/summary").get_json()["parcelas_ativas"] == 0

    client.post("/api/users/u1/installments", json={
        "description": "ainda dentro", "monthly_value": 100,
        "total_months": 12, "date_added": meses_atras(11).isoformat(),
    }, headers=auth)
    assert client.get("/api/users/u1/summary").get_json()["parcelas_ativas"] == 1


@pytest.mark.parametrize("n_meses,total,esperado", [
    (0, 12, True),    # começou este mês
    (11, 12, True),   # última parcela
    (12, 12, False),  # acabou
    (13, 12, False),  # antiga
    (0, 1, True),     # parcela única, no mês
    (1, 1, False),    # parcela única, já foi
])
def test_parcela_ativa_pela_aritmetica_de_meses(env_app, n_meses, total, esperado):
    backend, _ = env_app
    assert backend.parcela_ativa(meses_atras(n_meses), total, date.today()) is esperado


@pytest.mark.parametrize("inicio,total", [(None, 12), (date.today(), None), (date.today(), 0)])
def test_parcela_ativa_e_defensiva_contra_linhas_invalidas(env_app, inicio, total):
    """Linhas gravadas antes da validação existir não podem derrubar o resumo."""
    backend, _ = env_app
    assert backend.parcela_ativa(inicio, total, date.today()) is False


def test_meses_decorridos_ignora_o_dia_do_mes(env_app):
    """A diferença é em meses cheios: dia 1 e dia 28 do mesmo mês são 0 meses."""
    backend, _ = env_app
    assert backend.meses_decorridos(date(2026, 1, 1), date(2026, 1, 28)) == 0
    assert backend.meses_decorridos(date(2026, 1, 28), date(2026, 2, 1)) == 1
    assert backend.meses_decorridos(date(2025, 12, 15), date(2026, 1, 10)) == 1
    assert backend.meses_decorridos(date(2026, 1, 10), date(2025, 12, 15)) == -1


def test_resumo_continua_com_os_campos_de_sempre(client, auth):
    """As contagens novas são aditivas; nenhum campo existente sumiu."""
    client.post("/api/users/u1/transactions", json={
        "description": "salário", "amount": 1000, "type": "income",
    }, headers=auth)
    corpo = client.get("/api/users/u1/summary").get_json()
    for campo in ("income", "expenses_avulsa", "expenses_parcelas",
                  "expenses_total", "balance"):
        assert campo in corpo, f"campo {campo} sumiu do resumo"
    assert corpo["income"] == 1000


# ---------------------------------------------------------------------------
# Deduplicação do sync
# ---------------------------------------------------------------------------
def _sincronizar(client, auth):
    client.post("/api/users/u1/openfinance/consents", json={}, headers=auth)
    return client.post("/api/users/u1/openfinance/sync", headers=auth)


def test_segundo_sync_nao_duplica(client, auth):
    assert _sincronizar(client, auth).get_json()["imported"] == 3
    segunda = _sincronizar(client, auth).get_json()
    assert segunda["imported"] == 0
    assert segunda["skipped_duplicates"] == 3


def test_transacao_apagada_nao_ressuscita_no_sync(client, auth):
    """Regressão: o filtro de dedupe ignorava linhas com soft delete, então apagar
    uma transação importada a trazia de volta na sincronização seguinte."""
    primeira = _sincronizar(client, auth).get_json()
    ids = [t["id"] for t in primeira["transactions"]]

    assert client.delete(f"/api/users/u1/transactions/{ids[0]}",
                         headers=auth).status_code == 200
    assert client.get("/api/users/u1/summary").get_json() is not None

    segunda = _sincronizar(client, auth).get_json()
    assert segunda["imported"] == 0, "a transação apagada voltou no sync seguinte"
    assert segunda["skipped_duplicates"] == 3

    total = client.get("/api/users/u1/transactions").get_json()["pagination"]["total"]
    assert total == 2, "a transação apagada reapareceu na listagem"


def test_sync_reporta_itens_invalidos(client, auth):
    """Campo novo na resposta: um item malformado do banco não aborta mais o sync."""
    corpo = _sincronizar(client, auth).get_json()
    assert "skipped_invalid" in corpo
    assert corpo["skipped_invalid"] == 0


# ---------------------------------------------------------------------------
# Banco mal configurado falha alto
# ---------------------------------------------------------------------------
def test_nao_ha_fallback_para_banco_em_memoria():
    """O fallback silencioso fazia o app subir 'verde' perdendo todos os dados.

    Cada conexão nova era um banco vazio: o usuário criava transações e elas
    sumiam no request seguinte, sem nenhum erro no log.
    """
    literais = strings_de_codigo(os.path.join(ROOT, "backend.py"))
    culpados = [s for s in literais if ":memory:" in s]
    assert not culpados, f"o fallback para banco em memória voltou: {culpados}"


def test_falha_de_banco_derruba_o_boot_e_nao_e_engolida():
    """Regressão do `except` que dizia "App will still start, just without
    database": o health check passava, o Azure trocava o slot e todo request
    devolvia 500 — falha total anunciada como deploy bem-sucedido.
    """
    fonte = open(os.path.join(ROOT, "backend.py"), encoding="utf-8").read()
    trecho = fonte.split("Base.metadata.create_all(db_engine)", 1)[1][:600]
    assert "raise RuntimeError" in trecho, (
        "a falha do create_all voltou a ser engolida no boot"
    )
    assert "App will still start" not in fonte


def test_url_de_banco_invalida_derruba_o_boot(tmp_path):
    with pytest.raises(RuntimeError) as exc:
        build_app({"GF_DB_URL": "dialeto-inexistente://localhost/x"})
    assert "banco de dados" in str(exc.value).lower()


def test_mensagem_de_falha_do_banco_nao_vaza_a_connection_string(tmp_path):
    """A connection string carrega a senha do banco; não pode ir para o log/erro."""
    url_com_senha = "dialeto-inexistente://user:senha-super-secreta@host/db"
    with pytest.raises(RuntimeError) as exc:
        build_app({"GF_DB_URL": url_com_senha})
    assert "senha-super-secreta" not in str(exc.value)


def test_engine_e_criado_sob_demanda(env_app):
    """Importar o módulo não pode abrir conexão (o Alembic importa Base)."""
    backend, _ = env_app
    assert callable(backend.get_engine)
    assert callable(backend.resolve_db_url)


def test_resolve_db_url_prefere_database_url(monkeypatch):
    import backend
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://a:b@h/db")
    monkeypatch.setenv("GF_DB_URL", "sqlite:///local.db")
    assert backend.resolve_db_url() == "postgresql+psycopg2://a:b@h/db"

    monkeypatch.delenv("DATABASE_URL")
    assert backend.resolve_db_url() == "sqlite:///local.db"

    monkeypatch.delenv("GF_DB_URL")
    assert backend.resolve_db_url() == "sqlite:///data.db"


# ---------------------------------------------------------------------------
# Migrações Alembic
# ---------------------------------------------------------------------------
def test_cadeia_tem_um_unico_head_e_tres_revisoes():
    script = ScriptDirectory.from_config(alembic_cfg())
    assert len(script.get_heads()) == 1, "cadeia ramificada: falta um merge"
    revisoes = list(script.walk_revisions("base", "heads"))
    assert len(revisoes) == 3, [r.revision for r in revisoes]


def test_revisao_inicial_cria_as_tabelas_de_verdade():
    """A revisão inicial tinha `upgrade(): pass` — marcava o Alembic como
    aplicado sem criar nada, e a seguinte morria com 'no such table'."""
    fonte = open(os.path.join(
        VERSIONS, "46d24e28829d_initial_schema_with_indexes_and_soft_.py"),
        encoding="utf-8").read()
    corpo = fonte.split("def upgrade()", 1)[1]
    assert "op.create_table" in corpo
    for tabela in ("transactions", "installments", "consents", "investments"):
        assert f'"{tabela}"' in corpo, f"revisão inicial não cria {tabela}"


def test_migracoes_nao_usam_catalogo_de_um_dialeto_so():
    """`sqlite_master` só existe no SQLite; no PostgreSQL a migração estourava.

    O banco de produção ainda não está decidido, então as migrações precisam
    valer nos dois dialetos — inspeção via `sa.inspect()`, nunca catálogo cru.
    """
    proibidos = ("sqlite_master", "pg_indexes", "pg_catalog", "information_schema")
    for nome in sorted(os.listdir(VERSIONS)):
        if not nome.endswith(".py"):
            continue
        literais = strings_de_codigo(os.path.join(VERSIONS, nome))
        for catalogo in proibidos:
            culpados = [s for s in literais if catalogo in s]
            assert not culpados, f"{nome} usa catálogo {catalogo} em código: {culpados}"


def test_upgrade_head_cria_esquema_com_numeric(tmp_path, monkeypatch):
    db = tmp_path / "mig.db"
    monkeypatch.setenv("GF_DB_URL", f"sqlite:///{db}")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    command.upgrade(alembic_cfg(), "head")

    assert db.exists(), "a migração não criou o banco"
    conn = sqlite3.connect(db)
    tabelas = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()

    assert {"transactions", "installments", "consents", "investments"} <= tabelas

    engine = sa.create_engine(f"sqlite:///{db}")
    inspetor = sa.inspect(engine)
    tipos = {c["name"]: c["type"] for c in inspetor.get_columns("transactions")}
    assert isinstance(tipos["amount"], sa.Numeric)
    assert not isinstance(tipos["amount"], sa.Float)

    inv = {c["name"]: c["type"] for c in inspetor.get_columns("investments")}
    assert inv["amount"].scale == 8, "quantidade de ativo precisa de 8 casas"
    engine.dispose()


def test_upgrade_head_preserva_dados_e_e_idempotente(tmp_path, monkeypatch):
    """Banco antigo (FLOAT, criado pelo create_all) precisa migrar sem perder nada,
    e rodar de novo não pode falhar — o startup.txt roda em todo boot."""
    db = tmp_path / "legado.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
    CREATE TABLE transactions (id INTEGER NOT NULL PRIMARY KEY,
      user_id VARCHAR(64) NOT NULL, description VARCHAR(255) NOT NULL,
      amount FLOAT NOT NULL, type VARCHAR(16) NOT NULL, date DATE NOT NULL,
      deleted_at DATETIME);
    CREATE TABLE installments (id INTEGER NOT NULL PRIMARY KEY,
      user_id VARCHAR(64) NOT NULL, description VARCHAR(255) NOT NULL,
      monthly_value FLOAT NOT NULL, total_months INTEGER NOT NULL,
      date_added DATE NOT NULL, deleted_at DATETIME);
    CREATE TABLE consents (id INTEGER NOT NULL PRIMARY KEY,
      user_id VARCHAR(64) NOT NULL, consent_id VARCHAR(128) NOT NULL UNIQUE,
      provider VARCHAR(64) NOT NULL, scopes VARCHAR(512) NOT NULL,
      status VARCHAR(32) NOT NULL, created_at DATETIME NOT NULL,
      deleted_at DATETIME);
    CREATE TABLE investments (id INTEGER NOT NULL PRIMARY KEY,
      user_id VARCHAR(64) NOT NULL, name VARCHAR(256) NOT NULL,
      asset_type VARCHAR(64) NOT NULL, amount FLOAT NOT NULL,
      purchase_price FLOAT NOT NULL, current_price FLOAT,
      purchase_date DATE NOT NULL, target_return FLOAT, status VARCHAR(32) NOT NULL,
      notes VARCHAR(1024), created_at DATETIME NOT NULL,
      updated_at DATETIME NOT NULL, deleted_at DATETIME);
    INSERT INTO transactions (user_id, description, amount, type, date)
      VALUES ('u1', 'café', 0.1, 'expense', '2026-01-06');
    INSERT INTO investments (user_id, name, asset_type, amount, purchase_price,
      purchase_date, status, created_at, updated_at)
      VALUES ('u1', 'BTC', 'crypto', 0.00012345, 60000.0, '2026-01-01', 'active',
      '2026-01-01', '2026-01-01');
    """)
    conn.commit()
    conn.close()

    monkeypatch.setenv("GF_DB_URL", f"sqlite:///{db}")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    command.upgrade(alembic_cfg(), "head")
    command.upgrade(alembic_cfg(), "head")  # segunda vez: não pode falhar

    conn = sqlite3.connect(db)
    assert conn.execute("SELECT description, amount FROM transactions").fetchall() == \
        [("café", 0.1)], "dados perdidos na migração"
    assert conn.execute("SELECT amount FROM investments").fetchall() == \
        [(0.00012345,)], "fração de cripto perdida na migração"
    indices = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'i%'")}
    conn.close()

    # os idx_* (revisão 2) e os ix_*_user_id (revisão 1) precisam existir mesmo
    # num banco que já tinha as tabelas — a guarda de índice é separada da de tabela
    assert "idx_investment_type" in indices
    assert "ix_investments_user_id" in indices
    assert len(indices) == 17, sorted(indices)


def test_downgrade_ate_a_base_funciona(tmp_path, monkeypatch):
    db = tmp_path / "down.db"
    monkeypatch.setenv("GF_DB_URL", f"sqlite:///{db}")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    command.upgrade(alembic_cfg(), "head")
    command.downgrade(alembic_cfg(), "base")

    conn = sqlite3.connect(db)
    restantes = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert restantes == {"alembic_version"}, restantes


def test_modo_offline_gera_sql_sem_precisar_de_banco(tmp_path, monkeypatch):
    """`alembic upgrade head --sql` não conecta; as guardas não podem quebrá-lo.

    Offline o Alembic entrega um MockConnection, e `sa.inspect()` lança
    NoInspectionAvailable — sem tratamento, gerar o SQL para um DBA revisar falhava.
    """
    monkeypatch.setenv("GF_DB_URL", f"sqlite:///{tmp_path / 'nao-existe.db'}")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    command.upgrade(alembic_cfg(), "head", sql=True)  # não deve lançar


def test_alembic_ini_nao_tem_url_fixa():
    """URL fixa no .ini fazia migrar o data.db local achando que era produção."""
    ini = open(os.path.join(ROOT, "alembic.ini"), encoding="utf-8").read()
    ativas = [l for l in ini.splitlines()
              if l.strip().startswith("sqlalchemy.url")]
    assert not ativas, f"alembic.ini ainda fixa a URL: {ativas}"


def test_env_py_le_a_url_do_ambiente():
    env = open(os.path.join(ALEMBIC_DIR, "env.py"), encoding="utf-8").read()
    assert "resolve_db_url" in env, "env.py precisa re-resolver a URL do ambiente"
    assert "render_as_batch" in env, "sem batch mode o SQLite não altera coluna"
    assert "compare_type" in env, "sem isto o autogenerate não vê Float -> Numeric"
