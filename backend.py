"""Backend robusto para Gestor Financeiro.

Funcionalidades atuais:
- CRUD de transações (receitas/despesas)
- CRUD de compras parceladas
- Summary (totais e saldo)
- Importação simulada de extrato (Open Finance)
- Health check e tratamento uniforme de erros

Persistência: SQLite via SQLAlchemy.
Serialização/validação: Marshmallow.
"""

from datetime import datetime, date, timedelta, UTC
from typing import Optional
import hashlib
import hmac
import secrets
from functools import wraps
import time

from flask import Flask, jsonify, request, redirect, url_for, session
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, generate_csrf
from werkzeug.middleware.proxy_fix import ProxyFix
from decimal import Decimal
from sqlalchemy import (
    create_engine, Integer, String, Float, Numeric, Date, Column, DateTime,
    Index, case, func,
)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from marshmallow import Schema, fields, ValidationError, validate
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import os
from providers import SimulatedProvider, OpenFinanceProvider
from logger import logger, LogContext

load_dotenv()

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
def resolve_db_url() -> str:
    """Resolve a connection string: DATABASE_URL (Azure) → GF_DB_URL (local).

    Existe como função (e não só a constante abaixo) porque o `alembic/env.py`
    precisa re-resolver no momento da migração. Importar a constante `DB_URL`
    congelaria o valor lido no primeiro import do módulo — dentro de um processo
    de teste, ou de um boot que mudou o ambiente depois, a migração iria para o
    banco errado sem nenhum aviso.
    """
    return os.getenv("DATABASE_URL") or os.getenv("GF_DB_URL", "sqlite:///data.db")


# Suporta tanto DATABASE_URL (Azure) quanto GF_DB_URL (local)
DB_URL = resolve_db_url()
# Suporta tanto SECRET_KEY (Azure) quanto FLASK_SECRET_KEY (local)
_SECRET_KEY_CONFIGURED = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY")
FLASK_SECRET_KEY = _SECRET_KEY_CONFIGURED or secrets.token_hex(32)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")


def env_flag(name: str, default: str = "false") -> bool:
    """Interpreta uma variável de ambiente booleana de forma previsível.

    Aceita 1/true/yes/on (case-insensitive) como verdadeiro; qualquer outro
    valor (inclusive ausente) é falso, a menos que `default` diga o contrário.
    """
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Ambiente
# ---------------------------------------------------------------------------
# Fail-closed: na ausência de APP_ENV assumimos produção, para que recursos de
# desenvolvimento nunca fiquem ativos por acidente num deploy.
APP_ENV = os.getenv("APP_ENV", "production").strip().lower()
# O Azure App Service sempre define WEBSITE_SITE_NAME; usamos como reforço para
# que um APP_ENV errado não consiga "ligar" modo desenvolvimento na nuvem.
IS_PRODUCTION = APP_ENV in ("production", "prod") or bool(os.getenv("WEBSITE_SITE_NAME"))

# Porta dos fundos de desenvolvimento (/auth/dev-login).
# Antes era liberada por `not OPENFINANCE_ENABLE_REAL`, cujo default é false —
# ou seja, ficava ABERTA EM PRODUÇÃO e permitia assumir a identidade de
# qualquer user_id. Agora exige opt-in explícito E ambiente não-produtivo.
DEV_LOGIN_ENABLED = env_flag("ENABLE_DEV_LOGIN") and not IS_PRODUCTION

# ---------------------------------------------------------------------------
# URLs públicas, CORS e proxy reverso
# ---------------------------------------------------------------------------
# Origens autorizadas a chamar a API com o cookie de sessão.
# Antes era hardcoded em http://localhost:5000 — no Azure o navegador não
# recebia Access-Control-Allow-Origin e nenhuma chamada do frontend funcionava.
FRONTEND_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "FRONTEND_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000"
    ).split(",")
    if origin.strip()
]

# URL pública da aplicação (ex.: https://gestao.azurewebsites.net).
# Quando ausente, derivamos do próprio request — que só sai com https:// e o
# host certo porque aplicamos ProxyFix abaixo.
APP_BASE_URL = (os.getenv("APP_BASE_URL") or "").strip().rstrip("/")

# Destino do redirect após o callback do Google (antes: localhost:5000 fixo).
POST_LOGIN_PATH = os.getenv("POST_LOGIN_PATH", "/static/index.html")

# Quantidade de proxies reversos confiáveis na frente do app (Azure = 1).
# Sem ProxyFix, request.remote_addr é o IP do balanceador: todos os usuários
# caem no MESMO balde de rate limit (um abusador derruba a API para todos) e
# url_for(_external=True) gera http:// em vez de https://.
TRUSTED_PROXY_COUNT = max(0, int(os.getenv("TRUSTED_PROXY_COUNT", "1")))

# Backend do rate limiter. memory:// vale por processo/instância: com mais de
# uma instância no Azure, cada uma conta seu próprio limite. Use Redis
# (ex.: redis://host:6379) se escalar horizontalmente.
RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")


def internal_path(path: str) -> str:
    """Sanitiza um caminho para uso em redirect interno.

    Rejeita URLs absolutas e protocol-relative (`//evil.com`), que
    transformariam o redirect pós-login em open redirect.
    """
    path = (path or "").strip()
    if not path.startswith("/") or path.startswith("//"):
        return "/"
    return path

def money_type(precision: int = 14, scale: int = 2):
    """Tipo monetário: NUMERIC(precision, scale) em qualquer dialeto.

    Antes era `Float`. Somar centavos em binário acumula erro — o clássico
    `0.1 + 0.2 != 0.3` — e o resumo financeiro do usuário é exatamente uma soma
    longa de centavos. NUMERIC é exato no PostgreSQL e, no SQLite, o SQLAlchemy
    quantiza o valor lido para `scale` casas e devolve Decimal, então as somas em
    Python também ficam exatas.

    Custo conhecido no SQLite: o dialeto não tem Decimal nativo, então o
    SQLAlchemy converte float <-> Decimal e emite um SAWarning uma vez. Vale a
    troca — dinheiro errado é pior que log ruidoso.

    Nada aqui vaza para as rotas: `money()` abaixo normaliza Decimal e float para
    o mesmo resultado na borda JSON (jsonify não serializa Decimal).
    """
    return Numeric(precision, scale)


def quantity_type(precision: int = 20, scale: int = 8):
    """Tipo para quantidades e cotações — fração importa aqui.

    Diferente de `money_type()`: uma posição pode ser 0.00012345 BTC ou 0.375 de
    uma ação fracionada, e um token pode custar 0.0000012. Arredondar isso para 2
    casas (NUMERIC(14,2)) zeraria a posição. Por isso 8 casas decimais.
    """
    return Numeric(precision, scale)


def money(value, default: float = 0.0) -> float:
    """Converte um valor monetário do banco para float de 2 casas.

    `Numeric` devolve `Decimal` no PostgreSQL e `float` no SQLite; `jsonify` não
    serializa `Decimal` (seria 500 só em produção). Passar tudo por aqui torna os
    dois dialetos equivalentes na borda JSON.
    """
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(round(value, 2))
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return default


def meses_decorridos(inicio: date, hoje: date) -> int:
    """Meses completos entre duas datas (0 dentro do próprio mês de início)."""
    return (hoje.year - inicio.year) * 12 + (hoje.month - inicio.month)


def parcela_ativa(inicio, total_meses, hoje: date) -> bool:
    """Uma compra em N parcelas ainda pesa no orçamento?

    Só enquanto não termina. `total_meses <= 0` ou data ausente contam como
    encerrada — defensivo para linhas gravadas antes desta validação existir.
    """
    if not inicio or not total_meses or total_meses <= 0:
        return False
    return meses_decorridos(inicio, hoje) < total_meses


# CRITICAL: Defer engine creation to avoid module import failures
# If DB_URL is invalid/unreachable, this will cause gunicorn to timeout
# So we create it lazily inside create_app()
Base = declarative_base()
engine = None
SessionLocal = None

def get_engine():
    """Cria a engine uma única vez — e falha alto se o banco estiver mal configurado.

    Antes, qualquer exceção aqui caía num `sqlite:///:memory:` silencioso. O
    efeito era o pior possível: o app subia "verde", o health check passava, o
    usuário criava transações e **cada conexão nova começava um banco vazio** —
    os dados evaporavam sem nenhum erro no log. Em produção isso seria
    descoberto só depois de perder tudo.
    """
    global engine
    if engine is None:
        try:
            engine = create_engine(DB_URL, echo=False, future=True)
        except Exception as e:
            # Nunca logar DB_URL: a connection string carrega a senha do banco.
            logger.critical(
                "Falha ao configurar o banco de dados",
                extra={"error_code": "db_engine_failed", "exception": type(e).__name__},
            )
            raise RuntimeError(
                "Não foi possível configurar o banco de dados "
                f"({type(e).__name__}). Verifique GF_DB_URL/DATABASE_URL."
            ) from e
    return engine

def utcnow() -> datetime:
    """Único ponto que produz "agora" no aplicativo.

    Sempre em UTC. As colunas são `DateTime` sem timezone de propósito: no
    PostgreSQL (`TIMESTAMP`) e no SQLite o valor é gravado como wall-clock UTC e
    volta *naive*. Usar `DateTime(timezone=True)` faria o PostgreSQL devolver
    datetime com fuso e o SQLite sem — divergência de dialeto dentro do código.
    Regra: nunca comparar um datetime vindo do banco com um `now()` local.
    """
    return datetime.now(UTC)


def get_session_local():
    global SessionLocal
    if SessionLocal is None:
        SessionLocal = scoped_session(sessionmaker(bind=get_engine(), autoflush=False, autocommit=False))
    return SessionLocal


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index('idx_transaction_date', 'date'),
        Index('idx_transaction_type', 'type'),
        Index('idx_transaction_deleted_at', 'deleted_at'),
        Index('idx_transaction_user_date', 'user_id', 'date'),
    )
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    description = Column(String(255), nullable=False)
    amount = Column(money_type(), nullable=False)
    type = Column(String(16), nullable=False)  # income | expense
    date = Column(Date, nullable=False)
    deleted_at = Column(DateTime, nullable=True)  # Soft delete timestamp


