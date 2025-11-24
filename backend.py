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

from datetime import datetime, date
from typing import Optional
import secrets
from functools import wraps
from datetime import timedelta

from flask import Flask, jsonify, request, redirect, url_for, session
from flask_cors import CORS
from sqlalchemy import create_engine, Integer, String, Float, Date, Column
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from marshmallow import Schema, fields, ValidationError, validate
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import os
from open_finance import sync_user_transactions

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


class Installment(Base):
    __tablename__ = "installments"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    description = Column(String(255), nullable=False)
    monthly_value = Column(Float, nullable=False)
    total_months = Column(Integer, nullable=False)
    date_added = Column(Date, nullable=False)


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


def create_app() -> Flask:
    # Serve arquivos estáticos (ex.: index_api.html) a partir da raiz do projeto
    app = Flask(__name__, static_url_path='', static_folder='.')
    app.secret_key = FLASK_SECRET_KEY
    
    # CORS com suporte a credenciais
    CORS(app, supports_credentials=True, origins=["http://localhost:5000", "http://127.0.0.1:5000"])

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
    def handle_bad_request(e: BadRequest):
        return jsonify({"error": "bad_request", "details": e.messages}), 400

    @app.errorhandler(NotFound)
    def handle_not_found(e: NotFound):
        return jsonify({"error": "not_found", "details": e.message}), 404

    from werkzeug.exceptions import HTTPException
    @app.errorhandler(Exception)
    def handle_generic(e: Exception):
        # Evita transformar 404/405 etc em 500
        if isinstance(e, HTTPException):
            return jsonify({"error": e.name.lower().replace(' ', '_'), "details": e.description}), e.code
        return jsonify({"error": "internal_error", "details": str(e)}), 500

    # -------------------------------------------------------------------
    # Health
    # -------------------------------------------------------------------
    @app.route("/api/health")
    @require_auth
    def health():
        return jsonify({"status": "ok"})

    @app.route("/")
    @require_auth
    def root():
        return jsonify({"message": "Gestor Financeiro API", "health": "/api/health"}), 200

    # -------------------------------------------------------------------
    # Autenticação Google OAuth
    # -------------------------------------------------------------------
    @app.route("/auth/login")
    def login():
        """Inicia fluxo de login com Google."""
        if not google:
            return jsonify({"error": "OAuth não configurado. Configure GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET."}), 500
        redirect_uri = url_for('auth_callback', _external=True)
        return google.authorize_redirect(redirect_uri)

    @app.route("/auth/callback")
    def auth_callback():
        """Callback do Google OAuth."""
        if not google:
            return jsonify({"error": "OAuth não configurado"}), 500
        try:
            token = google.authorize_access_token()
            user_info = token.get('userinfo')
            if user_info:
                session['user'] = {
                    'id': user_info.get('sub'),
                    'email': user_info.get('email'),
                    'name': user_info.get('name'),
                    'picture': user_info.get('picture')
                }
                # Redirecionar para frontend
                return redirect('http://localhost:5000/index_api.html?logged=true')
            return jsonify({"error": "Falha ao obter informações do usuário"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/auth/logout")
    def logout():
        """Encerra sessão do usuário."""
        session.pop('user', None)
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
    # Transactions CRUD
    # -------------------------------------------------------------------
    @app.route("/api/users/<user_id>/transactions", methods=["GET"])
    @require_auth
    def list_transactions(user_id: str):
        session = get_session()
        items = session.query(Transaction).filter(Transaction.user_id == user_id).order_by(Transaction.date.desc()).all()
        return jsonify(transactions_schema.dump(items))

    @app.route("/api/users/<user_id>/transactions", methods=["POST"])
    @require_auth
    def create_transaction(user_id: str):
        payload = request.get_json(silent=True) or {}
        payload["user_id"] = user_id
        if "date" not in payload:
            payload["date"] = today_date().isoformat()
        data = parse_json(transaction_schema, payload)
        session = get_session()
        txn = Transaction(**data)
        session.add(txn)
        session.commit()
        return jsonify(transaction_schema.dump(txn)), 201

    @app.route("/api/users/<user_id>/transactions/<int:txn_id>", methods=["PUT", "PATCH"])
    @require_auth
    def update_transaction(user_id: str, txn_id: int):
        payload = request.get_json(silent=True) or {}
        session = get_session()
        txn: Optional[Transaction] = session.query(Transaction).filter(Transaction.id == txn_id, Transaction.user_id == user_id).first()
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
    def delete_transaction(user_id: str, txn_id: int):
        session = get_session()
        txn = session.query(Transaction).filter(Transaction.id == txn_id, Transaction.user_id == user_id).first()
        if not txn:
            raise NotFound("Transação não encontrada")
        session.delete(txn)
        session.commit()
        return jsonify({"deleted": txn_id})

    # -------------------------------------------------------------------
    # Installments CRUD
    # -------------------------------------------------------------------
    @app.route("/api/users/<user_id>/installments", methods=["GET"])
    @require_auth
    def list_installments(user_id: str):
        session = get_session()
        items = session.query(Installment).filter(Installment.user_id == user_id).order_by(Installment.date_added.desc()).all()
        return jsonify(installments_schema.dump(items))

    @app.route("/api/users/<user_id>/installments", methods=["POST"])
    @require_auth
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
    def update_installment(user_id: str, inst_id: int):
        payload = request.get_json(silent=True) or {}
        session = get_session()
        inst: Optional[Installment] = session.query(Installment).filter(Installment.id == inst_id, Installment.user_id == user_id).first()
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
    def delete_installment(user_id: str, inst_id: int):
        session = get_session()
        inst = session.query(Installment).filter(Installment.id == inst_id, Installment.user_id == user_id).first()
        if not inst:
            raise NotFound("Parcela não encontrada")
        session.delete(inst)
        session.commit()
        return jsonify({"deleted": inst_id})

    # -------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------
    @app.route("/api/users/<user_id>/summary", methods=["GET"])
    @require_auth
    def summary(user_id: str):
        session = get_session()
        txns = session.query(Transaction).filter(Transaction.user_id == user_id).all()
        insts = session.query(Installment).filter(Installment.user_id == user_id).all()
        income = sum(t.amount for t in txns if t.type == "income")
        expenses_avulsa = sum(t.amount for t in txns if t.type == "expense")
        expenses_parcelas = sum(i.monthly_value for i in insts)
        expenses_total = expenses_avulsa + expenses_parcelas
        balance = income - expenses_total
        return jsonify({
            "income": income,
            "expenses_avulsa": expenses_avulsa,
            "expenses_parcelas": expenses_parcelas,
            "expenses_total": expenses_total,
            "balance": balance
        })

    # -------------------------------------------------------------------
    # Importação simulada (Open Finance)
    # -------------------------------------------------------------------
    @app.route("/api/users/<user_id>/import", methods=["POST"])
    @require_auth
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
    def open_finance_sync(user_id: str):
        """Sincroniza transações via Open Finance (simulado)."""
        session_db = get_session()
        result = sync_user_transactions(local_user_id=user_id)
        inserted = []
        skipped = 0

        # Pré-carrega transações existentes do usuário para deduplicação
        existing = session_db.query(Transaction).filter(Transaction.user_id == user_id).all()
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
        return jsonify({
            "status": "success",
            "source": result.get("source"),
            "imported": len(inserted),
            "skipped_duplicates": skipped,
            "transactions": transactions_schema.dump(inserted)
        }), 201

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)