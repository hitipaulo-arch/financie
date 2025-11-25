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

from datetime import datetime, date, UTC
from typing import Optional
import secrets
from functools import wraps
from datetime import timedelta
import time

from flask import Flask, jsonify, request, redirect, url_for, session
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import create_engine, Integer, String, Float, Date, Column, DateTime
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
DB_URL = os.getenv("GF_DB_URL", "sqlite:///data.db")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False))
Base = declarative_base()


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    description = Column(String(255), nullable=False)
    amount = Column(Float, nullable=False)
    type = Column(String(16), nullable=False)  # income | expense
    date = Column(Date, nullable=False)
    deleted_at = Column(DateTime, nullable=True)  # Soft delete timestamp


class Installment(Base):
    __tablename__ = "installments"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    description = Column(String(255), nullable=False)
    monthly_value = Column(Float, nullable=False)
    total_months = Column(Integer, nullable=False)
    date_added = Column(Date, nullable=False)
    deleted_at = Column(DateTime, nullable=True)  # Soft delete timestamp


class Consent(Base):
    __tablename__ = "consents"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    consent_id = Column(String(128), unique=True, nullable=False)
    provider = Column(String(64), nullable=False)
    scopes = Column(String(512), nullable=False)
    status = Column(String(32), nullable=False)  # active | revoked | expired
    created_at = Column(DateTime, nullable=False)
    deleted_at = Column(DateTime, nullable=True)  # Soft delete timestamp


class ConsentSchema(Schema):
    id = fields.Int(dump_only=True)
    user_id = fields.Str(required=True, validate=validate.Length(min=1))
    consent_id = fields.Str(required=True, validate=validate.Length(min=4))
    provider = fields.Str(required=True, validate=validate.Length(min=2))
    scopes = fields.Str(required=True)
    status = fields.Str(required=True, validate=validate.OneOf(["active", "revoked", "expired"]))
    created_at = fields.DateTime(dump_only=True)


class TransactionSchema(Schema):
    id = fields.Int(dump_only=True)
    user_id = fields.Str(required=True, validate=validate.Length(min=1))
    description = fields.Str(required=True, validate=validate.Length(min=1))
    amount = fields.Float(required=True)
    type = fields.Str(required=True, validate=validate.OneOf(["income", "expense"]))
    date = fields.Date(required=True)


class InstallmentSchema(Schema):
    id = fields.Int(dump_only=True)
    user_id = fields.Str(required=True, validate=validate.Length(min=1))
    description = fields.Str(required=True, validate=validate.Length(min=1))
    monthly_value = fields.Float(required=True)
    total_months = fields.Int(required=True)
    date_added = fields.Date(required=True)


transaction_schema = TransactionSchema()
transactions_schema = TransactionSchema(many=True)
installment_schema = InstallmentSchema()
installments_schema = InstallmentSchema(many=True)
consent_schema = ConsentSchema()
consents_schema = ConsentSchema(many=True)