class Installment(Base):
    __tablename__ = "installments"
    __table_args__ = (
        Index('idx_installment_date_added', 'date_added'),
        Index('idx_installment_deleted_at', 'deleted_at'),
        Index('idx_installment_user_date', 'user_id', 'date_added'),
    )
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    description = Column(String(255), nullable=False)
    monthly_value = Column(money_type(), nullable=False)
    total_months = Column(Integer, nullable=False)
    date_added = Column(Date, nullable=False)
    deleted_at = Column(DateTime, nullable=True)  # Soft delete timestamp


class Consent(Base):
    __tablename__ = "consents"
    __table_args__ = (
        Index('idx_consent_status', 'status'),
        Index('idx_consent_deleted_at', 'deleted_at'),
        Index('idx_consent_user_status', 'user_id', 'status'),
    )
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    consent_id = Column(String(128), unique=True, nullable=False)
    provider = Column(String(64), nullable=False)
    scopes = Column(String(512), nullable=False)
    status = Column(String(32), nullable=False)  # active | revoked | expired
    created_at = Column(DateTime, nullable=False)
    deleted_at = Column(DateTime, nullable=True)  # Soft delete timestamp


class Investment(Base):
    __tablename__ = "investments"
    __table_args__ = (
        Index('idx_investment_user_date', 'user_id', 'purchase_date'),
        Index('idx_investment_type', 'asset_type'),
        Index('idx_investment_deleted_at', 'deleted_at'),
    )
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    name = Column(String(256), nullable=False)  # ex: "Tesla", "Fundo Imobiliário"
    asset_type = Column(String(64), nullable=False)  # stocks, reit, crypto, bonds, funds, savings, real_estate, commodities
    amount = Column(quantity_type(), nullable=False)  # quantidade (frações valem)
    purchase_price = Column(quantity_type(), nullable=False)  # preço de compra/cotação
    current_price = Column(quantity_type(), nullable=True)  # preço atual
    purchase_date = Column(Date, nullable=False)
    target_return = Column(Float, nullable=True)  # % de retorno esperado
    status = Column(String(32), nullable=False, default='active')  # active | sold | matured
    notes = Column(String(1024), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    deleted_at = Column(DateTime, nullable=True)  # Soft delete timestamp


# ---------------------------------------------------------------------------
# Validação de entrada
# ---------------------------------------------------------------------------
# Os limites espelham as colunas do banco: NUMERIC(14,2) e String(n).
# Sem eles o SQLite aceitava qualquer coisa (uma description de 5.000 caracteres
# gravava sem erro) enquanto o PostgreSQL devolveria 500 — a mesma requisição
# funcionava ou não dependendo do dialeto. E dinheiro negativo ou zero passava no
# POST mas era rejeitado no PUT.
MAX_DINHEIRO = 999_999_999_999.99  # 12 dígitos inteiros + 2 casas

valor_positivo = validate.Range(
    min=0.01, max=MAX_DINHEIRO,
    error="Deve ser um valor positivo (mínimo 0.01).",
)
preco_nao_negativo = validate.Range(
    min=0, max=MAX_DINHEIRO,
    error="Não pode ser negativo.",
)
percentual = validate.Range(
    min=-100, max=10000,
    error="Percentual fora de um intervalo razoável.",
)
# Quantidade de um ativo: precisa aceitar frações (0.00012345 BTC, 0.375 de ação
# fracionada). O mínimo de 0.01 usado para dinheiro zeraria essas posições.
MAX_QUANTIDADE = 999_999_999_999.99999999  # NUMERIC(20,8)
quantidade_positiva = validate.Range(
    min=0.00000001, max=MAX_QUANTIDADE,
    error="Quantidade deve ser positiva.",
)


class ConsentSchema(Schema):
    id = fields.Int(dump_only=True)
    user_id = fields.Str(required=True, validate=validate.Length(min=1, max=64))
    consent_id = fields.Str(required=True, validate=validate.Length(min=4, max=128))
    provider = fields.Str(required=True, validate=validate.Length(min=2, max=64))
    scopes = fields.Str(required=True, validate=validate.Length(max=512))
    status = fields.Str(required=True, validate=validate.OneOf(["active", "revoked", "expired"]))
    created_at = fields.DateTime(dump_only=True)


class InvestmentSchema(Schema):
    id = fields.Int(dump_only=True)
    user_id = fields.Str(required=True, validate=validate.Length(min=1, max=64))
    name = fields.Str(required=True, validate=validate.Length(min=1, max=256))
    asset_type = fields.Str(required=True, validate=validate.OneOf(["stocks", "reit", "crypto", "bonds", "funds", "savings", "real_estate", "commodities"]))
    amount = fields.Float(required=True, validate=quantidade_positiva)
    purchase_price = fields.Float(required=True, validate=preco_nao_negativo)
    current_price = fields.Float(allow_none=True, validate=preco_nao_negativo)
    purchase_date = fields.Date(required=True)
    target_return = fields.Float(allow_none=True, validate=percentual)
    status = fields.Str(required=True, validate=validate.OneOf(["active", "sold", "matured"]))
    notes = fields.Str(allow_none=True, validate=validate.Length(max=1024))
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class TransactionSchema(Schema):
    id = fields.Int(dump_only=True)
    user_id = fields.Str(required=True, validate=validate.Length(min=1, max=64))
    description = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    amount = fields.Float(required=True, validate=valor_positivo)
    type = fields.Str(required=True, validate=validate.OneOf(["income", "expense"]))
    date = fields.Date(required=True)


class InstallmentSchema(Schema):
    id = fields.Int(dump_only=True)
    user_id = fields.Str(required=True, validate=validate.Length(min=1, max=64))
    description = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    monthly_value = fields.Float(required=True, validate=valor_positivo)
    total_months = fields.Int(required=True, validate=validate.Range(min=1, max=1200))
    date_added = fields.Date(required=True)


transaction_schema = TransactionSchema()
transactions_schema = TransactionSchema(many=True)
installment_schema = InstallmentSchema()
installments_schema = InstallmentSchema(many=True)
investment_schema = InvestmentSchema()
investments_schema = InvestmentSchema(many=True)
consent_schema = ConsentSchema()
consents_schema = ConsentSchema(many=True)


def create_app() -> Flask:
    # Arquivos estáticos servidos SOMENTE a partir de ./static.
    # Antes: static_folder='.' expunha pela web qualquer arquivo da raiz do
    # projeto (verificado: GET /backend.py, GET /.env e GET /.git/config
    # respondiam 200). Se houver frontend, coloque os arquivos em static/.
    app = Flask(__name__, static_url_path="/static", static_folder="static")
    app.secret_key = FLASK_SECRET_KEY

    if IS_PRODUCTION and not _SECRET_KEY_CONFIGURED:
        # Não derrubamos o app (isso quebraria deploys já existentes), mas o
        # aviso é crítico: sem SECRET_KEY fixa cada worker/instância/restart
        # gera uma chave nova e invalida todas as sessões.
        logger.critical(
            "SECRET_KEY/FLASK_SECRET_KEY não configurada em produção: sessões "
            "serão invalidadas a cada restart e divergirão entre workers",
            extra={"error_code": "secret_key_missing"},
        )

    # Proxy reverso (Azure App Service sempre coloca um na frente do gunicorn).
    # Precisa vir ANTES de qualquer coisa que use request.remote_addr / scheme.
    if TRUSTED_PROXY_COUNT > 0:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=TRUSTED_PROXY_COUNT,
            x_proto=TRUSTED_PROXY_COUNT,
            x_host=TRUSTED_PROXY_COUNT,
        )

    # CORS com credenciais: origens vêm de FRONTEND_ORIGINS
    CORS(app, supports_credentials=True, origins=FRONTEND_ORIGINS)

    # Rate limiting.
    # Antes: default_limits=["200 per day", "50 per hour"] valia para TODAS as
    # rotas — inclusive /api/health e cada arquivo estático. Verificado na main:
    # 55 chamadas seguidas ao health check já devolviam 429, o que faz o Azure
    # marcar a app como indisponível e um frontend que carrega N assets estourar
    # a cota do dia.
    # Agora: default folgado, rotas de infraestrutura isentas e limites rígidos
    # concentrados em autenticação e escrita.
    app.config["RATELIMIT_ENABLED"] = env_flag("RATELIMIT_ENABLED", "true")
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["500 per hour", "5000 per day"],
        storage_uri=RATELIMIT_STORAGE_URI,
    )
    # Assets estáticos não consomem cota de API: uma única página pode pedir
    # N arquivos e cada um contaria como requisição.
    limiter.exempt(app.view_functions["static"])

    # CSRF — política uniforme.
    # Regra: toda rota que muda estado (POST/PUT/PATCH/DELETE) exige o token
    # retornado por GET /api/csrf-token, enviado no header X-CSRFToken.
    # Únicas isenções (documentadas no próprio decorador):
    #   - /api/openfinance/webhook: chamado por serviço externo, autenticado por HMAC
    #   - /auth/dev-login: só existe fora de produção e o chamador ainda não tem sessão
    # GET/HEAD/OPTIONS nunca exigem token (WTF_CSRF_METHODS).
    app.config.update(
        # None = o token vive o mesmo tempo da sessão. O default de 3600s expirava
        # antes dos 120min de sessão e quebrava formulários deixados abertos.
        WTF_CSRF_TIME_LIMIT=None,
        # Default do Flask-WTF (True); exposto aqui para permitir desligar quando
        # houver cliente de API não-navegador (sem header Referer) em HTTPS.
        WTF_CSRF_SSL_STRICT=env_flag("WTF_CSRF_SSL_STRICT", "true"),
    )
    csrf = CSRFProtect(app)

    # Configuração de cookies/sessão (controlada por .env)
    # SESSION_COOKIE_SECURE assume "true" em produção (fail-closed): o Azure
    # serve HTTPS, então o cookie de sessão nunca deve trafegar em claro.
    app.config.update(
        SESSION_COOKIE_SECURE=env_flag("SESSION_COOKIE_SECURE", "true" if IS_PRODUCTION else "false"),
        SESSION_COOKIE_HTTPONLY=env_flag("SESSION_COOKIE_HTTPONLY", "true"),
        SESSION_COOKIE_SAMESITE=os.getenv("SESSION_COOKIE_SAMESITE", "Lax"),
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=int(os.getenv("SESSION_LIFETIME_MINUTES", "120")))
    )

    @app.before_request
    def _permanent_session():
        session.permanent = True

    # -------------------------------------------------------------------
    # Ciclo de vida da sessão de banco
    # -------------------------------------------------------------------
    @app.teardown_appcontext
    def shutdown_db_session(exception=None):
        """Devolve/encerra a sessão do scoped_session ao fim de CADA request.

        Sem isto (situação anterior), o scoped_session ficava preso à thread do
        worker sync e era reutilizado pelo request seguinte. Consequência
        reproduzida na main: um request que falhava no meio deixava objetos
        pendentes que o PRÓXIMO request commitava — um registro "órfão" de uma
        requisição abortada aparecia no banco junto com dados legítimos.
        Também não havia rollback, então qualquer erro de banco deixava a sessão
        em PendingRollbackError e quebrava todas as requisições seguintes da
        thread até o restart do worker.
        """
        if SessionLocal is None:
            return  # request não tocou no banco (ex.: estático, health)
        try:
            if exception is not None:
                SessionLocal.rollback()
        except Exception:  # rollback não pode mascarar o erro original
            logger.warning("Rollback da sessão no teardown falhou", exc_info=True,
                           extra={"error_code": "teardown_rollback_failed"})
        finally:
            # remove() é o que garante o essencial: fecha a sessão, descarta
            # objetos pendentes (add() ou setattr não commitados) e devolve a
            # conexão ao pool. Vale também para exceções tratadas por
            # errorhandler — nesse caso o Flask chama o teardown com None.
            SessionLocal.remove()

    # Endpoint para obter CSRF token (para chamadas AJAX)
    @app.route('/api/csrf-token', methods=['GET'])
    @limiter.exempt  # chamado no carregamento de toda página
    def get_csrf_token():
        """Retorna o token CSRF que o cliente deve enviar no header X-CSRFToken.

        Antes lia `session['_csrf_token']`, chave que o Flask-WTF nunca grava
        (a correta é `csrf_token`, de WTF_CSRF_FIELD_NAME) e jamais chamava
        generate_csrf() — o endpoint devolvia sempre "N/A" e nenhuma rota de
        escrita conseguia ser usada (PUT/DELETE de transações e todo o CRUD de
        parcelas respondiam 400 "The CSRF token is missing.").
        """
        return jsonify({
            "csrf_token": generate_csrf(),
            "header_name": "X-CSRFToken",
        }), 200

    # Cria as tabelas se não existirem.
    #
    # Rede de segurança, não o mecanismo principal: o `startup.txt` roda
    # `alembic upgrade head` antes do gunicorn, mas o portal do Azure permite
    # sobrescrever o comando de inicialização — sem isto, um deploy com o comando
    # errado não criaria tabela alguma.
    #
    # O que mudou na Fase 3: a exceção NÃO é mais engolida. O `except` anterior
    # registrava "Failed to create database tables" e seguia em frente ("App will
    # still start, just without database"). Na prática: o health check passava, o
    # Azure trocava o slot e TODO request devolvia 500 — uma falha total de
    # serviço anunciada como deploy bem-sucedido. Sem banco o aplicativo não serve
    # para nada, então o boot falha e o deploy é rejeitado.
    db_engine = get_engine()
    try:
        Base.metadata.create_all(db_engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        # Nunca logar a connection string: ela carrega a senha do banco.
        logger.critical(
            "Falha ao preparar o esquema do banco",
            extra={"error_code": "db_schema_failed", "exception": type(e).__name__},
        )
        raise RuntimeError(
            "Não foi possível preparar o esquema do banco de dados "
            f"({type(e).__name__}). Verifique GF_DB_URL/DATABASE_URL."
        ) from e
    
    # Configurar OAuth
    oauth = OAuth(app)
    if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
        google = oauth.register(
            name='google',
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'}
        )
    else:
        google = None

    # Inicializa provider Open Finance
    # Se credenciais reais configuradas, usa OpenFinanceProvider; senão, usa simulado
    use_real_openfinance = os.getenv("OPENFINANCE_ENABLE_REAL", "false").lower() == "true"
    
    if use_real_openfinance:
        provider = OpenFinanceProvider(
            base_url=os.getenv("OPENFINANCE_BASE_URL"),
            client_id=os.getenv("OPENFINANCE_CLIENT_ID"),
            client_secret=os.getenv("OPENFINANCE_CLIENT_SECRET"),
            certificate_path=os.getenv("OPENFINANCE_CERT_PATH"),
            private_key_path=os.getenv("OPENFINANCE_KEY_PATH")
        )
        logger.info("Open Finance real provider inicializado")
    else:
        provider = SimulatedProvider()
        logger.info("Open Finance simulated provider inicializado (modo desenvolvimento)")

    # -------------------------------------------------------------------
    # Utilitários
    # -------------------------------------------------------------------
    def get_session():
        session_factory = get_session_local()
        if session_factory is None:
            raise RuntimeError("Database session not initialized")
        return session_factory()

    def parse_json(schema: Schema, payload: dict, partial: bool = False):
        try:
            return schema.load(payload, partial=partial)
        except ValidationError as err:
            raise BadRequest(err.messages)

    def apply_update(obj, schema: Schema, payload: dict, campos: tuple):
        """Valida um payload parcial com o MESMO schema do POST e aplica só o permitido.

        Substitui os blocos `for field in [...]` com `try/except` que cada PUT
        tinha. As regras viviam em dois lugares e divergiam: o POST aceitava
        `amount <= 0` e o PUT rejeitava; `description` sem limite de tamanho num
        e com `strptime` manual no outro. Agora a fonte de verdade é o schema.

        Dois detalhes de segurança/robustez:
        - `campos` é uma whitelist. `user_id` fica de fora de propósito: sem isso,
          enviar o campo no body transferiria o registro para outra conta.
        - campo desconhecido vira 400 (default do Marshmallow é `unknown=RAISE`).
          Antes era ignorado em silêncio — o formulário de edição de investimento
          mandava `asset_type`, `amount`, `purchase_price` e `purchase_date`, o
          PUT descartava os quatro e respondia 200 como se tivesse salvado.
        """
        dados = parse_json(schema, payload, partial=True)
        for campo in campos:
            if campo in dados:
                setattr(obj, campo, dados[campo])
        return dados

    def today_date() -> date:
        return date.today()

    def paginate_query(query, page: int = 1, per_page: int = 20):
        """
        Pagina resultado de query SQLAlchemy.
        
        Args:
            query: Query SQLAlchemy
            page: Número da página (1-indexed)
            per_page: Itens por página (máx 100)
        
        Returns:
            {
                "items": [...],
                "total": 150,
                "pages": 8,
                "current_page": 1,
                "per_page": 20
            }
        """
        # Validar e limitar per_page
        try:
            page = max(1, int(page))
            per_page = max(1, min(100, int(per_page)))  # Max 100 itens por página
        except (ValueError, TypeError):
            page = 1
            per_page = 20
        
        # Executar query e contar total
        items = query.offset((page - 1) * per_page).limit(per_page).all()
        total = query.count()
        
        # Calcular total de páginas
        pages = (total + per_page - 1) // per_page
        
        return {
            "items": items,
            "total": total,
            "pages": pages,
            "current_page": page,
            "per_page": per_page
        }

    def require_auth(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Em testes, não exigir autenticação
            if app.config.get('TESTING'):
                return fn(*args, **kwargs)
            user = session.get('user')
            if not user:
                return jsonify({"error": "unauthorized", "details": "Não autenticado"}), 401
            # Se a rota tem user_id, ele deve coincidir com o id do usuário logado
            requested_user = kwargs.get('user_id')
            if requested_user and requested_user != user.get('id'):
                return jsonify({"error": "forbidden", "details": "User ID não corresponde ao usuário autenticado"}), 403
            return fn(*args, **kwargs)
        return wrapper

    # -------------------------------------------------------------------
    # Exceções customizadas
    # -------------------------------------------------------------------
    class BadRequest(Exception):
        def __init__(self, messages):
            self.messages = messages

    class NotFound(Exception):
        def __init__(self, message: str):
            self.message = message

    @app.errorhandler(BadRequest)
    def handle_bad_request(e: BadRequest) -> tuple:
        return jsonify({"error": "bad_request", "details": e.messages}), 400

    @app.errorhandler(NotFound)
    def handle_not_found(e: NotFound) -> tuple:
        return jsonify({"error": "not_found", "details": e.message}), 404

    from werkzeug.exceptions import HTTPException

    @app.errorhandler(ValidationError)
    def handle_validation_error(e: ValidationError) -> tuple:
        """Marshmallow ValidationError fora de `parse_json` -> 400.

        Antes escapava como 500 `internal_error` com as mensagens internas do
        schema no corpo da resposta (ex.: POST /openfinance/consents).
        """
        return jsonify({"error": "bad_request", "details": e.messages}), 400

    @app.errorhandler(Exception)
    def handle_generic(e: Exception) -> tuple:
        # Evita transformar 404/405 etc em 500
        if isinstance(e, HTTPException):
            return jsonify({"error": e.name.lower().replace(' ', '_'), "details": e.description}), e.code
        # Nunca devolver `str(e)` ao cliente: mensagens de driver de banco,
        # strings de conexão e detalhes de configuração vazavam na resposta.
        # O detalhe vai para o log, correlacionado por `error_id`.
        error_id = secrets.token_hex(8)
        try:
            context = {
                "endpoint": request.path,
                "method": request.method,
                "user_id": (session.get("user") or {}).get("id"),
            }
        except Exception:  # fora de um request context
            context = {}
        logger.error(
            "Erro interno não tratado",
            exc_info=e,
            extra={**context, "error_code": error_id},
        )
        return jsonify({
            "error": "internal_error",
            "details": "Erro interno do servidor.",
            "error_id": error_id,
        }), 500

    # -------------------------------------------------------------------
    # Health
    # -------------------------------------------------------------------
    @app.route("/api/health")
    @limiter.exempt  # health probe do Azure: não pode consumir cota nem levar 429
    def health():
        return jsonify({"status": "ok"})

    @app.route("/")
    @require_auth
    @limiter.exempt  # descoberta da API / probe de raiz
    def root():
        return jsonify({"message": "Gestor Financeiro API", "health": "/api/health"}), 200

    # -------------------------------------------------------------------
    # Autenticação Google OAuth
    # -------------------------------------------------------------------
    @app.route("/auth/login")
    @limiter.limit("5 per minute")  # CRITICAL: Protege contra brute force
    def login():
        """Inicia fluxo de login com Google."""
        logger.info("Login iniciado", extra={"endpoint": "/auth/login", "method": "GET"})
        if not google:
            logger.error("OAuth não configurado", extra={"endpoint": "/auth/login", "error_code": "oauth_config_missing"})
            return jsonify({"error": "OAuth não configurado. Configure GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET."}), 500
        redirect_uri = url_for('auth_callback', _external=True)
        return google.authorize_redirect(redirect_uri)

    @app.route("/auth/callback")
    @limiter.limit("10 per minute")  # protege o callback contra tentativas em força bruta
    def auth_callback():
        """Callback do Google OAuth."""
        if not google:
            logger.error("OAuth não configurado no callback", extra={"endpoint": "/auth/callback", "error_code": "oauth_config_missing"})
            return jsonify({"error": "OAuth não configurado"}), 500
        try:
            token = google.authorize_access_token()
            user_info = token.get('userinfo')
            if user_info:
                user_id = user_info.get('sub')
                session['user'] = {
                    'id': user_id,
                    'email': user_info.get('email'),
                    'name': user_info.get('name'),
                    'picture': user_info.get('picture')
                }
                logger.info("Login bem-sucedido", extra={"user_id": user_id, "endpoint": "/auth/callback", "method": "GET"})
                # Redirect pós-login.
                # Antes: URL absoluta hardcoded para o frontend em localhost,
                # apontando para um index_api.html que nem existe no repositório
                # — no Azure jogava o usuário para a própria máquina. Agora a
                # base vem de APP_BASE_URL (ou do próprio request, que sai
                # correto graças ao ProxyFix) e o caminho é sanitizado contra
                # open redirect.
                base = APP_BASE_URL or request.url_root.rstrip("/")
                return redirect(f"{base}{internal_path(POST_LOGIN_PATH)}?logged=true")
            logger.warning("Informações de usuário não obtidas", extra={"endpoint": "/auth/callback", "error_code": "no_user_info"})
            return jsonify({"error": "Falha ao obter informações do usuário"}), 400
        except Exception as e:
            # Detalhe só no log: `str(e)` do Authlib expunha state/nonce e
            # erros internos do fluxo OAuth ao cliente.
            logger.error(
                "Erro no callback OAuth",
                exc_info=e,
                extra={"endpoint": "/auth/callback", "method": "GET", "error_code": "oauth_error"},
            )
            return jsonify({
                "error": "oauth_callback_failed",
                "details": "Não foi possível concluir o login com o Google.",
            }), 400

    @app.route("/auth/logout")
    def logout():
        """Encerra sessão do usuário."""
        user_id = session.get('user', {}).get('id')
        session.pop('user', None)
        logger.info("Logout realizado", extra={"user_id": user_id, "endpoint": "/auth/logout", "method": "GET"})
        return jsonify({"message": "Logout realizado"}), 200

    @app.route("/auth/dev-login", methods=['POST'])
    @csrf.exempt  # isenção documentada: existe só fora de produção e o chamador ainda não tem sessão/token
    @limiter.limit("5 per minute")  # é um endpoint de login: limita tentativa em força bruta
    def dev_login():
        """
        Endpoint de login para desenvolvimento (SEM OAuth).
        POST /auth/dev-login
        Body: {"user_id": "test_user", "email": "test@example.com", "name": "Test User"}

        SEGURANÇA: desativado por padrão. Só responde quando
        `ENABLE_DEV_LOGIN=true` E o ambiente não é produção
        (`APP_ENV != production` e sem `WEBSITE_SITE_NAME`). Em testes
        (`app.config['TESTING']`) também é liberado.

        Antes a condição era `not OPENFINANCE_ENABLE_REAL`, cujo default é
        false — ou seja, a porta dos fundos ficava aberta em produção e
        permitia a qualquer pessoa assumir a sessão de um `user_id` arbitrário
        (inclusive o `sub` do Google de um usuário real) e ler/alterar os dados
        financeiros dele.
        """
        if not (app.config.get('TESTING') or DEV_LOGIN_ENABLED):
            logger.warning(
                "Tentativa de dev-login com o recurso desativado",
                extra={
                    "endpoint": "/auth/dev-login",
                    "method": "POST",
                    "error_code": "dev_login_disabled",
                },
            )
            return jsonify({
                "error": "dev_login_disabled",
                "details": "Login de desenvolvimento desativado. "
                           "Defina ENABLE_DEV_LOGIN=true apenas em ambiente local.",
            }), 403

        data = request.get_json(silent=True) or {}
        # Limita tamanho dos campos para não gravar lixo arbitrário na sessão.
        user_id = str(data.get('user_id') or 'test_user').strip()[:64] or 'test_user'
        email = str(data.get('email') or f'{user_id}@example.com').strip()[:254]
        name = str(data.get('name') or 'Test User').strip()[:120]

        session['user'] = {
            'id': user_id,
            'email': email,
            'name': name,
            'picture': None
        }
        logger.info(
            "Dev login realizado",
            extra={"user_id": user_id, "endpoint": "/auth/dev-login", "method": "POST"},
        )
        return jsonify({
            "message": "Login de desenvolvimento bem-sucedido",
            "user": session['user']
        }), 200

    @app.route("/auth/me")
    def get_current_user():
        """Retorna usuário autenticado atual."""
        user = session.get('user')
        if user:
            # Incluir alias user_id para o frontend
            out = dict(user)
            out['user_id'] = out.get('id')
            return jsonify(out), 200
        return jsonify({"error": "Não autenticado"}), 401

    # -------------------------------------------------------------------
    # Consents Open Finance (simulado)
    # -------------------------------------------------------------------
    @app.route("/api/users/<user_id>/openfinance/consents", methods=["POST"])
    @require_auth
    @limiter.limit("20 per hour")  # IMPORTANT: Limita criação de consents
    def create_consent(user_id: str):
        payload = request.get_json(silent=True) or {}
        if not payload.get('consent_id'):
            payload['consent_id'] = secrets.token_hex(8)
        if not payload.get('provider'):
            payload['provider'] = 'simulated'
        if not payload.get('scopes'):
            payload['scopes'] = 'accounts:read transactions:read'
        if not payload.get('status'):
            payload['status'] = 'active'
        payload['user_id'] = user_id
        # parse_json (e não schema.load direto): ValidationError vira 400
        # padronizado. E o objeto é montado a partir do resultado VALIDADO,
        # não do payload cru — antes a validação era descartada.
        data = parse_json(consent_schema, payload)
        session_db = get_session()
        obj = Consent(
            user_id=data['user_id'],
            consent_id=data['consent_id'],
            provider=data['provider'],
            scopes=data['scopes'],
            status=data['status'],
            created_at=utcnow()
        )
        session_db.add(obj)
        session_db.commit()
        return jsonify(consent_schema.dump(obj)), 201

    @app.route("/api/users/<user_id>/openfinance/consents", methods=["GET"])
    @require_auth
    def list_consents(user_id: str):
        session_db = get_session()
        query = session_db.query(Consent).filter(
            Consent.user_id == user_id,
            Consent.deleted_at.is_(None)
        ).order_by(Consent.created_at.desc())
        
        # Parâmetros de paginação
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Paginar
        paginated = paginate_query(query, page, per_page)
        
        # Retornar com metadados de paginação
        return jsonify({
            "items": consents_schema.dump(paginated["items"]),
            "pagination": {
                "current_page": paginated["current_page"],
                "per_page": paginated["per_page"],
                "total": paginated["total"],
                "pages": paginated["pages"]
            }
        })

    # -------------------------------------------------------------------
    # Transactions CRUD
    # -------------------------------------------------------------------
    @app.route("/api/users/<user_id>/transactions", methods=["GET"])
    @require_auth
    def list_transactions(user_id: str):
        # Query base - filtrar apenas registros não deletados
        session_db = get_session()
        query = session_db.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None)
        ).order_by(Transaction.date.desc())
        
        # Parâmetros de paginação
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Paginar
        paginated = paginate_query(query, page, per_page)
        
        # Retornar com metadados de paginação
        return jsonify({
            "items": transactions_schema.dump(paginated["items"]),
            "pagination": {
                "current_page": paginated["current_page"],
                "per_page": paginated["per_page"],
                "total": paginated["total"],
                "pages": paginated["pages"]
            }
        })

    @app.route("/api/users/<user_id>/transactions", methods=["POST"])
    @require_auth
    @limiter.limit("100 per hour")  # IMPORTANT: Limita criação de transações
    def create_transaction(user_id: str):
        payload = request.get_json(silent=True) or {}
        payload["user_id"] = user_id
        if "date" not in payload:
            payload["date"] = today_date().isoformat()
        # Usa o resultado VALIDADO: antes o objeto era montado a partir do
        # payload cru, jogando fora a coerção do Marshmallow e duplicando o
        # parse de data com um strptime manual.
        data = parse_json(transaction_schema, payload)
        session_db = get_session()
        txn = Transaction(
            user_id=data['user_id'],
            description=data['description'],
            amount=data['amount'],
            type=data['type'],
            date=data['date'],  # fields.Date já devolve datetime.date
        )
        session_db.add(txn)
        session_db.commit()
        return jsonify(transaction_schema.dump(txn)), 201

    @app.route("/api/users/<user_id>/transactions/<int:txn_id>", methods=["PUT", "PATCH"])
    @require_auth
    @limiter.limit("100 per hour")  # IMPORTANT: Limita atualizações
    def update_transaction(user_id: str, txn_id: int):
        payload = request.get_json(silent=True) or {}
        session_db = get_session()
        txn: Optional[Transaction] = session_db.query(Transaction).filter(
            Transaction.id == txn_id,
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None)
        ).first()
        if not txn:
            raise NotFound("Transação não encontrada")
        # Mesmas regras do POST (schema) e só estes campos são editáveis.
        apply_update(txn, transaction_schema, payload,
                     ("description", "amount", "type", "date"))
        session_db.commit()
        return jsonify(transaction_schema.dump(txn))

    @app.route("/api/users/<user_id>/transactions/<int:txn_id>", methods=["DELETE"])
    @require_auth
    @limiter.limit("100 per hour")  # IMPORTANT: Limita exclusões
    def delete_transaction(user_id: str, txn_id: int):
        session_db = get_session()
        txn = session_db.query(Transaction).filter(
            Transaction.id == txn_id,
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None)
        ).first()
        if not txn:
            raise NotFound("Transação não encontrada")
        # Soft delete: set deleted_at timestamp
        txn.deleted_at = utcnow()
        session_db.commit()
        return jsonify({"deleted": txn_id})

    # -------------------------------------------------------------------
    # Sugestões Financeiras
    # -------------------------------------------------------------------
    @app.route("/api/users/<user_id>/suggestions", methods=["GET"])
    @require_auth
    @limiter.limit("50 per hour")
    def get_suggestions(user_id: str):
        """
        Retorna sugestões personalizadas baseadas no histórico financeiro do usuário.
        Analisa padrões de gastos e oferece recomendações de economia.
        """
        session_db = get_session()
        
        # Buscar transações dos últimos 30 dias.
        # Projeção de colunas: a análise usa só tipo, descrição e valor. Carregar o
        # objeto ORM inteiro traz o resto das colunas de cada linha sem necessidade.
        thirty_days_ago = today_date() - timedelta(days=30)
        recent_txns = session_db.query(
            Transaction.type, Transaction.description, Transaction.amount
        ).filter(
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None),
            Transaction.date >= thirty_days_ago
        ).all()
        
        suggestions = []
        
        if not recent_txns:
            suggestions.append({
                "type": "info",
                "category": "getting_started",
                "title": "Comece a registrar suas transações",
                "description": "Adicione suas receitas e despesas para receber sugestões personalizadas",
                "priority": "high",
                "icon": "📊"
            })
            return jsonify({"suggestions": suggestions})
        
        # Calcular estatísticas. money() normaliza Decimal (PostgreSQL) e float
        # (SQLite) para a mesma coisa na borda JSON.
        total_income = money(sum(a for t, _, a in recent_txns if t == "income"))
        total_expense = money(sum(a for t, _, a in recent_txns if t == "expense"))
        balance = money(total_income - total_expense)
        
        # Análise por descrição (categorias informais)
        expense_categories = {}
        for tipo, descricao, valor in recent_txns:
            if tipo == "expense":
                desc = (descricao or "").lower()
                # Categorizar por palavras-chave
                if any(word in desc for word in ['restaurante', 'ifood', 'uber eats', 'almoço', 'jantar', 'lanche']):
                    category = 'alimentacao'
                elif any(word in desc for word in ['uber', 'taxi', '99', 'gasolina', 'combustível']):
                    category = 'transporte'
                elif any(word in desc for word in ['netflix', 'spotify', 'amazon', 'assinatura', 'streaming']):
                    category = 'assinaturas'
                elif any(word in desc for word in ['supermercado', 'mercado', 'compras']):
                    category = 'supermercado'
                elif any(word in desc for word in ['energia', 'água', 'internet', 'celular', 'conta']):
                    category = 'contas'
                else:
                    category = 'outros'
                
                expense_categories[category] = (
                    expense_categories.get(category, 0.0) + float(valor or 0)
                )
        
        # SUGESTÃO 1: Saldo negativo
        if balance < 0:
            suggestions.append({
                "type": "alert",
                "category": "budget",
                "title": "Gastos acima das receitas",
                "description": f"Você gastou R$ {abs(balance):.2f} a mais do que recebeu nos últimos 30 dias. Considere revisar seus gastos.",
                "priority": "high",
                "icon": "⚠️",
                "action": {
                    "label": "Ver despesas",
                    "endpoint": f"/api/users/{user_id}/transactions?type=expense"
                }
            })
        
        # SUGESTÃO 2: Gastos com alimentação elevados
        if 'alimentacao' in expense_categories:
            food_expense = expense_categories['alimentacao']
            if total_income > 0:
                food_percentage = (food_expense / total_income) * 100
                if food_percentage > 30:
                    suggestions.append({
                        "type": "tip",
                        "category": "savings",
                        "title": "Gastos com alimentação elevados",
                        "description": f"Você gastou R$ {food_expense:.2f} ({food_percentage:.1f}% da sua receita) com alimentação. Considere cozinhar mais em casa.",
                        "priority": "medium",
                        "icon": "🍔",
                        "potential_savings": food_expense * 0.3  # Economia de 30%
                    })
        
        # SUGESTÃO 3: Muitas assinaturas
        if 'assinaturas' in expense_categories:
            subscription_expense = expense_categories['assinaturas']
            suggestions.append({
                "type": "tip",
                "category": "subscriptions",
                "title": "Revise suas assinaturas",
                "description": f"Você tem R$ {subscription_expense:.2f} em assinaturas. Cancele serviços que não usa.",
                "priority": "low",
                "icon": "📺",
                "potential_savings": subscription_expense * 0.5
            })
        
        # SUGESTÃO 4: Gastos com transporte
        if 'transporte' in expense_categories:
            transport_expense = expense_categories['transporte']
            if transport_expense > 500:
                suggestions.append({
                    "type": "tip",
                    "category": "transport",
                    "title": "Considere alternativas de transporte",
                    "description": f"Você gastou R$ {transport_expense:.2f} com transporte. Avalie transporte público ou carona compartilhada.",
                    "priority": "medium",
                    "icon": "🚗"
                })
        
        # SUGESTÃO 5: Poucas receitas
        if len([t for t in recent_txns if t.type == "income"]) < 2:
            suggestions.append({
                "type": "info",
                "category": "income",
                "title": "Diversifique suas fontes de renda",
                "description": "Considere buscar fontes alternativas de renda como freelancing ou investimentos.",
                "priority": "low",
                "icon": "💰"
            })
        
        # SUGESTÃO 6: Meta de economia (Regra 50-30-20)
        if total_income > 0:
            recommended_savings = total_income * 0.20  # 20% da receita
            actual_savings = balance
            if actual_savings < recommended_savings:
                suggestions.append({
                    "type": "goal",
                    "category": "savings",
                    "title": "Meta de economia mensal",
                    "description": f"Tente economizar 20% da sua receita (R$ {recommended_savings:.2f}). Você está economizando R$ {actual_savings:.2f}.",
                    "priority": "medium",
                    "icon": "🎯",
                    "progress": (actual_savings / recommended_savings * 100) if recommended_savings > 0 else 0
                })
        
        # SUGESTÃO 7: Categoria com maior gasto
        if expense_categories:
            max_category = max(expense_categories.items(), key=lambda x: x[1])
            category_name_map = {
                'alimentacao': 'Alimentação',
                'transporte': 'Transporte',
                'assinaturas': 'Assinaturas',
                'supermercado': 'Supermercado',
                'contas': 'Contas Fixas',
                'outros': 'Outros'
            }
            suggestions.append({
                "type": "insight",
                "category": "spending_pattern",
                "title": f"Maior gasto: {category_name_map.get(max_category[0], 'Outros')}",
                "description": f"Sua categoria com mais gastos é {category_name_map.get(max_category[0], 'Outros')}: R$ {max_category[1]:.2f}",
                "priority": "low",
                "icon": "📈"
            })
        
        # Ordenar por prioridade
        priority_order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 2))
        
        
        return jsonify({
            "suggestions": suggestions,
            "period": {
                "start": thirty_days_ago.isoformat(),
                "end": today_date().isoformat(),
                "days": 30
            },
            "summary": {
                "total_income": round(total_income, 2),
                "total_expense": round(total_expense, 2),
                "balance": round(balance, 2),
                "transactions_count": len(recent_txns)
            }
        })

    # -------------------------------------------------------------------
    # Installments CRUD
    # -------------------------------------------------------------------
    @app.route("/api/users/<user_id>/installments", methods=["GET"])
    @require_auth
    def list_installments(user_id: str):
        session_db = get_session()
        query = session_db.query(Installment).filter(
            Installment.user_id == user_id,
            Installment.deleted_at.is_(None)
        ).order_by(Installment.date_added.desc())
        
        # Parâmetros de paginação
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Paginar
        paginated = paginate_query(query, page, per_page)
        
        # Retornar com metadados de paginação
        return jsonify({
            "items": installments_schema.dump(paginated["items"]),
            "pagination": {
                "current_page": paginated["current_page"],
                "per_page": paginated["per_page"],
                "total": paginated["total"],
                "pages": paginated["pages"]
            }
        })

    @app.route("/api/users/<user_id>/installments", methods=["POST"])
    @require_auth
    @limiter.limit("100 per hour")  # IMPORTANT: Limita criação de parcelas
    def create_installment(user_id: str):
        payload = request.get_json(silent=True) or {}
        payload["user_id"] = user_id
        if "date_added" not in payload:
            payload["date_added"] = today_date().isoformat()
        data = parse_json(installment_schema, payload)
        session_db = get_session()
        inst = Installment(**data)
        session_db.add(inst)
        session_db.commit()
        return jsonify(installment_schema.dump(inst)), 201

    @app.route("/api/users/<user_id>/installments/<int:inst_id>", methods=["PUT", "PATCH"])
    @require_auth
    @limiter.limit("100 per hour")  # IMPORTANT: Limita atualizações de parcelas
    def update_installment(user_id: str, inst_id: int):
        payload = request.get_json(silent=True) or {}
        session_db = get_session()
        inst: Optional[Installment] = session_db.query(Installment).filter(
            Installment.id == inst_id,
            Installment.user_id == user_id,
            Installment.deleted_at.is_(None)
        ).first()
        if not inst:
            raise NotFound("Parcela não encontrada")
        # Mesmas regras do POST (schema) e só estes campos são editáveis.
        apply_update(inst, installment_schema, payload,
                     ("description", "monthly_value", "total_months", "date_added"))
        session_db.commit()
        return jsonify(installment_schema.dump(inst))

    @app.route("/api/users/<user_id>/installments/<int:inst_id>", methods=["DELETE"])
    @require_auth
    @limiter.limit("100 per hour")  # IMPORTANT: Limita exclusões de parcelas
    def delete_installment(user_id: str, inst_id: int):
        session_db = get_session()
        inst = session_db.query(Installment).filter(
            Installment.id == inst_id,
            Installment.user_id == user_id,
            Installment.deleted_at.is_(None)
        ).first()
        if not inst:
            raise NotFound("Parcela não encontrada")
        # Soft delete: set deleted_at timestamp
        inst.deleted_at = utcnow()
        session_db.commit()
        return jsonify({"deleted": inst_id})

    # -------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------
    @app.route("/api/users/<user_id>/summary", methods=["GET"])
    @require_auth
    def summary(user_id: str):
        session_db = get_session()

        # Somas feitas no banco (SUM + GROUP BY) em vez de carregar todas as
        # linhas e somar em Python: o custo deixa de crescer com o histórico.
        por_tipo = dict(
            session_db.query(
                Transaction.type,
                func.coalesce(func.sum(Transaction.amount), 0),
            ).filter(
                Transaction.user_id == user_id,
                Transaction.deleted_at.is_(None),
            ).group_by(Transaction.type).all()
        )
        income = money(por_tipo.get("income"))
        expenses_avulsa = money(por_tipo.get("expense"))

        # Parcelas: só as que AINDA estão sendo pagas. Antes o resumo somava todas
        # as parcelas cadastradas para sempre — uma compra em 12x feita há três
        # anos continuava pesando no orçamento do mês.
        # A aritmética de meses é por linha (cada compra tem sua data de início) e
        # não é portável entre SQLite e PostgreSQL, então projetamos só as três
        # colunas necessárias e filtramos aqui, sem carregar objeto ORM inteiro.
        hoje = today_date()
        parcelas = session_db.query(
            Installment.monthly_value,
            Installment.date_added,
            Installment.total_months,
        ).filter(
            Installment.user_id == user_id,
            Installment.deleted_at.is_(None),
        ).all()
        ativas = [
            mv for mv, inicio, total in parcelas if parcela_ativa(inicio, total, hoje)
        ]
        expenses_parcelas = money(sum(ativas)) if ativas else 0.0

        expenses_total = money(expenses_avulsa + expenses_parcelas)
        balance = money(income - expenses_total)
        return jsonify({
            "income": income,
            "expenses_avulsa": expenses_avulsa,
            "expenses_parcelas": expenses_parcelas,
            "expenses_total": expenses_total,
            "balance": balance,
            "parcelas_ativas": len(ativas),
            "parcelas_encerradas": len(parcelas) - len(ativas),
        })

    # -------------------------------------------------------------------
    # Importação simulada (Open Finance)
    # -------------------------------------------------------------------
    @app.route("/api/users/<user_id>/import", methods=["POST"])
    @require_auth
    @limiter.limit("20 per hour")  # IMPORTANT: Limita importações
    def import_data(user_id: str):
        session_db = get_session()
        hoje_str = today_date().isoformat()
        simulated = [
            {"description": "Transferência Recebida (Freelancer)", "amount": 1500.00, "type": "income", "date": hoje_str},
            {"description": "Restaurante - Almoço", "amount": 45.50, "type": "expense", "date": hoje_str},
            {"description": "Assinatura Netflix", "amount": 39.90, "type": "expense", "date": hoje_str},
        ]
        created = []
        for item in simulated:
            data = parse_json(transaction_schema, {**item, "user_id": user_id})
            txn = Transaction(**data)
            session_db.add(txn)
            created.append(txn)
        session_db.commit()
        return jsonify({
            "status": "success",
            "imported": len(created),
            "transactions": transactions_schema.dump(created)
        })

    # -------------------------------------------------------------------
    # Open Finance Sync (simulado)
    # -------------------------------------------------------------------
    @app.route("/api/users/<user_id>/openfinance/sync", methods=["POST"])
    @require_auth
    @limiter.limit("10 per hour")  # IMPORTANT: Limita sync para economizar banda
    def open_finance_sync(user_id: str):
        """Sincroniza transações via Open Finance."""
        start_time = time.time()
        session_db = get_session()
        
        # Validar consent ativo
        active_consent = session_db.query(Consent).filter(
            Consent.user_id == user_id,
            Consent.status == 'active',
            Consent.deleted_at.is_(None)
        ).first()
        
        if not active_consent:
            logger.warning("Tentativa de sync sem consent ativo", extra={"user_id": user_id, "endpoint": "/openfinance/sync", "error_code": "no_active_consent"})
            return jsonify({"error": "no_active_consent", "details": "Nenhum consent ativo encontrado para este usuário."}), 400
        
        logger.info("Sincronização Open Finance iniciada", extra={"user_id": user_id, "endpoint": "/openfinance/sync", "consent_id": active_consent.consent_id})
        
        # Usa provider para sincronizar
        # Provider real requer consent_id; provider simulado ignora
        try:
            if isinstance(provider, OpenFinanceProvider):
                result = provider.sync(local_user_id=user_id, consent_id=active_consent.consent_id)
            else:
                # SimulatedProvider usa assinatura antiga (sem consent_id)
                result = provider.sync(local_user_id=user_id)
        except Exception as e:
            logger.error(
                "Erro na sincronização Open Finance",
                exc_info=e,
                extra={"user_id": user_id, "endpoint": "/openfinance/sync", "error_code": "sync_failed"},
            )
            # `str(e)` vazava configuração interna do provider
            # (ex.: "Configurações faltantes: OPENFINANCE_CLIENT_SECRET").
            return jsonify({
                "error": "sync_failed",
                "details": "Falha na sincronização com o Open Finance.",
            }), 500
        
        inserted = []
        skipped = 0
        invalidos = 0

        def fingerprint(data_, tipo, valor, descricao) -> Optional[str]:
            """Assinatura estável de uma transação, ou None se faltar dado essencial.

            Antes era `f"{d['date']}|{d['type']}|{d['amount']:.2f}|..."` com índice
            direto: um provider que omitisse qualquer um dos campos derrubava o
            endpoint inteiro com KeyError (500), e um `amount` que não fosse número
            estourava no format. Agora nada aqui lança — o item inválido é pulado.
            """
            if isinstance(data_, datetime):
                dia = data_.date().isoformat()
            elif isinstance(data_, date):
                dia = data_.isoformat()
            else:
                dia = str(data_ or "").strip()[:10]
            if not dia or not tipo:
                return None
            return (
                f"{dia}|{str(tipo).strip().lower()}|"
                f"{money(valor):.2f}|{str(descricao or '').strip().lower()}"
            )

        # Deduplicação contra TUDO que o usuário já tem, inclusive linhas com soft
        # delete. O filtro `deleted_at IS NULL` que estava aqui fazia o oposto do
        # esperado: apagar uma transação importada a trazia de volta no sync
        # seguinte, já que ela deixava de constar entre as existentes.
        existentes = session_db.query(
            Transaction.date, Transaction.type,
            Transaction.amount, Transaction.description,
        ).filter(Transaction.user_id == user_id).all()
        existing_fp = set()
        for linha in existentes:
            fp = fingerprint(*linha)
            if fp:
                existing_fp.add(fp)

        for tx in (result.get("transactions") or []):
            if not isinstance(tx, dict):
                invalidos += 1
                continue
            fp = fingerprint(
                tx.get("date"), tx.get("type"), tx.get("amount"), tx.get("description")
            )
            if fp and fp in existing_fp:
                skipped += 1
                continue
            try:
                data = transaction_schema.load({**tx, "user_id": user_id})
            except ValidationError as err:
                # Um item malformado do banco não pode abortar a importação inteira
                # (era o que acontecia: parse_json lançava BadRequest e o sync
                # devolvia 400 sem gravar nada).
                invalidos += 1
                logger.warning(
                    "Item inválido ignorado na sincronização Open Finance",
                    extra={
                        "user_id": user_id, "endpoint": "/openfinance/sync",
                        "error_code": "sync_item_invalid",
                        "fields": sorted(err.messages),
                    },
                )
                continue
            obj = Transaction(**data)
            session_db.add(obj)
            inserted.append(obj)
            if fp:
                existing_fp.add(fp)
        session_db.commit()
        duration_ms = (time.time() - start_time) * 1000
        logger.info("Sincronização Open Finance concluída", extra={"user_id": user_id, "endpoint": "/openfinance/sync", "imported": len(inserted), "skipped": skipped, "invalid": invalidos, "duration_ms": round(duration_ms, 2)})
        return jsonify({
            "status": "success",
            "source": result.get("source"),
            "imported": len(inserted),
            "skipped_duplicates": skipped,
            # Novo: itens que o provider mandou mas não passaram na validação.
            # Antes um único item assim abortava o sync inteiro com 400.
            "skipped_invalid": invalidos,
            "transactions": transactions_schema.dump(inserted),
        }), 201

    # -------------------------------------------------------------------
    # Investments CRUD
    # -------------------------------------------------------------------
    @app.route("/api/users/<user_id>/investments", methods=["GET"])
    @require_auth
    @limiter.limit("100 per hour")
    def list_investments(user_id: str):
        """Lista investimentos do usuário com paginação."""
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        status_filter = request.args.get('status')
        asset_type_filter = request.args.get('asset_type')
        
        session_db = get_session()
        query = session_db.query(Investment).filter(
            Investment.user_id == user_id,
            Investment.deleted_at.is_(None)
        )
        
        if status_filter:
            query = query.filter(Investment.status == status_filter)
        if asset_type_filter:
            query = query.filter(Investment.asset_type == asset_type_filter)
        
        query = query.order_by(Investment.purchase_date.desc())
        paginated = paginate_query(query, page, per_page)
        
        return jsonify({
            "items": investments_schema.dump(paginated["items"]),
            "pagination": {
                "total": paginated["total"],
                "pages": paginated["pages"],
                "current_page": paginated["current_page"],
                "per_page": paginated["per_page"]
            }
        })

    @app.route("/api/users/<user_id>/investments", methods=["POST"])
    @require_auth
    @limiter.limit("100 per hour")  # Limita criação de investimentos
    def create_investment(user_id: str):
        """Cria novo investimento."""
        payload = request.get_json(silent=True) or {}
        payload["user_id"] = user_id
        if "purchase_date" not in payload:
            payload["purchase_date"] = today_date().isoformat()
        if "status" not in payload:
            payload["status"] = "active"
        if "current_price" not in payload:
            payload["current_price"] = payload.get("purchase_price")
        
        data = parse_json(investment_schema, payload)
        session_db = get_session()
        inv = Investment(**data)
        session_db.add(inv)
        session_db.commit()
        result = investment_schema.dump(inv)
        return jsonify(result), 201

    @app.route("/api/users/<user_id>/investments/<int:inv_id>", methods=["PUT", "PATCH"])
    @require_auth
    @limiter.limit("100 per hour")
    def update_investment(user_id: str, inv_id: int):
        """Atualiza investimento existente."""
        payload = request.get_json(silent=True) or {}
        session_db = get_session()
        inv = session_db.query(Investment).filter(
            Investment.id == inv_id,
            Investment.user_id == user_id,
            Investment.deleted_at.is_(None)
        ).first()
        if not inv:
            raise NotFound("Investimento não encontrado")
        
        # Antes só 5 campos eram aceitos aqui: name, current_price,
        # target_return, status e notes. O formulário de edição do frontend envia
        # também asset_type, amount, purchase_price e purchase_date — que eram
        # descartados em silêncio enquanto a resposta 200 dizia que salvou.
        # Agora todos os campos de negócio são editáveis, validados pelo schema.
        apply_update(inv, investment_schema, payload, (
            "name", "asset_type", "amount", "purchase_price", "current_price",
            "purchase_date", "target_return", "status", "notes",
        ))

        inv.updated_at = utcnow()
        session_db.commit()
        result = investment_schema.dump(inv)
        return jsonify(result)

    @app.route("/api/users/<user_id>/investments/<int:inv_id>", methods=["DELETE"])
    @require_auth
    @limiter.limit("100 per hour")
    def delete_investment(user_id: str, inv_id: int):
        """Deleta investimento (soft delete)."""
        session_db = get_session()
        inv = session_db.query(Investment).filter(
            Investment.id == inv_id,
            Investment.user_id == user_id,
            Investment.deleted_at.is_(None)
        ).first()
        if not inv:
            raise NotFound("Investimento não encontrado")
        
        inv.deleted_at = utcnow()
        session_db.commit()
        return jsonify({"deleted": inv_id})

    @app.route("/api/users/<user_id>/investments/portfolio", methods=["GET"])
    @require_auth
    @limiter.limit("50 per hour")
    def get_portfolio_analysis(user_id: str):
        """Análise detalhada do portfólio de investimentos."""
        session_db = get_session()

        filtro = (
            Investment.user_id == user_id,
            Investment.deleted_at.is_(None),
            Investment.status == "active",
        )

        # Valor investido = quantidade x preço de compra.
        # Valor atual usa a cotação corrente; quando ela não existe (ou é zero, que
        # esta API sempre tratou como "cotação desconhecida") cai no valor
        # investido — mesmo comportamento de antes, agora expresso em SQL.
        investido = Investment.amount * Investment.purchase_price
        atual = case(
            (func.coalesce(Investment.current_price, 0) == 0, investido),
            else_=Investment.amount * Investment.current_price,
        )

        # Agregação no banco. Antes carregávamos todas as posições para somar em
        # Python; agora são duas consultas cujo custo não cresce com o portfólio.
        total_posicoes, soma_investido, soma_atual = session_db.query(
            func.count(Investment.id),
            func.coalesce(func.sum(investido), 0),
            func.coalesce(func.sum(atual), 0),
        ).filter(*filtro).one()

        if not total_posicoes:
            return jsonify({
                "portfolio": {
                    "total_invested": 0,
                    "current_value": 0,
                    "total_return": 0,
                    "return_percentage": 0,
                    "by_asset_type": {},
                    "count": 0
                },
                "recommendations": [
                    {
                        "type": "info",
                        "title": "Comece seu portfólio",
                        "description": "Você não tem investimentos registrados. Comece adicionando seus investimentos!"
                    }
                ]
            })

        por_tipo = session_db.query(
            Investment.asset_type,
            func.count(Investment.id),
            func.coalesce(func.sum(investido), 0),
            func.coalesce(func.sum(atual), 0),
        ).filter(*filtro).group_by(Investment.asset_type).all()

        # money() normaliza Decimal (PostgreSQL, NUMERIC) e float (SQLite) para o
        # mesmo tipo — jsonify não serializa Decimal, e sem isso o endpoint daria
        # 500 apenas em produção.
        total_invested = money(soma_investido)
        current_value = money(soma_atual)

        by_asset_type = {}
        for asset_type, quantidade, inv_bruto, cur_bruto in por_tipo:
            inv_valor = money(inv_bruto)
            cur_valor = money(cur_bruto)
            by_asset_type[asset_type] = {
                "invested": inv_valor,
                "current_value": cur_valor,
                "count": quantidade,
                "return_percentage": round(
                    (cur_valor - inv_valor) / inv_valor * 100, 2
                ) if inv_valor > 0 else 0,
            }

        total_return = money(current_value - total_invested)
        return_percentage = round(
            total_return / total_invested * 100, 2
        ) if total_invested > 0 else 0

        # Gerar recomendações
        recommendations = []
        
        # Recomendação 1: Diversificação
        if len(by_asset_type) < 3:
            recommendations.append({
                "type": "tip",
                "icon": "📊",
                "title": "Diversifique seu portfólio",
                "description": "Você tem apenas investimentos em " + str(len(by_asset_type)) + " tipo(s) de ativo. Considere diversificar em stocks, REITs, fundos e outros.",
                "priority": "medium"
            })
        
        # Recomendação 2: Rendimento ruim
        if return_percentage < 0:
            recommendations.append({
                "type": "alert",
                "icon": "⚠️",
                "title": "Portfólio em queda",
                "description": f"Seu portfólio está em queda de {abs(return_percentage):.2f}%. Revise suas posições.",
                "priority": "high"
            })
        
        # Recomendação 3: Rendimento bom
        elif return_percentage > 15:
            recommendations.append({
                "type": "success",
                "icon": "🎉",
                "title": "Ótimo rendimento!",
                "description": f"Seu portfólio cresceu {return_percentage:.2f}%! Parabéns!",
                "priority": "low"
            })
        
        # Recomendação 4: Rebalanceamento
        largest_asset = max(by_asset_type.items(), key=lambda x: x[1]["current_value"])
        largest_percentage = (largest_asset[1]["current_value"] / current_value * 100) if current_value > 0 else 0
        if largest_percentage > 60:
            recommendations.append({
                "type": "tip",
                "icon": "⚖️",
                "title": "Rebalanceie seu portfólio",
                "description": f"{largest_asset[0]} representa {largest_percentage:.1f}% do seu portfólio. Considere reduzir essa posição.",
                "priority": "medium"
            })
        
        
        return jsonify({
            "portfolio": {
                "total_invested": round(total_invested, 2),
                "current_value": round(current_value, 2),
                "total_return": round(total_return, 2),
                "return_percentage": round(return_percentage, 2),
                "by_asset_type": {k: {
                    "invested": round(v["invested"], 2),
                    "current_value": round(v["current_value"], 2),
                    "count": v["count"],
                    "return_percentage": v["return_percentage"]
                } for k, v in by_asset_type.items()},
                "count": total_posicoes
            },
            "recommendations": recommendations
        })

    @app.route("/api/investments/tips", methods=["GET"])
    @limiter.limit("50 per hour")
    def get_investment_tips():
        """Dicas e conselhos sobre investimentos."""
        tips = [
            {
                "id": 1,
                "category": "beginner",
                "icon": "📚",
                "title": "Entenda os Fundamentos",
                "description": "Antes de investir, aprenda sobre diferentes tipos de ativos: ações, fundos, REITs, criptomoedas e commodities.",
                "tips": [
                    "Ações: propriedade de empresa, pode crescer muito",
                    "Fundos: carteira diversificada gerenciada por profissional",
                    "REITs: investimento em imóveis via bolsa",
                    "Criptomoedas: altamente voláteis, requer cuidado",
                    "Commodities: preço de matérias-primas"
                ],
                "difficulty": "easy"
            },
            {
                "id": 2,
                "category": "strategy",
                "icon": "📊",
                "title": "Regra 50-30-20",
                "description": "Uma estratégia simples e eficaz para gerenciar suas finanças.",
                "tips": [
                    "50% da renda: despesas essenciais (moradia, comida, contas)",
                    "30% da renda: gastos discricionários (lazer, compras)",
                    "20% da renda: poupança e investimentos"
                ],
                "difficulty": "easy"
            },
            {
                "id": 3,
                "category": "diversification",
                "icon": "🎯",
                "title": "Diversificação do Portfólio",
                "description": "Não coloque todos os ovos em uma única cesta.",
                "tips": [
                    "Distribua investimentos em diferentes tipos de ativos",
                    "Invista em diferentes setores da economia",
                    "Considere geograficamente diversificado",
                    "Mix típico: 60% ações, 30% renda fixa, 10% alternativo"
                ],
                "difficulty": "medium"
            },
            {
                "id": 4,
                "category": "risk",
                "icon": "⚠️",
                "title": "Risco vs Retorno",
                "description": "Quanto maior o retorno esperado, maior o risco.",
                "tips": [
                    "Criptomoedas: altíssimo risco e retorno",
                    "Ações: risco alto, retorno potencial alto",
                    "Fundos: risco médio, retorno médio",
                    "Renda fixa: risco baixo, retorno baixo"
                ],
                "difficulty": "medium"
            },
            {
                "id": 5,
                "category": "timing",
                "icon": "📈",
                "title": "Compre Regularmente (Dollar Cost Averaging)",
                "description": "Invista uma quantia fixa regularmente, independente do preço.",
                "tips": [
                    "Reduz o impacto da volatilidade",
                    "Ideal para investidores iniciantes",
                    "Pode ser automático via débito automático",
                    "Exemplo: R$ 500 mensais em fundos de índice"
                ],
                "difficulty": "easy"
            },
            {
                "id": 6,
                "category": "emotions",
                "icon": "😌",
                "title": "Controle Emocional",
                "description": "Não venda por pânico ou euforia.",
                "tips": [
                    "Ignore notícias de curto prazo",
                    "Mantenha sua estratégia de longo prazo",
                    "Não tente 'adivinhar' o mercado",
                    "Pessoas emocionais perdem dinheiro com consistência"
                ],
                "difficulty": "hard"
            },
            {
                "id": 7,
                "category": "taxation",
                "icon": "💰",
                "title": "Impostos em Investimentos",
                "description": "Entenda como os impostos afetam seus retornos.",
                "tips": [
                    "Imposto de renda em ganho de capital",
                    "Fundos imobiliários têm tributação especial",
                    "Renda fixa tributada como renda normal",
                    "Planeje suas vendas para otimizar impostos"
                ],
                "difficulty": "hard"
            },
            {
                "id": 8,
                "category": "emergency",
                "icon": "🏦",
                "title": "Tenha um Fundo de Emergência",
                "description": "Antes de investir, tenha de 3-6 meses de despesas guardadas.",
                "tips": [
                    "Deixe em conta poupança ou aplicação de renda fixa",
                    "Fácil acesso em caso de necessidade",
                    "Evita necessidade de vender investimentos com prejuízo",
                    "Traz paz de espírito"
                ],
                "difficulty": "easy"
            },
            {
                "id": 9,
                "category": "passive_income",
                "icon": "🌱",
                "title": "Renda Passiva",
                "description": "Deixe seu dinheiro trabalhar para você.",
                "tips": [
                    "Dividendos de ações: ganho periódico",
                    "Fundos imobiliários: aluguel distribuído",
                    "Renda fixa: juros periódicos",
                    "Juros compostos: efeito exponencial no longo prazo"
                ],
                "difficulty": "medium"
            },
            {
                "id": 10,
                "category": "rebalancing",
                "icon": "⚙️",
                "title": "Rebalanceie Regularmente",
                "description": "Ajuste seu portfólio para manter o alvo.",
                "tips": [
                    "Rebalanceie anualmente ou semestralmente",
                    "Se uma categoria ficou muito grande, reduza",
                    "Se uma categoria ficou pequena, aumente",
                    "Aproveite para otimizar impostos"
                ],
                "difficulty": "medium"
            }
        ]
        
        return jsonify({
            "tips": tips,
            "total": len(tips),
            "categories": list(set([t["category"] for t in tips]))
        })

    @app.route("/api/openfinance/webhook", methods=["POST"])
    @csrf.exempt  # Webhooks são chamados por serviços externos, não podem ter CSRF
    @limiter.limit("100 per hour")
    def openfinance_webhook():
        """
        Endpoint para receber webhooks do Open Finance.
        
        Eventos suportados:
        - consent.revoked: Consentimento foi revogado pelo usuário
        - consent.expired: Consentimento expirou
        - transaction.created: Nova transação disponível
        - account.updated: Dados da conta foram atualizados
        """
        start_time = time.time()

        # Fail-closed: sem OPENFINANCE_WEBHOOK_SECRET o endpoint fica
        # DESATIVADO. Antes a verificação era condicional (`if webhook_secret:`),
        # então na ausência do segredo qualquer pessoa podia enviar
        # {"event": "consent.revoked", "consent_id": "..."} e revogar/expirar
        # consentimentos de terceiros.
        webhook_secret = os.getenv("OPENFINANCE_WEBHOOK_SECRET")
        if not webhook_secret:
            logger.error(
                "Webhook Open Finance recebido sem OPENFINANCE_WEBHOOK_SECRET configurado",
                extra={"endpoint": "/openfinance/webhook", "error_code": "webhook_not_configured"},
            )
            return jsonify({
                "error": "webhook_not_configured",
                "details": "Recepção de webhooks desativada por falta de configuração.",
            }), 503

        signature = (request.headers.get("X-Webhook-Signature") or "").strip()
        if not signature:
            logger.warning(
                "Webhook sem assinatura recebido",
                extra={"endpoint": "/openfinance/webhook", "error_code": "missing_signature"},
            )
            return jsonify({"error": "missing_signature"}), 401

        # Aceita tanto "<hex>" quanto "sha256=<hex>".
        if signature.lower().startswith("sha256="):
            signature = signature.split("=", 1)[1].strip()

        expected_signature = hmac.new(
            webhook_secret.encode(),
            request.get_data(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature.lower(), expected_signature.lower()):
            logger.warning(
                "Webhook com assinatura inválida",
                extra={"endpoint": "/openfinance/webhook", "error_code": "invalid_signature"},
            )
            return jsonify({"error": "invalid_signature"}), 401
        
        try:
            payload = request.get_json()
            if not payload:
                return jsonify({"error": "invalid_payload"}), 400
            
            event_type = payload.get("event")
            consent_id = payload.get("consent_id")
            event_data = payload.get("data", {})
            
            if not event_type or not consent_id:
                return jsonify({"error": "missing_required_fields"}), 400
            
            logger.info(f"Webhook recebido: {event_type}", extra={
                "endpoint": "/openfinance/webhook",
                "event": event_type,
                "consent_id": consent_id
            })
            
            # Usar sessão do banco (get_session_local() inicializa sob demanda;
            # o global SessionLocal ainda é None se o webhook for a 1ª rota
            # chamada após o boot, o que causava TypeError -> 500).
            db = get_session_local()()
            try:
                # Buscar consentimento
                consent = db.query(Consent).filter(
                    Consent.consent_id == consent_id,
                    Consent.deleted_at.is_(None)
            ).first()
            
                if not consent:
                    logger.warning("Webhook para consent desconhecido", extra={
                        "consent_id": consent_id,
                        "event": event_type
                    })
                    return jsonify({"error": "consent_not_found"}), 404
                
                # Processar evento
                if event_type == "consent.revoked":
                    consent.status = "revoked"
                    db.commit()
                    logger.info("Consentimento revogado via webhook", extra={
                        "consent_id": consent_id,
                        "user_id": consent.user_id
                    })
                    
                elif event_type == "consent.expired":
                    consent.status = "expired"
                    db.commit()
                    logger.info("Consentimento expirado via webhook", extra={
                        "consent_id": consent_id,
                        "user_id": consent.user_id
                    })
                    
                elif event_type == "transaction.created":
                    # Disparar sincronização automática em background (opcional)
                    # Por enquanto, apenas logar o evento
                    logger.info("Nova transação disponível", extra={
                        "consent_id": consent_id,
                        "user_id": consent.user_id,
                        "transaction_count": event_data.get("count", 1)
                    })
                    # TODO: Implementar sincronização automática em background task
                    
                elif event_type == "account.updated":
                    logger.info("Conta atualizada", extra={
                        "consent_id": consent_id,
                        "user_id": consent.user_id
                    })
                    # TODO: Atualizar informações da conta
                    
                else:
                    logger.warning("Evento desconhecido", extra={
                        "event": event_type,
                        "consent_id": consent_id
                    })
                    return jsonify({"error": "unknown_event_type"}), 400
                
                duration_ms = (time.time() - start_time) * 1000
                logger.info("Webhook processado com sucesso", extra={
                    "endpoint": "/openfinance/webhook",
                    "event": event_type,
                    "duration_ms": round(duration_ms, 2)
                })
                
                return jsonify({"status": "processed", "event": event_type}), 200
            finally:
                db.close()
                
        except Exception as e:
            logger.error(
                "Erro ao processar webhook",
                exc_info=e,
                extra={"endpoint": "/openfinance/webhook", "error_code": "webhook_processing_failed"},
            )
            # `str(e)` vazava detalhes internos (mesma classe de problema
            # corrigida nos demais handlers na Fase 1).
            return jsonify({
                "error": "webhook_processing_failed",
                "details": "Falha ao processar o webhook.",
            }), 500

    return app


# Observação: NÃO criar `app = create_app()` em nível de módulo.
# - `alembic/env.py` faz `from backend import Base`: com o app criado no import,
#   cada migração disparava create_all() e abria conexão com o banco.
# - `wsgi.py` chama create_app() explicitamente: o import criava um segundo app
#   a cada boot (tabelas, provider e Limiter inicializados duas vezes — dava
#   para ver a duplicidade nos logs de startup).
_APP_SOB_DEMANDA = None


def __getattr__(name: str):
    """Shim de compatibilidade (PEP 562): `backend.app` continua existindo para
    quem referencia `backend:app` (gunicorn / flask --app), mas o app só é
    criado no primeiro acesso — nunca no import.

    O entrypoint canônico continua sendo `wsgi:app` (ver startup.txt).
    """
    global _APP_SOB_DEMANDA
    if name == "app":
        if _APP_SOB_DEMANDA is None:
            _APP_SOB_DEMANDA = create_app()
        return _APP_SOB_DEMANDA
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    # O modo debug do Werkzeug, combinado com bind em 0.0.0.0, expunha o console
    # interativo (execução remota de código) para qualquer um que alcançasse a
    # porta 5000 — e o README manda rodar exatamente `python backend.py`.
    # Agora o debug é opt-in via FLASK_DEBUG e nunca fica ligado por padrão.
    create_app().run(
        host=os.getenv("FLASK_RUN_HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "5000")),
        debug=env_flag("FLASK_DEBUG"),
    )