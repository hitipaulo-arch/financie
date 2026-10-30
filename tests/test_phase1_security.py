"""Testes de regressão das correções de segurança da Fase 1.

Cada teste aqui reproduz uma vulnerabilidade ou bug confirmado na análise de
2026-10-29 e garante que ele não volte.

Para rodar:
    pytest tests/ -v
"""
from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import os
import sys
from datetime import datetime, UTC

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
BASE_ENV = {
    # Banco isolado por teste (definido em `env`)
    "GF_DB_URL": "",
    "DATABASE_URL": "",
    "SECRET_KEY": "",
    "FLASK_SECRET_KEY": "chave-fixa-para-testes",
    "LOG_LEVEL": "ERROR",
    "SESSION_LIFETIME_MINUTES": "120",
}

# Toda variável de ambiente que o backend lê. `build_app` limpa todas antes de
# aplicar o cenário do teste — sem isso um teste vaza configuração para o
# seguinte (o módulo resolve as flags no import).
APP_ENV_VARS = [
    "APP_ENV", "ENABLE_DEV_LOGIN", "WEBSITE_SITE_NAME", "DEV_LOGIN_RATE_LIMIT",
    "OPENFINANCE_ENABLE_REAL", "OPENFINANCE_WEBHOOK_SECRET",
    "OPENFINANCE_BASE_URL", "OPENFINANCE_CLIENT_ID", "OPENFINANCE_CLIENT_SECRET",
    "OPENFINANCE_CERT_PATH", "OPENFINANCE_KEY_PATH",
    "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
    "SESSION_COOKIE_SECURE", "SESSION_COOKIE_HTTPONLY", "SESSION_COOKIE_SAMESITE",
    "FRONTEND_ORIGINS", "APP_BASE_URL", "POST_LOGIN_PATH",
    "TRUSTED_PROXY_COUNT", "RATELIMIT_STORAGE_URI", "RATELIMIT_ENABLED",
    "WTF_CSRF_SSL_STRICT", "FLASK_DEBUG", "FLASK_RUN_HOST", "PORT",
]


def reload_backend(extra_env: dict | None = None):
    """Aplica o ambiente e recarrega o módulo `backend` (sem criar o app).

    O reload é necessário porque as flags (APP_ENV, DEV_LOGIN_ENABLED,
    IS_PRODUCTION, FRONTEND_ORIGINS...) são resolvidas no import do módulo.
    """
    env = dict(BASE_ENV)
    env.update(extra_env or {})

    for key in APP_ENV_VARS:
        os.environ.pop(key, None)

    for key, value in env.items():
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)

    return importlib.reload(importlib.import_module("backend"))


def build_app(extra_env: dict | None = None):
    """Recarrega o `backend` com o ambiente desejado e devolve (módulo, app)."""
    backend = reload_backend(extra_env)
    return backend, backend.create_app()


def login(client, user_id: str = "u1"):
    """Injeta uma sessão autenticada sem depender do /auth/dev-login."""
    with client.session_transaction() as sess:
        sess["user"] = {
            "id": user_id,
            "email": f"{user_id}@example.com",
            "name": "Usuário de Teste",
            "picture": None,
        }


def csrf_headers(client) -> dict:
    """Faz o que qualquer cliente real precisa fazer antes de escrever:
    GET /api/csrf-token e devolver o header X-CSRFToken.

    Na Fase 2 o CSRF passou a ser exigido de forma uniforme em toda rota que
    muda estado, então os testes de escrita usam este helper.
    """
    resp = client.get("/api/csrf-token")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    token = resp.get_json()["csrf_token"]
    assert token and token != "N/A", "endpoint de CSRF não devolveu um token real"
    return {"X-CSRFToken": token}


@pytest.fixture
def prod_app(tmp_path):
    """App em configuração de produção padrão (nenhuma flag de dev)."""
    backend, app = build_app({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'prod.db'}",
        "APP_ENV": "production",
    })
    app.config["TESTING"] = False
    return backend, app


@pytest.fixture
def dev_app(tmp_path):
    """App em desenvolvimento com dev-login explicitamente habilitado."""
    backend, app = build_app({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'dev.db'}",
        "APP_ENV": "development",
        "ENABLE_DEV_LOGIN": "true",
    })
    app.config["TESTING"] = False
    return backend, app


# ---------------------------------------------------------------------------
# 2.1 — Exposição de arquivos pela raiz (static_folder='.')
# ---------------------------------------------------------------------------
SENSITIVE_PATHS = [
    "/backend.py",
    "/providers.py",
    "/logger.py",
    "/requirements.txt",
    "/alembic.ini",
    "/.env",
    "/.env.example",
    "/.git/config",
    "/.gitignore",
    "/wsgi.py",
]


