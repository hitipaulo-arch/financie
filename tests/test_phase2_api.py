"""Testes de regressão da Fase 2 — a API volta a funcionar.

Cobre os quatro problemas que tornavam a API inutilizável ou imprevisível:
  3.1 CSRF quebrado (6 endpoints permanentemente em 400)
  3.2 Sessão de banco sem teardown/rollback (contaminação entre requests)
  3.3 create_consent fora do parse_json (500 em vez de 400)
  3.4 Rate limiting global sufocando /api/health e estáticos
  2.6 CORS e redirect pós-login hardcoded em localhost

Para rodar:
    pytest tests/ -v
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.test_phase1_security import (  # noqa: E402
    build_app, csrf_headers, login, reload_backend,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def app_env(tmp_path):
    """App em produção padrão (CSRF ativo, rate limit ativo)."""
    backend, app = build_app({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'fase2.db'}",
        "APP_ENV": "production",
    })
    app.config["TESTING"] = False
    return backend, app


@pytest.fixture
def dev_env(tmp_path):
    """App em desenvolvimento com dev-login habilitado (para testar limites)."""
    backend, app = build_app({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'fase2dev.db'}",
        "APP_ENV": "development",
        "ENABLE_DEV_LOGIN": "true",
    })
    app.config["TESTING"] = False
    return backend, app


# ---------------------------------------------------------------------------
# 3.1 — CSRF: o token existe e destrava a API
# ---------------------------------------------------------------------------
def test_csrf_token_endpoint_devolve_token_real(app_env):
    """Antes: session.get('_csrf_token', 'N/A') -> sempre "N/A", porque o
    Flask-WTF grava a chave `csrf_token` e generate_csrf() nunca era chamado."""
    _, app = app_env
    client = app.test_client()
    login(client)

    resp = client.get("/api/csrf-token")
    assert resp.status_code == 200
    body = resp.get_json()

    assert body["csrf_token"] != "N/A"
    assert len(body["csrf_token"]) > 20
    assert body["header_name"] == "X-CSRFToken"


def test_token_csrf_e_reutilizavel_na_mesma_sessao(app_env):
    _, app = app_env
    client = app.test_client()
    login(client)

    primeiro = client.get("/api/csrf-token").get_json()["csrf_token"]
    segundo = client.get("/api/csrf-token").get_json()["csrf_token"]
    assert primeiro == segundo, "o token deve ser estável dentro da sessão"

    # E serve para mais de uma escrita
    for i in range(3):
        resp = client.post("/api/users/u1/transactions", json={
            "description": f"tx {i}", "amount": 10 + i, "type": "expense",
        }, headers={"X-CSRFToken": primeiro})
        assert resp.status_code == 201, resp.get_data(as_text=True)


def test_token_csrf_nao_expira_antes_da_sessao(app_env):
    """WTF_CSRF_TIME_LIMIT default (3600s) expirava antes dos 120min de sessão."""
    _, app = app_env
    assert app.config["WTF_CSRF_TIME_LIMIT"] is None
    vida_sessao = app.config["PERMANENT_SESSION_LIFETIME"].total_seconds()
    assert vida_sessao == 120 * 60


def test_escrita_sem_token_e_rejeitada(app_env):
    _, app = app_env
    client = app.test_client()
    login(client)

    resp = client.post("/api/users/u1/transactions", json={
        "description": "sem token", "amount": 1, "type": "expense",
    })
    assert resp.status_code == 400
    assert "CSRF" in resp.get_json()["details"]


def test_token_csrf_invalido_e_rejeitado(app_env):
    _, app = app_env
    client = app.test_client()
    login(client)
    client.get("/api/csrf-token")  # popula a sessão

    resp = client.post("/api/users/u1/transactions", json={
        "description": "token falso", "amount": 1, "type": "expense",
    }, headers={"X-CSRFToken": "token-inventado"})
    assert resp.status_code == 400


def test_header_alternativo_x_csrf_token_tambem_funciona(app_env):
    _, app = app_env
    client = app.test_client()
    login(client)
    token = csrf_headers(client)["X-CSRFToken"]

    resp = client.post("/api/users/u1/transactions", json={
        "description": "header alternativo", "amount": 1, "type": "expense",
    }, headers={"X-CSRF-Token": token})
    assert resp.status_code == 201


# ---- A matriz de escrita que estava 100% quebrada antes da Fase 2 ----------
def test_matriz_de_escrita_funciona_com_token(app_env):
    """PUT/DELETE de transações, TODO o CRUD de parcelas e POST /import
    respondiam 400 "The CSRF token is missing." na main — e não havia como
    obter um token válido. Aqui exercitamos o fluxo completo."""
    _, app = app_env
    client = app.test_client()
    login(client)
    h = csrf_headers(client)

    # --- transações -------------------------------------------------------
    criada = client.post("/api/users/u1/transactions", json={
        "description": "Salário", "amount": 5000, "type": "income",
        "date": "2026-01-05",
    }, headers=h)
    assert criada.status_code == 201, criada.get_data(as_text=True)
    txn_id = criada.get_json()["id"]
    assert criada.get_json()["date"] == "2026-01-05"  # fields.Date coerciona

    atual = client.put(f"/api/users/u1/transactions/{txn_id}",
                       json={"amount": 6000}, headers=h)
    assert atual.status_code == 200, atual.get_data(as_text=True)
    assert atual.get_json()["amount"] == 6000

    # --- parcelas (CRUD inteiro estava bloqueado) -------------------------
    parc = client.post("/api/users/u1/installments", json={
        "description": "Notebook", "monthly_value": 350.5, "total_months": 12,
    }, headers=h)
    assert parc.status_code == 201, parc.get_data(as_text=True)
    inst_id = parc.get_json()["id"]

    parc_atual = client.patch(f"/api/users/u1/installments/{inst_id}",
                              json={"total_months": 10}, headers=h)
    assert parc_atual.status_code == 200, parc_atual.get_data(as_text=True)
    assert parc_atual.get_json()["total_months"] == 10

    assert client.delete(f"/api/users/u1/installments/{inst_id}",
                         headers=h).status_code == 200

    # --- importação simulada ---------------------------------------------
    imp = client.post("/api/users/u1/import", headers=h)
    assert imp.status_code == 200, imp.get_data(as_text=True)
    assert imp.get_json()["imported"] == 3

    # --- investimentos ----------------------------------------------------
    inv = client.post("/api/users/u1/investments", json={
        "name": "Tesla", "asset_type": "stocks", "amount": 10,
        "purchase_price": 200.0, "current_price": 250.0,
        "purchase_date": "2026-01-10", "status": "active",
    }, headers=h)
    assert inv.status_code == 201, inv.get_data(as_text=True)
    inv_id = inv.get_json()["id"]

    inv_atual = client.put(f"/api/users/u1/investments/{inv_id}",
                           json={"current_price": 275.0}, headers=h)
    assert inv_atual.status_code == 200
    assert inv_atual.get_json()["current_price"] == 275.0

    # --- open finance -----------------------------------------------------
    consent = client.post("/api/users/u1/openfinance/consents", json={}, headers=h)
    assert consent.status_code == 201, consent.get_data(as_text=True)

    sync = client.post("/api/users/u1/openfinance/sync", headers=h)
    assert sync.status_code == 201, sync.get_data(as_text=True)
    assert sync.get_json()["imported"] == 3

    # segunda sync: deduplicação continua funcionando
    sync2 = client.post("/api/users/u1/openfinance/sync", headers=h)
    assert sync2.get_json()["imported"] == 0
    assert sync2.get_json()["skipped_duplicates"] == 3

    # --- exclusão de transação -------------------------------------------
    assert client.delete(f"/api/users/u1/transactions/{txn_id}",
                         headers=h).status_code == 200
    listing = client.get("/api/users/u1/transactions").get_json()
    ids = [t["id"] for t in listing["items"]]
    assert txn_id not in ids, "soft delete não removeu da listagem"


def test_get_nao_exige_token_csrf(app_env):
    """GET/HEAD/OPTIONS nunca exigem token (WTF_CSRF_METHODS)."""
    _, app = app_env
    client = app.test_client()
    login(client)

    for path in ("/api/users/u1/transactions", "/api/users/u1/summary",
                 "/api/users/u1/investments", "/api/health",
                 "/api/users/u1/openfinance/consents"):
        assert client.get(path).status_code == 200, path


def test_apenas_duas_isencoes_de_csrf_existem():
    """A política é uniforme: só webhook (HMAC) e dev-login (fora de produção)."""
    src = open(os.path.join(ROOT, "backend.py"), encoding="utf-8").read()
    assert src.count("@csrf.exempt") == 2, (
        "isenções de CSRF devem ser apenas /auth/dev-login e o webhook"
    )


# ---------------------------------------------------------------------------
# 3.2 — Teardown da sessão de banco
# ---------------------------------------------------------------------------
def test_request_falhado_nao_vaza_para_o_request_seguinte(app_env):
    """Reprodução exata do bug da análise.

    `update_transaction` aplica os campos em ordem; um payload com
    `description` válida e `date` inválida grava a descrição no ORM e só então
    lança 400. Sem rollback+remove no teardown, essa alteração pendente ficava
    na sessão scoped (presa à thread do worker sync) e era COMMITADA pelo
    próximo request — mudando um registro que o cliente nunca conseguiu alterar.
    """
    _, app = app_env
    client = app.test_client()
    login(client)
    h = csrf_headers(client)

    criada = client.post("/api/users/u1/transactions", json={
        "description": "Original", "amount": 100, "type": "expense",
    }, headers=h)
    txn_id = criada.get_json()["id"]

    falha = client.put(f"/api/users/u1/transactions/{txn_id}", json={
        "description": "ALTERACAO_FANTASMA",
        "date": "31/12/2026",  # formato inválido -> 400 no meio do handler
    }, headers=h)
    assert falha.status_code == 400

    # Outro request, sem relação, que faz commit
    assert client.post("/api/users/u1/transactions", json={
        "description": "outra", "amount": 1, "type": "income",
    }, headers=h).status_code == 201

    itens = client.get("/api/users/u1/transactions").get_json()["items"]
    original = next(t for t in itens if t["id"] == txn_id)
    assert original["description"] == "Original", (
        "a alteração do request que falhou vazou para o banco"
    )


def test_erro_de_banco_nao_deixa_sessao_em_estado_irrecuperavel(app_env):
    """Sem rollback, um erro deixava a sessão em PendingRollbackError e todas
    as requisições seguintes da thread falhavam até o restart do worker."""
    _, app = app_env
    client = app.test_client()
    login(client)
    h = csrf_headers(client)

    # força um erro de integridade: consent_id é UNIQUE
    assert client.post("/api/users/u1/openfinance/consents",
                       json={"consent_id": "duplicado"}, headers=h).status_code == 201

    duplicado = client.post("/api/users/u1/openfinance/consents",
                            json={"consent_id": "duplicado"}, headers=h)
    assert duplicado.status_code == 500

    # a aplicação precisa continuar saudável no request seguinte
    saudavel = client.post("/api/users/u1/transactions", json={
        "description": "depois do erro", "amount": 42, "type": "income",
    }, headers=h)
    assert saudavel.status_code == 201, saudavel.get_data(as_text=True)

    resumo = client.get("/api/users/u1/summary").get_json()
    assert resumo["income"] == 42


def test_teardown_registrado(app_env):
    _, app = app_env
    nomes = [f.__name__ for f in app.teardown_appcontext_funcs]
    assert "shutdown_db_session" in nomes


# ---------------------------------------------------------------------------
# 3.3 — create_consent validado
# ---------------------------------------------------------------------------
def test_consent_invalido_devolve_400_e_nao_grava(app_env):
    _, app = app_env
    client = app.test_client()
    login(client)
    h = csrf_headers(client)

    resp = client.post("/api/users/u1/openfinance/consents",
                       json={"status": "nao-existe"}, headers=h)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "bad_request"

    assert client.get("/api/users/u1/openfinance/consents").get_json()["pagination"]["total"] == 0


# ---------------------------------------------------------------------------
# 3.4 — Rate limiting
# ---------------------------------------------------------------------------
def test_health_check_nao_e_limitado(app_env):
    """Antes: default_limits valia para /api/health — 55 chamadas já davam 429
    (verificado na main), o que faz o Azure marcar a app como indisponível."""
    _, app = app_env
    client = app.test_client()

    codes = [client.get("/api/health").status_code for _ in range(120)]
    assert 429 not in codes, f"health check levou 429: {codes.count(429)} vezes"
    assert set(codes) == {200}


def test_arquivos_estaticos_nao_consomem_cota(app_env):
    _, app = app_env
    client = app.test_client()

    codes = [client.get("/static/nao-existe.txt").status_code for _ in range(120)]
    assert 429 not in codes, f"estáticos levaram 429: {codes.count(429)} vezes"


def test_csrf_token_e_raiz_nao_sao_limitados(app_env):
    _, app = app_env
    client = app.test_client()
    login(client)

    assert 429 not in [client.get("/api/csrf-token").status_code for _ in range(80)]
    assert 429 not in [client.get("/").status_code for _ in range(80)]


def test_endpoint_de_login_tem_limite_apertado(dev_env):
    """/auth/dev-login é um endpoint de login: 5/min."""
    _, app = dev_env
    client = app.test_client()

    codes = [client.post("/auth/dev-login", json={"user_id": "x"}).status_code
             for _ in range(8)]
    assert codes[:5] == [200] * 5, codes
    assert 429 in codes[5:], f"limite de login não disparou: {codes}"


def test_rate_limit_por_ip_real_gracas_ao_proxyfix(dev_env):
    """Sem ProxyFix, remote_addr era o IP do balanceador: todos os usuários
    dividiam o mesmo balde (um abusador derrubava a API para todos)."""
    _, app = dev_env
    client = app.test_client()

    def chama(ip):
        return client.post("/auth/dev-login", json={"user_id": "x"},
                           headers={"X-Forwarded-For": ip}).status_code

    assert [chama("203.0.113.10") for _ in range(5)] == [200] * 5
    assert chama("203.0.113.10") == 429, "o IP abusador deveria estar limitado"
    # Um usuário diferente NÃO pode ser punido pelo abuso do primeiro
    assert chama("198.51.100.77") == 200, "balde de rate limit é compartilhado"


def test_dar_para_desligar_rate_limit_por_env(tmp_path):
    """Válvula de escape para suítes de teste e ambientes controlados."""
    backend, app = build_app({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'nolimit.db'}",
        "APP_ENV": "development",
        "ENABLE_DEV_LOGIN": "true",
        "RATELIMIT_ENABLED": "false",
    })
    app.config["TESTING"] = False
    client = app.test_client()

    codes = [client.post("/auth/dev-login", json={"user_id": "x"}).status_code
             for _ in range(12)]
    assert 429 not in codes


def test_storage_uri_vem_de_env(tmp_path):
    """memory:// é por instância; no Azure escalado é preciso Redis.

    Só recarregamos o módulo (sem criar o app): instanciar o Limiter com
    redis:// exige o pacote `redis` (limits[redis]), que não é dependência
    do projeto — e é exatamente por isso que o README documenta o extra.
    """
    backend = reload_backend({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'storage.db'}",
        "RATELIMIT_STORAGE_URI": "redis://localhost:6379",
    })
    assert backend.RATELIMIT_STORAGE_URI == "redis://localhost:6379"

    # default continua memory://
    backend2 = reload_backend({"GF_DB_URL": f"sqlite:///{tmp_path / 'storage2.db'}"})
    assert backend2.RATELIMIT_STORAGE_URI == "memory://"


# ---------------------------------------------------------------------------
# 2.6 — CORS e redirect pós-login
# ---------------------------------------------------------------------------
def test_cors_vem_de_frontend_origins(tmp_path):
    """Antes: origins hardcoded em localhost:5000 -> no Azure o navegador não
    recebia Access-Control-Allow-Origin e nenhuma chamada do frontend funcionava."""
    backend, app = build_app({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'cors.db'}",
        "FRONTEND_ORIGINS": "https://gestao.azurewebsites.net, https://app.exemplo.com.br",
    })
    assert backend.FRONTEND_ORIGINS == [
        "https://gestao.azurewebsites.net", "https://app.exemplo.com.br",
    ]

    client = app.test_client()
    permitido = client.get("/api/health",
                           headers={"Origin": "https://gestao.azurewebsites.net"})
    assert permitido.headers.get("Access-Control-Allow-Origin") == "https://gestao.azurewebsites.net"

    estranho = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert estranho.headers.get("Access-Control-Allow-Origin") is None


def test_cors_default_preserva_localhost_para_dev(tmp_path):
    backend, app = build_app({"GF_DB_URL": f"sqlite:///{tmp_path / 'cors2.db'}"})
    assert "http://localhost:5000" in backend.FRONTEND_ORIGINS

    client = app.test_client()
    resp = client.get("/api/health", headers={"Origin": "http://localhost:5000"})
    assert resp.headers.get("Access-Control-Allow-Origin") == "http://localhost:5000"


def test_sem_localhost_hardcoded_no_backend():
    src = open(os.path.join(ROOT, "backend.py"), encoding="utf-8").read()
    assert "http://localhost:5000/index_api.html" not in src
    # a única menção a localhost aceita é o default de FRONTEND_ORIGINS
    for linha in src.splitlines():
        if "localhost" in linha and "FRONTEND_ORIGINS" not in linha and "#" not in linha:
            pytest.fail(f"localhost hardcoded fora do default de FRONTEND_ORIGINS: {linha.strip()}")


def test_internal_path_bloqueia_open_redirect():
    from backend import internal_path

    assert internal_path("/static/index.html") == "/static/index.html"
    assert internal_path("/") == "/"
    # URL absoluta e protocol-relative viram "/"
    assert internal_path("//evil.example/robo") == "/"
    assert internal_path("https://evil.example") == "/"
    assert internal_path("http://evil.example") == "/"
    assert internal_path("") == "/"
    assert internal_path("   ") == "/"


def test_redirect_pos_login_usa_app_base_url(tmp_path, monkeypatch):
    """Antes: redirect('http://localhost:5000/index_api.html?logged=true') —
    no Azure mandava o usuário para localhost e para um arquivo inexistente."""
    # authlib >= 1.6 renomeou o client registrado pelo Flask para FlaskOAuth2App
    from authlib.integrations.flask_client import FlaskOAuth2App

    monkeypatch.setattr(
        FlaskOAuth2App, "authorize_access_token",
        lambda self, *a, **k: {"userinfo": {
            "sub": "google-sub-1", "email": "user@gmail.com",
            "name": "Usuária", "picture": None,
        }},
    )

    backend, app = build_app({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'login.db'}",
        "APP_ENV": "production",
        "GOOGLE_CLIENT_ID": "id.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "segredo",
        "APP_BASE_URL": "https://gestao.azurewebsites.net/",
        "POST_LOGIN_PATH": "/static/app.html",
    })
    app.config["TESTING"] = False

    resp = app.test_client().get("/auth/callback")
    assert resp.status_code == 302
    local = resp.headers["Location"]
    assert local == "https://gestao.azurewebsites.net/static/app.html?logged=true"
    assert "localhost" not in local

    # a sessão foi populada com o usuário do Google
    with app.test_client() as c2:
        c2.get("/auth/callback")
        eu = c2.get("/auth/me").get_json()
        assert eu["user_id"] == "google-sub-1"


def test_redirect_pos_login_nao_vira_open_redirect(tmp_path, monkeypatch):
    # authlib >= 1.6 renomeou o client registrado pelo Flask para FlaskOAuth2App
    from authlib.integrations.flask_client import FlaskOAuth2App

    monkeypatch.setattr(
        FlaskOAuth2App, "authorize_access_token",
        lambda self, *a, **k: {"userinfo": {"sub": "s1", "email": "e@x.com",
                                            "name": "N", "picture": None}},
    )
    _, app = build_app({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'login2.db'}",
        "APP_ENV": "production",
        "GOOGLE_CLIENT_ID": "id.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "segredo",
        "APP_BASE_URL": "https://gestao.azurewebsites.net",
        "POST_LOGIN_PATH": "//evil.example/roubo",
    })
    app.config["TESTING"] = False

    local = app.test_client().get("/auth/callback").headers["Location"]
    assert "evil.example" not in local
    assert local.startswith("https://gestao.azurewebsites.net/")


# ---------------------------------------------------------------------------
# Bônus da Fase 2 — efeitos colaterais no import, leak no webhook e debug/RCE
# ---------------------------------------------------------------------------
def test_backend_nao_cria_app_no_import(tmp_path):
    """Antes havia `app = create_app()` em nível de módulo.

    Consequências reais: `alembic/env.py` faz `from backend import Base` e, com
    isso, cada migração abria conexão e rodava create_all(); e o `wsgi.py`
    (que chama create_app()) gerava um SEGUNDO app a cada boot — tabelas,
    provider e Limiter inicializados duas vezes.
    """
    backend = reload_backend({"GF_DB_URL": f"sqlite:///{tmp_path / 'import.db'}"})

    assert "app" not in vars(backend), "app não pode ser criado no import"
    assert not os.path.exists(tmp_path / "import.db"), (
        "o import do módulo não deve tocar no banco"
    )
    assert callable(backend.create_app)


def test_backend_app_continua_acessivel_sob_demanda(tmp_path):
    """O shim PEP 562 mantém `backend:app` funcionando (gunicorn/flask --app),
    mas só cria o app no primeiro acesso."""
    backend = reload_backend({"GF_DB_URL": f"sqlite:///{tmp_path / 'lazy.db'}"})
    assert "app" not in vars(backend)

    app = backend.app
    assert app.test_client().get("/api/health").status_code == 200
    assert backend.app is app, "o app sob demanda deve ser cacheado"


def test_webhook_erro_interno_nao_vaza_detalhes(tmp_path):
    """O handler do webhook tinha o mesmo vazamento corrigido na Fase 1 nos
    demais handlers: `{"details": str(e)}`."""
    import hashlib
    import hmac

    secret = "segredo-fase2"
    backend, app = build_app({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'wh.db'}",
        "APP_ENV": "production",
        "OPENFINANCE_WEBHOOK_SECRET": secret,
    })
    app.config["TESTING"] = False

    corpo = b"{ isto nao e json valido"
    assinatura = hmac.new(secret.encode(), corpo, hashlib.sha256).hexdigest()

    resp = app.test_client().post(
        "/api/openfinance/webhook",
        data=corpo,
        content_type="application/json",
        headers={"X-Webhook-Signature": assinatura},
    )
    body = resp.get_data(as_text=True)

    assert resp.status_code == 500
    payload = resp.get_json()
    assert payload["error"] == "webhook_processing_failed"
    assert payload["details"] == "Falha ao processar o webhook."
    # Nenhum resquício do parser/traceback no corpo
    for vazamento in ("werkzeug", "BadRequest", "decode JSON", "400 Bad Request"):
        assert vazamento.lower() not in body.lower(), vazamento
    assert set(payload) == {"error", "details"}


def test_debug_do_werkzeug_nao_liga_por_padrao(tmp_path):
    """`app.run(host="0.0.0.0", debug=True)` expunha o debugger interativo do
    Werkzeug (execução remota de código) na porta 5000 — e o README manda rodar
    exatamente `python backend.py`."""
    backend = reload_backend({"GF_DB_URL": f"sqlite:///{tmp_path / 'dbg.db'}"})
    assert backend.env_flag("FLASK_DEBUG") is False

    backend2 = reload_backend({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'dbg2.db'}",
        "FLASK_DEBUG": "true",
    })
    assert backend2.env_flag("FLASK_DEBUG") is True

    src = open(os.path.join(ROOT, "backend.py"), encoding="utf-8").read()
    assert "debug=True" not in src
