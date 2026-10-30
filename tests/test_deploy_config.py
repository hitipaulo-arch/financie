"""Testes dos artefatos de deploy (Fase 2).

O template de app settings do Azure e o `startup.txt` são a diferença entre um
deploy que funciona e um que sobe "verde" mas não serve ninguém. Estes testes
impedem que:
  - o template fique obsoleto (variável que o backend não lê mais, ou variável
    nova que o backend lê e ninguém configurou);
  - um segredo de verdade seja commitado no exemplo;
  - o comando de inicialização volte a apontar para a porta/entry point errados.
"""
from __future__ import annotations

import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "deploy", "azure-appsettings.example.json")
STARTUP = os.path.join(ROOT, "startup.txt")
DEPLOY_README = os.path.join(ROOT, "deploy", "README.md")

# Variáveis que precisam estar no template para produção funcionar.
OBRIGATORIAS = {
    "APP_ENV",
    "FLASK_SECRET_KEY",
    "GF_DB_URL",
    "APP_BASE_URL",
    "FRONTEND_ORIGINS",
    "POST_LOGIN_PATH",
    "TRUSTED_PROXY_COUNT",
    "ENABLE_DEV_LOGIN",
    "RATELIMIT_ENABLED",
    "RATELIMIT_STORAGE_URI",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "OPENFINANCE_ENABLE_REAL",
    "OPENFINANCE_WEBHOOK_SECRET",
    "SESSION_COOKIE_SECURE",
}

# Chaves cujo valor de exemplo jamais pode parecer um segredo real.
SENSIVEIS = {
    "FLASK_SECRET_KEY",
    "GOOGLE_CLIENT_SECRET",
    "OPENFINANCE_CLIENT_SECRET",
    "OPENFINANCE_WEBHOOK_SECRET",
}

# O Azure injeta sozinho; definir à mão é fonte de confusão.
NAO_DEFINIR = {"WEBSITE_SITE_NAME"}


def variaveis_lidas_pelo_backend():
    """Extrai do fonte toda variável de ambiente que a aplicação lê.

    Cobre `os.getenv`, `os.environ.get`, `os.environ["X"]` e o helper
    `env_flag("X")`, inclusive em chamadas multilinha. Percorre também
    `logger.py` (dono do `LOG_LEVEL`) e `providers.py`.
    """
    padroes = [
        r'getenv\(\s*"([A-Z_0-9]+)"',
        r'environ\.get\(\s*"([A-Z_0-9]+)"',
        r'environ\[\s*"([A-Z_0-9]+)"\s*\]',
        r'env_flag\(\s*"([A-Z_0-9]+)"',
    ]
    achadas = set()
    for arquivo in ("backend.py", "logger.py", "providers.py"):
        caminho = os.path.join(ROOT, arquivo)
        if not os.path.isfile(caminho):
            continue
        fonte = open(caminho, encoding="utf-8").read()
        for padrao in padroes:
            achadas |= set(re.findall(padrao, fonte))
    return achadas


@pytest.fixture(scope="module")
def config():
    with open(TEMPLATE, encoding="utf-8") as fh:
        return json.load(fh)


def test_template_e_json_valido_de_strings(config):
    assert isinstance(config, dict) and config, "o template precisa ser um objeto JSON"
    for chave, valor in config.items():
        assert isinstance(chave, str) and isinstance(valor, str), (
            f"{chave}: app settings do Azure são pares string/string, "
            f"recebi {type(valor).__name__}"
        )


def test_template_cobre_as_variaveis_de_producao(config):
    faltando = sorted(OBRIGATORIAS - set(config))
    assert not faltando, f"variáveis de produção ausentes do template: {faltando}"


def test_template_nao_tem_variavel_obsoleta(config):
    """Se o backend parar de ler uma variável, ela sai do template também."""
    lidas = variaveis_lidas_pelo_backend()
    assert lidas, "a extração falhou — o padrão de leitura de env mudou?"
    obsoletas = sorted(set(config) - lidas)
    assert not obsoletas, (
        f"o template define variáveis que o backend não lê: {obsoletas}"
    )


def test_template_nao_define_variaveis_da_plataforma(config):
    indevidas = sorted(set(config) & NAO_DEFINIR)
    assert not indevidas, f"o Azure injeta estas sozinho: {indevidas}"