@pytest.mark.parametrize("path", SENSITIVE_PATHS)
def test_arquivos_do_projeto_nao_sao_servidos(prod_app, path):
    """Antes: static_folder='.' devolvia 200 com o conteúdo de qualquer
    arquivo da raiz do projeto — incluindo código-fonte, .env e .git/config."""
    _, app = prod_app
    resp = app.test_client().get(path)
    assert resp.status_code == 404, f"{path} ainda está exposto ({resp.status_code})"
    assert b"SECRET" not in resp.data
    assert b"sqlalchemy" not in resp.data


def test_pasta_estatica_e_dedicada(prod_app):
    _, app = prod_app
    assert app.static_folder.rstrip("/").endswith("/static")
    assert app.static_url_path == "/static"


def test_conteudo_de_static_e_servido(prod_app):
    """O único diretório público é ./static."""
    _, app = prod_app
    arquivo = os.path.join(app.static_folder, "ping.txt")
    with open(arquivo, "w", encoding="utf-8") as fh:
        fh.write("ok")
    try:
        resp = app.test_client().get("/static/ping.txt")
        assert resp.status_code == 200
        assert resp.data == b"ok"
    finally:
        os.remove(arquivo)


# ---------------------------------------------------------------------------
# 2.2 — Bypass de autenticação via /auth/dev-login
# ---------------------------------------------------------------------------
VICTIM_ID = "112233445566778899"


def test_dev_login_bloqueado_em_producao(prod_app):
    """Antes: `not OPENFINANCE_ENABLE_REAL` (default false) liberava o
    endpoint em produção e permitia assumir qualquer user_id."""
    _, app = prod_app
    client = app.test_client()

    resp = client.post("/auth/dev-login", json={"user_id": VICTIM_ID})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "dev_login_disabled"

    # E, principalmente: nenhuma sessão foi criada.
    assert client.get("/auth/me").status_code == 401


def test_dev_login_bloqueado_em_producao_mesmo_com_flag(tmp_path):
    """ENABLE_DEV_LOGIN=true não pode abrir a porta dos fundos na nuvem:
    APP_ENV=production e WEBSITE_SITE_NAME (Azure) vetam o recurso."""
    for extra in (
        {"APP_ENV": "production", "ENABLE_DEV_LOGIN": "true"},
        {"APP_ENV": "development", "ENABLE_DEV_LOGIN": "true",
         "WEBSITE_SITE_NAME": "gestao-financeira"},
    ):
        backend, app = build_app({
            "GF_DB_URL": f"sqlite:///{tmp_path / 'flag.db'}", **extra
        })
        app.config["TESTING"] = False
        assert backend.DEV_LOGIN_ENABLED is False, extra
        resp = app.test_client().post("/auth/dev-login", json={"user_id": VICTIM_ID})
        assert resp.status_code == 403, extra


def test_dev_login_bloqueado_sem_flag_em_desenvolvimento(tmp_path):
    """Fail-closed: APP_ENV=development sozinho não habilita o endpoint."""
    backend, app = build_app({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'noflag.db'}",
        "APP_ENV": "development",
    })
    app.config["TESTING"] = False
    assert backend.DEV_LOGIN_ENABLED is False
    assert app.test_client().post("/auth/dev-login", json={}).status_code == 403


def test_dev_login_funciona_apenas_com_opt_in_explicito(dev_app):
    backend, app = dev_app
    assert backend.DEV_LOGIN_ENABLED is True

    client = app.test_client()
    resp = client.post("/auth/dev-login", json={"user_id": "dev1"})
    assert resp.status_code == 200
    assert client.get("/auth/me").get_json()["user_id"] == "dev1"


def test_app_env_default_e_producao(tmp_path):
    """Sem APP_ENV definido, o backend deve assumir produção."""
    backend, _ = build_app({"GF_DB_URL": f"sqlite:///{tmp_path / 'default.db'}"})
    assert backend.APP_ENV == "production"
    assert backend.IS_PRODUCTION is True
    assert backend.DEV_LOGIN_ENABLED is False


def test_dados_de_outro_usuario_inacessiveis_sem_sessao(prod_app):
    _, app = prod_app
    client = app.test_client()
    assert client.get(f"/api/users/{VICTIM_ID}/summary").status_code == 401
    assert client.get(f"/api/users/{VICTIM_ID}/transactions").status_code == 401


