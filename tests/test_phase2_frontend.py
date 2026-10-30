"""Testes do frontend de referência em static/ e do contrato que ele implementa.

Antes da Fase 2 o repositório não tinha frontend algum, mas o README e o
redirect pós-login apontavam para `index_api.html` — que dava 404. Estes testes
travam:
  - os assets existem e são servidos por /static
  - o destino do redirect pós-login existe (regressão do 404)
  - o frontend usa URLs relativas e o fluxo CSRF correto
  - a sequência exata de chamadas que a UI faz continua funcionando
"""
from __future__ import annotations

import os
import re

import pytest

from tests.test_phase1_security import build_app, csrf_headers, login

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "static")

ASSETS = ["/static/index.html", "/static/app.js", "/static/styles.css"]


@pytest.fixture
def app_env(tmp_path):
    backend, app = build_app({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'frontend.db'}",
        "APP_ENV": "development",
        "ENABLE_DEV_LOGIN": "true",
    })
    app.config["TESTING"] = False
    return backend, app


def ler(nome):
    with open(os.path.join(STATIC, nome), encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Os arquivos existem e são servidos
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("caminho", ASSETS)
def test_assets_existem_no_disco(caminho):
    arquivo = os.path.join(STATIC, os.path.basename(caminho))
    assert os.path.isfile(arquivo), f"{caminho} não existe em static/"
    assert os.path.getsize(arquivo) > 0


@pytest.mark.parametrize("caminho,esperado", [
    ("/static/index.html", "text/html"),
    ("/static/app.js", "javascript"),
    ("/static/styles.css", "text/css"),
])
def test_assets_sao_servidos_com_mime_correto(app_env, caminho, esperado):
    _, app = app_env
    resp = app.test_client().get(caminho)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    assert esperado in resp.content_type


def test_index_referencia_os_outros_assets(app_env):
    _, app = app_env
    html = app.test_client().get("/static/index.html").get_data(as_text=True)
    assert '/static/styles.css' in html
    assert '/static/app.js' in html


# ---------------------------------------------------------------------------
# Regressão do redirect pós-login que dava 404
# ---------------------------------------------------------------------------
def test_destino_padrao_do_redirect_pos_login_existe(app_env):
    """POST_LOGIN_PATH padrão é /static/index.html — precisa existir, senão o
    usuário cai num 404 logo depois de logar com o Google."""
    backend, app = app_env
    assert backend.POST_LOGIN_PATH == "/static/index.html"

    resp = app.test_client().get(backend.POST_LOGIN_PATH)
    assert resp.status_code == 200, "o destino do redirect pós-login não existe"


def test_destino_configurado_do_redirect_existe(tmp_path):
    _, app = build_app({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'destino.db'}",
        "POST_LOGIN_PATH": "/static/index.html",
    })
    assert app.test_client().get("/static/index.html").status_code == 200


# ---------------------------------------------------------------------------
# Contrato do frontend
# ---------------------------------------------------------------------------
def test_frontend_nao_tem_host_hardcoded():
    """URLs relativas: o mesmo bundle precisa funcionar em localhost e no Azure."""
    for nome in ("index.html", "app.js"):
        conteudo = ler(nome)
        for proibido in ("http://localhost", "https://localhost", "127.0.0.1",
                         "azurewebsites.net"):
            assert proibido not in conteudo, f"{nome} contém host hardcoded: {proibido}"


def test_toda_chamada_fetch_do_frontend_e_relativa():
    js = ler("app.js")
    urls = re.findall(r"fetch\(\s*[`'\"]([^`'\"]+)[`'\"]", js)
    assert urls, "nenhum fetch encontrado — o padrão mudou?"
    for url in urls:
        assert url.startswith("/"), f"fetch com URL não-relativa: {url}"


def test_frontend_implimenta_o_fluxo_csrf_correto():
    js = ler("app.js")
    assert "/api/csrf-token" in js, "precisa buscar o token no endpoint correto"
    assert "X-CSRFToken" in js, "precisa enviar o header que o Flask-WTF lê"
    assert "'N/A'" in js or '"N/A"' in js, (
        "deve rejeitar o token 'N/A' que o endpoint devolvia antes da correção"
    )
    assert "credentials: 'include'" in js, "o cookie de sessão precisa viajar"


def test_frontend_nao_chama_rotas_inexistentes(app_env):
    """Cada caminho que a UI usa precisa existir no url_map do backend.

    Se alguém renomear uma rota sem atualizar o JS, este teste falha — é a
    proteção contra o frontend "quebrado de fábrica".
    """
    _, app = app_env
    js = ler("app.js")

    # Cada regra do Flask vira duas formas: uma regex para casar o caminho
    # inteiro e uma literal (placeholders -> "1") para aceitar prefixos, já que
    # o helper base() do JS monta só "/api/users/<id>" e concatena o resto.
    regex, literais = [], []
    for rule in app.url_map.iter_rules():
        texto = str(rule).rstrip("/")
        regex.append(re.compile("^" + re.sub(r"<[^>]*>", "[^/]+", texto) + "/?$"))
        literais.append(re.sub(r"<[^>]*>", "1", texto))

    citados = set(re.findall(r"[`'\"](/(?:api|auth)/[^`'\"]*)[`'\"]", js))
    assert citados, "nenhum caminho /api ou /auth encontrado no JS"

    for citado in sorted(citados):
        caminho = re.sub(r"\$\{[^}]*\}", "1", citado.split("?")[0]).rstrip("/") or "/"
        casa = any(r.match(caminho) for r in regex)
        prefixo = any(l.startswith(caminho + "/") for l in literais)
        assert casa or prefixo, (
            f"a UI chama uma rota que não existe no backend: {citado} ({caminho})"
        )