def test_template_nao_vaza_segredo_real(config):
    for chave in sorted(SENSIVEIS):
        valor = config.get(chave, "")
        assert valor == "" or valor.startswith("TROQUE_"), (
            f"{chave} parece conter um valor real ({valor[:8]}…); "
            "use um placeholder TROQUE_ ou uma referência ao Key Vault"
        )


def test_placeholders_do_template_estao_marcados(config):
    """Todo placeholder é identificável — dá para conferir antes de aplicar."""
    marcados = {k for k, v in config.items() if v.startswith("TROQUE_")}
    assert marcados >= {"FLASK_SECRET_KEY", "GF_DB_URL", "APP_BASE_URL"}, (
        "valores específicos de ambiente precisam estar marcados com TROQUE_"
    )


def test_valores_booleanos_sao_do_formato_aceito(config):
    """env_flag() só entende 1/true/yes/on — 'True'/'sim' seriam surpresa."""
    aceitos = {"1", "true", "yes", "on", "0", "false", "no", "off", ""}
    for chave in ("ENABLE_DEV_LOGIN", "RATELIMIT_ENABLED", "FLASK_DEBUG",
                  "SESSION_COOKIE_SECURE", "SESSION_COOKIE_HTTPONLY",
                  "WTF_CSRF_SSL_STRICT", "OPENFINANCE_ENABLE_REAL"):
        if chave in config:
            assert config[chave].strip().lower() in aceitos, (
                f"{chave}={config[chave]!r} não é um booleano reconhecido"
            )


def test_template_trava_producao_segura(config):
    assert config["APP_ENV"] == "production"
    assert config["ENABLE_DEV_LOGIN"] == "false", "dev-login jamais em produção"
    assert config["FLASK_DEBUG"] == "false", "debug do Werkzeug permite RCE"
    assert config["SESSION_COOKIE_SECURE"] == "true"


def test_post_login_path_do_template_existe_no_repositorio(config):
    """O redirect pós-login não pode apontar para um arquivo inexistente."""
    caminho = config["POST_LOGIN_PATH"]
    assert caminho.startswith("/"), f"POST_LOGIN_PATH precisa ser interno: {caminho}"
    assert not caminho.startswith("//"), "caminho //host é open redirect"
    arquivo = os.path.join(ROOT, caminho.lstrip("/"))
    assert os.path.isfile(arquivo), f"{caminho} não existe no repositório"


# ---------------------------------------------------------------------------
# startup.txt
# ---------------------------------------------------------------------------
def test_startup_file_existe():
    assert os.path.isfile(STARTUP), "o App Service lê o startup.txt da raiz"


def test_startup_usa_o_entry_point_correto():
    cmd = open(STARTUP, encoding="utf-8").read().strip()
    assert cmd.startswith("gunicorn"), f"esperado gunicorn, obtido: {cmd[:40]}"
    assert "wsgi:app" in cmd, (
        "o gunicorn precisa importar o objeto app de wsgi.py; "
        "'backend:app' funciona por shim, mas cria o app de forma preguiçosa"
    )
    assert "backend:app" not in cmd


def test_startup_binda_na_porta_que_o_azure_espera():
    cmd = open(STARTUP, encoding="utf-8").read()
    assert "--bind 0.0.0.0:8000" in cmd, (
        "o App Service encaminha para a porta 8000 e exige bind em 0.0.0.0; "
        "127.0.0.1 ou outra porta fazem o deploy falhar com "
        "'container didn't respond to HTTP pings'"
    )


def test_startup_loga_para_stdout():
    """Sem isto nada aparece em *Log stream* / Application Insights."""
    cmd = open(STARTUP, encoding="utf-8").read()
    assert "--access-logfile -" in cmd
    assert "--error-logfile -" in cmd


def test_deploy_readme_documenta_o_basico():
    assert os.path.isfile(DEPLOY_README), "deploy/README.md não existe"
    texto = open(DEPLOY_README, encoding="utf-8").read().lower()
    for topico in ("key vault", "startup", "appsettings", "postgresql",
                   "frontend_origins", "checklist", "wsgi:app", "0.0.0.0:8000"):
        assert topico in texto, f"deploy/README.md não menciona: {topico}"
    # avisa para não aplicar o exemplo cru
    assert "troque_" in texto