# ---------------------------------------------------------------------------
# 2.3 — Vazamento de detalhes internos em erros
# ---------------------------------------------------------------------------
def test_erro_500_nao_vaza_detalhes_internos(prod_app):
    """Antes: `return jsonify({"details": str(e)}), 500` devolvia a mensagem
    crua do driver de banco / configuração ao cliente."""
    _, app = prod_app

    segredo = "postgresql://admin:SuperSecret123@db-interno:5432/financas"

    @app.route("/__test_boom")
    def boom():  # pragma: no cover - rota de teste
        raise RuntimeError(segredo)

    resp = app.test_client().get("/__test_boom")
    body = resp.get_data(as_text=True)

    assert resp.status_code == 500
    assert resp.get_json()["error"] == "internal_error"
    assert "SuperSecret123" not in body
    assert "db-interno" not in body
    assert "RuntimeError" not in body
    # Existe um id de correlação para o suporte cruzar com o log
    assert len(resp.get_json()["error_id"]) == 16


def test_httpexception_mantem_codigo_original(prod_app):
    """404/405 do Werkzeug não podem virar 500."""
    _, app = prod_app
    client = app.test_client()
    assert client.get("/rota-que-nao-existe").status_code == 404
    assert client.delete("/api/health").status_code == 405


def test_erro_de_validacao_do_marshmallow_vira_400(prod_app):
    """Antes: create_consent chamava `schema.load()` fora do parse_json e o
    ValidationError escapava como 500 com as mensagens internas no corpo."""
    _, app = prod_app
    client = app.test_client()
    login(client)

    resp = client.post("/api/users/u1/openfinance/consents",
                       json={"status": "valor-invalido"},
                       headers=csrf_headers(client))
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "bad_request"
    assert "status" in body["details"]


def test_falha_de_sync_nao_vaza_configuracao(tmp_path):
    """Antes: `{"error": "sync_failed", "details": str(e)}` expunha quais
    variáveis de ambiente do provider estavam faltando.

    Reprodução real: OPENFINANCE_ENABLE_REAL=true sem as credenciais faz o
    OpenFinanceProvider levantar ValueError listando os nomes das variáveis.
    """
    backend, app = build_app({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'sync.db'}",
        "APP_ENV": "development",
        "ENABLE_DEV_LOGIN": "true",
        "OPENFINANCE_ENABLE_REAL": "true",
        # credenciais deliberadamente ausentes
    })
    app.config["TESTING"] = False
    assert isinstance(backend.OpenFinanceProvider, type)

    client = app.test_client()
    login(client)
    headers = csrf_headers(client)
    assert client.post("/api/users/u1/openfinance/consents", json={},
                       headers=headers).status_code == 201

    resp = client.post("/api/users/u1/openfinance/sync", headers=headers)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 500
    assert resp.get_json()["error"] == "sync_failed"
    for sensivel in ("OPENFINANCE_BASE_URL", "OPENFINANCE_CLIENT_ID",
                     "OPENFINANCE_CLIENT_SECRET", "Configurações faltantes"):
        assert sensivel not in body


# ---------------------------------------------------------------------------
# 2.4 — Webhook sem autenticação
# ---------------------------------------------------------------------------
def _criar_consent(backend, user_id="u1", consent_id="consent-123", status="active"):
    session_local = backend.get_session_local()
    db = session_local()
    consent = backend.Consent(
        user_id=user_id,
        consent_id=consent_id,
        provider="simulated",
        scopes="accounts:read",
        status=status,
        created_at=datetime.now(UTC),
    )
    db.add(consent)
    db.commit()
    db.close()
    return consent


def test_webhook_desativado_sem_segredo(prod_app):
    """Antes: sem OPENFINANCE_WEBHOOK_SECRET qualquer pessoa podia revogar
    consentimentos de terceiros (`if webhook_secret:` = verificação opcional)."""
    backend, app = prod_app
    _criar_consent(backend)

    resp = app.test_client().post(
        "/api/openfinance/webhook",
        json={"event": "consent.revoked", "consent_id": "consent-123"},
    )
    assert resp.status_code == 503
    assert resp.get_json()["error"] == "webhook_not_configured"

    # O consentimento NÃO pode ter sido alterado
    db = backend.get_session_local()()
    assert db.query(backend.Consent).filter_by(consent_id="consent-123").one().status == "active"
    db.close()


@pytest.fixture
def webhook_app(tmp_path):
    secret = "segredo-hmac-de-teste"
    backend, app = build_app({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'webhook.db'}",
        "APP_ENV": "production",
        "OPENFINANCE_WEBHOOK_SECRET": secret,
    })
    app.config["TESTING"] = False
    return backend, app, secret