def create_app() -> Flask:
    # Serve arquivos estáticos (ex.: index_api.html) a partir da raiz do projeto
    app = Flask(__name__, static_url_path='', static_folder='.')
    app.secret_key = FLASK_SECRET_KEY
    
    # CORS com suporte a credenciais
    CORS(app, supports_credentials=True, origins=["http://localhost:5000", "http://127.0.0.1:5000"])

    # Rate Limiting (CRITICAL: Previne brute force e DDoS)
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://"
    )
    
    # CSRF Protection (CRITICAL: Previne Cross-Site Request Forgery)
    csrf = CSRFProtect(app)

    # Configuração de cookies/sessão (controlada por .env)
    app.config.update(
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
        SESSION_COOKIE_HTTPONLY=os.getenv("SESSION_COOKIE_HTTPONLY", "true").lower() == "true",
        SESSION_COOKIE_SAMESITE=os.getenv("SESSION_COOKIE_SAMESITE", "Lax"),
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=int(os.getenv("SESSION_LIFETIME_MINUTES", "120")))
    )

    @app.before_request
    def _permanent_session():
        session.permanent = True

    # Endpoint para obter CSRF token (para chamadas AJAX)
    @app.route('/api/csrf-token', methods=['GET'])
    def get_csrf_token():
        """Retorna CSRF token para cliente usar em requisições POST/PUT/DELETE."""
        return jsonify({"csrf_token": session.get('_csrf_token', 'N/A')}), 200

    # Cria tabelas se não existirem
    Base.metadata.create_all(engine)
    
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
        return SessionLocal()

    def parse_json(schema: Schema, payload: dict):
        try:
            return schema.load(payload)
        except ValidationError as err:
            raise BadRequest(err.messages)

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
    @app.errorhandler(Exception)
    def handle_generic(e: Exception) -> tuple:
        # Evita transformar 404/405 etc em 500
        if isinstance(e, HTTPException):
            return jsonify({"error": e.name.lower().replace(' ', '_'), "details": e.description}), e.code
        return jsonify({"error": "internal_error", "details": str(e)}), 500

    # -------------------------------------------------------------------
    # Health
    # -------------------------------------------------------------------
    @app.route("/api/health")
    @require_auth
    @csrf.exempt  # GET não requer CSRF
    def health():
        return jsonify({"status": "ok"})

    @app.route("/")
    @require_auth
    @csrf.exempt  # GET não requer CSRF
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
                # Redirecionar para frontend
                return redirect('http://localhost:5000/index_api.html?logged=true')
            logger.warning("Informações de usuário não obtidas", extra={"endpoint": "/auth/callback", "error_code": "no_user_info"})
            return jsonify({"error": "Falha ao obter informações do usuário"}), 400
        except Exception as e:
            logger.error("Erro no callback OAuth", extra={"endpoint": "/auth/callback", "error_code": "oauth_error", "exception": str(e)})
            return jsonify({"error": str(e)}), 400

    @app.route("/auth/logout")
    def logout():
        """Encerra sessão do usuário."""
        user_id = session.get('user', {}).get('id')
        session.pop('user', None)
        logger.info("Logout realizado", extra={"user_id": user_id, "endpoint": "/auth/logout", "method": "GET"})
        return jsonify({"message": "Logout realizado"}), 200

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
        data = consent_schema.load(payload)
        session_db = get_session()
        obj = Consent(
            user_id=payload.get('user_id', ''),
            consent_id=payload.get('consent_id', ''),
            provider=payload.get('provider', ''),
            scopes=payload.get('scopes', ''),
            status=payload.get('status', ''),
            created_at=datetime.now(UTC)
        )
        session_db.add(obj)
        session_db.commit()
        return jsonify(consent_schema.dump(obj)), 201

    @app.route("/api/users/<user_id>/openfinance/consents", methods=["GET"])
    @require_auth
    @csrf.exempt  # GET não requer CSRF
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
    @csrf.exempt  # GET não requer CSRF
    def list_transactions(user_id: str):
        # Query base - filtrar apenas registros não deletados
        session = get_session()
        query = session.query(Transaction).filter(
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
        data = parse_json(transaction_schema, payload)
        session = get_session()
        # Construir Transaction com campos explícitos
        txn = Transaction(
            user_id=payload.get('user_id'),
            description=payload.get('description'),
            amount=payload.get('amount'),
            type=payload.get('type'),
            date=datetime.strptime(payload.get('date', ''), '%Y-%m-%d').date() if payload.get('date') else today_date()
        )
        session.add(txn)
        session.commit()
        return jsonify(transaction_schema.dump(txn)), 201

    @app.route("/api/users/<user_id>/transactions/<int:txn_id>", methods=["PUT", "PATCH"])
    @require_auth
    @limiter.limit("100 per hour")  # IMPORTANT: Limita atualizações
    def update_transaction(user_id: str, txn_id: int):
        payload = request.get_json(silent=True) or {}
        session = get_session()
        txn: Optional[Transaction] = session.query(Transaction).filter(
            Transaction.id == txn_id,
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None)
        ).first()
        if not txn:
            raise NotFound("Transação não encontrada")
        # Campos permitidos
        for field in ["description", "amount", "type", "date"]:
            if field in payload:
                if field == "amount":
                    try:
                        val = float(payload[field])
                        if val <= 0:
                            raise ValueError
                        setattr(txn, field, val)
                    except Exception:
                        raise BadRequest({"amount": ["Valor inválido"]})
                elif field == "date":
                    try:
                        setattr(txn, field, datetime.strptime(payload[field], "%Y-%m-%d").date())
                    except Exception:
                        raise BadRequest({"date": ["Formato deve ser YYYY-MM-DD"]})
                elif field == "type":
                    if payload[field] not in ["income", "expense"]:
                        raise BadRequest({"type": ["Deve ser income ou expense"]})
                    setattr(txn, field, payload[field])
                else:
                    setattr(txn, field, payload[field])
        session.commit()
        return jsonify(transaction_schema.dump(txn))

    @app.route("/api/users/<user_id>/transactions/<int:txn_id>", methods=["DELETE"])
    @require_auth
    @limiter.limit("100 per hour")  # IMPORTANT: Limita exclusões
    def delete_transaction(user_id: str, txn_id: int):
        session = get_session()
        txn = session.query(Transaction).filter(
            Transaction.id == txn_id,
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None)
        ).first()
        if not txn:
            raise NotFound("Transação não encontrada")
        # Soft delete: set deleted_at timestamp
        txn.deleted_at = datetime.now(UTC)
        session.commit()
        return jsonify({"deleted": txn_id})

    # -------------------------------------------------------------------
    # Installments CRUD
    # -------------------------------------------------------------------
    @app.route("/api/users/<user_id>/installments", methods=["GET"])
    @require_auth
    @csrf.exempt  # GET não requer CSRF
    def list_installments(user_id: str):
        session = get_session()
        query = session.query(Installment).filter(
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
        session = get_session()
        inst = Installment(**data)
        session.add(inst)
        session.commit()
        return jsonify(installment_schema.dump(inst)), 201

    @app.route("/api/users/<user_id>/installments/<int:inst_id>", methods=["PUT", "PATCH"])
    @require_auth
    @limiter.limit("100 per hour")  # IMPORTANT: Limita atualizações de parcelas
    def update_installment(user_id: str, inst_id: int):
        payload = request.get_json(silent=True) or {}
        session = get_session()
        inst: Optional[Installment] = session.query(Installment).filter(
            Installment.id == inst_id,
            Installment.user_id == user_id,
            Installment.deleted_at.is_(None)
        ).first()
        if not inst:
            raise NotFound("Parcela não encontrada")
        for field in ["description", "monthly_value", "total_months", "date_added"]:
            if field in payload:
                if field in ["monthly_value"]:
                    try:
                        val = float(payload[field])
                        if val <= 0:
                            raise ValueError
                        setattr(inst, field, val)
                    except Exception:
                        raise BadRequest({field: ["Valor inválido"]})
                elif field in ["total_months"]:
                    try:
                        val = int(payload[field])
                        if val <= 0:
                            raise ValueError
                        setattr(inst, field, val)
                    except Exception:
                        raise BadRequest({field: ["Inteiro positivo"]})
                elif field == "date_added":
                    try:
                        setattr(inst, field, datetime.strptime(payload[field], "%Y-%m-%d").date())
                    except Exception:
                        raise BadRequest({field: ["Formato deve ser YYYY-MM-DD"]})
                else:
                    setattr(inst, field, payload[field])
        session.commit()
        return jsonify(installment_schema.dump(inst))

    @app.route("/api/users/<user_id>/installments/<int:inst_id>", methods=["DELETE"])
    @require_auth
    @limiter.limit("100 per hour")  # IMPORTANT: Limita exclusões de parcelas
    def delete_installment(user_id: str, inst_id: int):
        session = get_session()
        inst = session.query(Installment).filter(
            Installment.id == inst_id,
            Installment.user_id == user_id,
            Installment.deleted_at.is_(None)
        ).first()
        if not inst:
            raise NotFound("Parcela não encontrada")
        # Soft delete: set deleted_at timestamp
        inst.deleted_at = datetime.now(UTC)
        session.commit()
        return jsonify({"deleted": inst_id})

    # -------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------
    @app.route("/api/users/<user_id>/summary", methods=["GET"])
    @require_auth
    @csrf.exempt  # GET não requer CSRF
    def summary(user_id: str):
        session = get_session()
        # Filtrar apenas registros não deletados
        txns = session.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None)
        ).all()
        insts = session.query(Installment).filter(
            Installment.user_id == user_id,
            Installment.deleted_at.is_(None)
        ).all()
        # Calcular somas iterando sobre objetos ORM
        income = 0.0
        expenses_avulsa = 0.0
        for t in txns:
            amt = float(t.amount) if t.amount else 0.0
            if t.type and t.type == "income":
                income += amt
            elif t.type and t.type == "expense":
                expenses_avulsa += amt
        expenses_parcelas = sum(float(i.monthly_value) if i.monthly_value else 0.0 for i in insts) if insts else 0.0
        expenses_total = float(expenses_avulsa) + float(expenses_parcelas)
        balance = float(income) - float(expenses_total)
        return jsonify({
            "income": round(income, 2),
            "expenses_avulsa": round(expenses_avulsa, 2),
            "expenses_parcelas": round(expenses_parcelas, 2),
            "expenses_total": round(expenses_total, 2),
            "balance": round(balance, 2)
        })

    # -------------------------------------------------------------------
    # Importação simulada (Open Finance)
    # -------------------------------------------------------------------
    @app.route("/api/users/<user_id>/import", methods=["POST"])
    @require_auth
    @limiter.limit("20 per hour")  # IMPORTANT: Limita importações
    def import_data(user_id: str):
        session = get_session()
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
            session.add(txn)
            created.append(txn)
        session.commit()
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
            logger.error("Erro na sincronização Open Finance", extra={"user_id": user_id, "error": str(e)})
            return jsonify({"error": "sync_failed", "details": str(e)}), 500
        
        inserted = []
        skipped = 0

        # Pré-carrega transações existentes do usuário para deduplicação (apenas não deletadas)
        existing = session_db.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None)
        ).all()
        def fingerprint(d: dict) -> str:
            return f"{d['date']}|{d['type']}|{d['amount']:.2f}|{d['description'].strip().lower()}"
        existing_fp = {fingerprint({
            'date': t.date.isoformat(),
            'type': t.type,
            'amount': t.amount,
            'description': t.description
        }) for t in existing}

        for tx in result["transactions"]:
            fp = fingerprint(tx)
            if fp in existing_fp:
                skipped += 1
                continue
            data = parse_json(transaction_schema, {**tx, "user_id": user_id})
            obj = Transaction(**data)
            session_db.add(obj)
            inserted.append(obj)
            existing_fp.add(fp)
        session_db.commit()
        duration_ms = (time.time() - start_time) * 1000
        logger.info("Sincronização Open Finance concluída", extra={"user_id": user_id, "endpoint": "/openfinance/sync", "imported": len(inserted), "skipped": skipped, "duration_ms": round(duration_ms, 2)})
        return jsonify({
            "status": "success",
            "source": result.get("source"),
            "imported": len(inserted),
            "skipped_duplicates": skipped,
            "transactions": transactions_schema.dump(inserted),
            "consent_id": active_consent.consent_id
        }), 201

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)