# ---------------------------------------------------------------------------
# Sequência real que a UI executa
# ---------------------------------------------------------------------------
def test_fluxo_completo_do_frontend(app_env):
    """Reproduz, na ordem, tudo o que o app.js faz de manhã até a noite."""
    _, app = app_env
    c = app.test_client()

    # 1) tela de login: sem sessão, /auth/me responde 401
    assert c.get("/auth/me").status_code == 401

    # 2) login (dev, neste ambiente) — como faz o botão "Entrar como dev"
    assert c.post("/auth/dev-login", json={"user_id": "dev"}).status_code == 200

    # 3) /auth/me popula o cabeçalho
    eu = c.get("/auth/me").get_json()
    assert eu["user_id"] == "dev"

    # 4) token CSRF antes de qualquer escrita
    token = c.get("/api/csrf-token").get_json()["csrf_token"]
    assert token and token != "N/A"
    h = {"X-CSRFToken": token}

    # 5) painel: summary, sugestões e portfólio
    resumo = c.get("/api/users/dev/summary")
    assert resumo.status_code == 200
    assert c.get("/api/users/dev/suggestions").status_code == 200
    assert c.get("/api/users/dev/investments/portfolio").status_code == 200

    # 6) aba transações: criar, editar, excluir
    criada = c.post("/api/users/dev/transactions", json={
        "description": "Salário", "amount": 7500, "type": "income", "date": "2026-10-01",
    }, headers=h)
    assert criada.status_code == 201, criada.get_data(as_text=True)
    txn_id = criada.get_json()["id"]

    assert c.put(f"/api/users/dev/transactions/{txn_id}",
                 json={"amount": 7800}, headers=h).status_code == 200

    lista = c.get("/api/users/dev/transactions?page=1&per_page=20").get_json()
    assert lista["pagination"]["total"] == 1

    # 7) aba parcelas
    parcela = c.post("/api/users/dev/installments", json={
        "description": "Notebook", "monthly_value": 350.5, "total_months": 12,
    }, headers=h)
    assert parcela.status_code == 201, parcela.get_data(as_text=True)
    inst_id = parcela.get_json()["id"]
    assert c.patch(f"/api/users/dev/installments/{inst_id}",
                   json={"total_months": 10}, headers=h).status_code == 200

    # 8) aba investimentos, com os filtros que a UI envia
    inv = c.post("/api/users/dev/investments", json={
        "name": "Tesla", "asset_type": "stocks", "amount": 10,
        "purchase_price": 200, "current_price": 265.4,
        "purchase_date": "2026-02-10", "status": "active",
    }, headers=h)
    assert inv.status_code == 201, inv.get_data(as_text=True)
    filtrados = c.get("/api/users/dev/investments?asset_type=stocks&status=active").get_json()
    assert filtrados["pagination"]["total"] == 1

    # 9) aba Open Finance: consentimento e sync
    assert c.post("/api/users/dev/openfinance/consents", json={}, headers=h).status_code == 201
    sync = c.post("/api/users/dev/openfinance/sync", headers=h)
    assert sync.status_code == 201, sync.get_data(as_text=True)
    assert sync.get_json()["imported"] == 3

    # 10) painel de novo, com os números atualizados
    final = c.get("/api/users/dev/summary").get_json()
    assert final["income"] == pytest.approx(7800 + 987.65)
    assert final["expenses_parcelas"] == pytest.approx(350.5)

    # 11) exclusão (soft delete) some da listagem
    assert c.delete(f"/api/users/dev/transactions/{txn_id}", headers=h).status_code == 200
    ids = [t["id"] for t in c.get("/api/users/dev/transactions").get_json()["items"]]
    assert txn_id not in ids

    # 12) logout devolve para a tela de login
    assert c.get("/auth/logout").status_code == 200
    assert c.get("/auth/me").status_code == 401


def test_frontend_funciona_sem_dev_login_usando_sessao_injetada(app_env):
    """Em produção não há dev-login: a UI entra por /auth/login. Simulamos a
    sessão já estabelecida e conferimos que o resto do fluxo continua igual."""
    _, app = app_env
    c = app.test_client()
    login(c, "prod-user")
    h = csrf_headers(c)

    assert c.get("/auth/me").get_json()["user_id"] == "prod-user"
    assert c.post("/api/users/prod-user/transactions", json={
        "description": "Aluguel", "amount": 1800, "type": "expense",
    }, headers=h).status_code == 201
    assert c.get("/api/users/prod-user/summary").get_json()["expenses_avulsa"] == 1800