def _assinar(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def test_webhook_rejeita_assinatura_invalida(webhook_app):
    backend, app, secret = webhook_app
    _criar_consent(backend)
    payload = json.dumps({"event": "consent.revoked", "consent_id": "consent-123"}).encode()

    resp = app.test_client().post(
        "/api/openfinance/webhook",
        data=payload,
        content_type="application/json",
        headers={"X-Webhook-Signature": "assinatura-falsa"},
    )
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "invalid_signature"

    db = backend.get_session_local()()
    assert db.query(backend.Consent).filter_by(consent_id="consent-123").one().status == "active"
    db.close()


def test_webhook_rejeita_ausencia_de_assinatura(webhook_app):
    backend, app, _ = webhook_app
    _criar_consent(backend)

    resp = app.test_client().post(
        "/api/openfinance/webhook",
        json={"event": "consent.revoked", "consent_id": "consent-123"},
    )
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "missing_signature"


def test_webhook_aceita_assinatura_valida(webhook_app):
    backend, app, secret = webhook_app
    _criar_consent(backend)
    payload = json.dumps({"event": "consent.revoked", "consent_id": "consent-123"}).encode()

    resp = app.test_client().post(
        "/api/openfinance/webhook",
        data=payload,
        content_type="application/json",
        headers={"X-Webhook-Signature": _assinar(payload, secret)},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    db = backend.get_session_local()()
    assert db.query(backend.Consent).filter_by(consent_id="consent-123").one().status == "revoked"
    db.close()


def test_webhook_aceita_prefixo_sha256(webhook_app):
    """Formato comum em provedores reais: `sha256=<hex>`."""
    backend, app, secret = webhook_app
    _criar_consent(backend, consent_id="consent-456")
    payload = json.dumps({"event": "consent.expired", "consent_id": "consent-456"}).encode()

    resp = app.test_client().post(
        "/api/openfinance/webhook",
        data=payload,
        content_type="application/json",
        headers={"X-Webhook-Signature": f"sha256={_assinar(payload, secret)}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    db = backend.get_session_local()()
    assert db.query(backend.Consent).filter_by(consent_id="consent-456").one().status == "expired"
    db.close()


def test_webhook_funciona_sem_request_anterior(webhook_app):
    """Antes: `db = SessionLocal()` quebrava com TypeError se o webhook fosse
    a primeira rota chamada após o boot (global ainda None)."""
    backend, app, secret = webhook_app
    assert backend.SessionLocal is None

    _criar_consent(backend, consent_id="consent-789")  # inicializa SessionLocal
    backend.SessionLocal = None  # simula boot sem nenhuma rota anterior
    payload = json.dumps({"event": "consent.revoked", "consent_id": "consent-789"}).encode()

    resp = app.test_client().post(
        "/api/openfinance/webhook",
        data=payload,
        content_type="application/json",
        headers={"X-Webhook-Signature": _assinar(payload, secret)},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Regressões de fumaça: o app continua servindo o que servia
# ---------------------------------------------------------------------------
def test_rotas_publicas_continuam_funcionando(prod_app):
    _, app = prod_app
    client = app.test_client()
    assert client.get("/api/health").get_json() == {"status": "ok"}
    assert client.get("/api/investments/tips").status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_crud_autenticado_continua_funcionando(prod_app):
    """As correções de segurança não podem ter quebrado o caminho feliz."""
    _, app = prod_app
    client = app.test_client()
    login(client, "u1")

    criada = client.post("/api/users/u1/transactions", json={
        "description": "Salário", "amount": 5000, "type": "income",
    }, headers=csrf_headers(client))
    assert criada.status_code == 201, criada.get_data(as_text=True)

    listing = client.get("/api/users/u1/transactions")
    assert listing.status_code == 200
    assert listing.get_json()["pagination"]["total"] == 1

    resumo = client.get("/api/users/u1/summary").get_json()
    assert resumo["income"] == 5000
    assert resumo["balance"] == 5000


def test_cookie_secure_em_producao(tmp_path):
    """Fail-closed: em produção o cookie de sessão é Secure por padrão."""
    _, app = build_app({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'cookie.db'}",
        "APP_ENV": "production",
    })
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True

    _, dev = build_app({
        "GF_DB_URL": f"sqlite:///{tmp_path / 'cookie2.db'}",
        "APP_ENV": "development",
    })
    assert dev.config["SESSION_COOKIE_SECURE"] is False
