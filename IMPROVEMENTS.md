# ANÁLISE DE CÓDIGO E MELHORIAS PROPOSTAS
## Gestor Financeiro 2.0 - 24/11/2025

---

## 1. MELHORIAS DE SEGURANÇA

### 1.1 Rate Limiting (CRÍTICO)
**Problema:** Sem proteção contra força bruta ou DDoS
**Impacto:** Endpoints de auth vulneráveis
**Solução:** Adicionar Flask-Limiter
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

@limiter.limit("5 per minute")  # Login
def login():
    pass
```

### 1.2 CSRF Protection (IMPORTANTE)
**Problema:** Sem token CSRF em formulários
**Solução:** Flask-WTF com csrf_protect
```python
from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect(app)
```

### 1.3 Input Validation (MELHORAR)
**Problema:** amount pode ser 0 ou negativo; description pode ter XSS
**Solução:** Adicionar validações Marshmallow
```python
amount = fields.Float(required=True, validate=validate.Range(min=0.01))
description = fields.Str(
    required=True,
    validate=validate.Length(min=1, max=255),
    required=True
)
```

---

## 2. MELHORIAS DE PERFORMANCE

### 2.1 Paginação (IMPORTANTE)
**Problema:** Listar ALL transações sem limite
**Impacto:** Com 1M de transações, API trava
**Solução:** Adicionar paginação
```python
@app.route("/api/users/<user_id>/transactions", methods=["GET"])
def list_transactions(user_id: str):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    query = session.query(Transaction).filter(Transaction.user_id == user_id)
    paginated = query.paginate(page=page, per_page=per_page)
    return jsonify({
        "items": transactions_schema.dump(paginated.items),
        "total": paginated.total,
        "pages": paginated.pages,
        "current_page": page
    })
```

### 2.2 Índices no DB (MELHORAR)
**Problema:** Queries sem índices em date, type, status
**Solução:** Adicionar índices
```python
class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), index=True)  # ✓ existe
    date = Column(Date, index=True)  # ✗ falta
    type = Column(String(16), index=True)  # ✗ falta
    
class Consent(Base):
    status = Column(String(32), index=True)  # ✗ falta
```

### 2.3 Filtros Avançados (MELHORAR)
**Problema:** Sem filtro por data/tipo
**Solução:** Query parameters
```python
@app.route("/api/users/<user_id>/transactions", methods=["GET"])
def list_transactions(user_id: str):
    start_date = request.args.get('start_date')  # 2025-11-01
    end_date = request.args.get('end_date')      # 2025-11-30
    type_filter = request.args.get('type')       # income|expense
    
    query = session.query(Transaction).filter(Transaction.user_id == user_id)
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    if type_filter:
        query = query.filter(Transaction.type == type_filter)
    ...
```

---

## 3. MELHORIAS DE FUNCIONALIDADE

### 3.1 Soft Delete (IMPORTANTE)
**Problema:** DELETE permanente; sem auditoria
**Solução:** Adicionar deleted_at
```python
class Transaction(Base):
    deleted_at = Column(DateTime, nullable=True, default=None)

@app.route("/api/users/<user_id>/transactions/<int:txn_id>", methods=["DELETE"])
def delete_transaction(user_id: str, txn_id: int):
    txn = session.query(Transaction).filter(...).first()
    txn.deleted_at = datetime.now(UTC)  # soft delete
    session.commit()
    
    # Query padrão:
    session.query(Transaction).filter(Transaction.deleted_at.is_(None))
```

### 3.2 Categorias de Transações (NICE-TO-HAVE)
**Problema:** Sem categorização (alimentação, transporte, etc)
**Solução:** Adicionar Category model
```python
class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), index=True)
    name = Column(String(64))  # "Alimentação"
    
class Transaction(Base):
    category_id = Column(Integer, ForeignKey("categories.id"))
```

### 3.3 Alertas/Metas (NICE-TO-HAVE)
**Problema:** Sem alertas de limite de gasto
**Solução:** Adicionar Alert model
```python
class Alert(Base):
    __tablename__ = "alerts"
    user_id = Column(String(64), index=True)
    type = Column(String(32))  # budget_exceeded, low_balance
    threshold = Column(Float)
    active = Column(Boolean, default=True)
```

### 3.4 Exportação (IMPORTANTE)
**Problema:** Sem exportar para CSV/PDF
**Solução:** Adicionar endpoint
```python
@app.route("/api/users/<user_id>/transactions/export", methods=["GET"])
def export_transactions(user_id: str):
    fmt = request.args.get('format', 'csv')  # csv, pdf, json
    # Implementar lógica...
```

---

## 4. MELHORIAS DE INFRAESTRUTURA

### 4.1 Database Connection Pool (IMPORTANTE)
**Problema:** Sem pooling; novas conexões por requisição
**Impacto:** Lentidão em alta concorrência
**Solução:** Configurar pool
```python
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DB_URL,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True  # Test connections before use
)
```

### 4.2 Migrations com Alembic (IMPORTANTE)
**Problema:** Sem versionamento de schema
**Impacto:** Difícil fazer rollback
**Solução:** Usar Alembic
```bash
pip install alembic
alembic init alembic
alembic revision --autogenerate -m "Add deleted_at to Transaction"
alembic upgrade head
```

### 4.3 Gunicorn para Produção (CRÍTICO)
**Problema:** Flask dev server não é production-ready
**Solução:** Usar Gunicorn
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 backend:app
```

### 4.4 Environment Configuration (MELHORAR)
**Problema:** .env sem validação de campos obrigatórios
**Solução:** Usar pydantic-settings
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DB_URL: str
    FLASK_SECRET_KEY: str
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    
    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 5. MELHORIAS DE OBSERVABILIDADE

### 5.1 Metrics (PROMETHEUS) (NICE-TO-HAVE)
**Problema:** Sem visibilidade de performance
**Solução:** Adicionar Prometheus
```python
from prometheus_client import Counter, Histogram, generate_latest

request_count = Counter('http_requests_total', 'Total Requests', ['method', 'endpoint'])
request_duration = Histogram('http_request_duration_ms', 'Request Duration')

@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    duration_ms = (time.time() - request.start_time) * 1000
    request_duration.observe(duration_ms)
    return response
```

### 5.2 Erro Tracking (SENTRY) (NICE-TO-HAVE)
**Problema:** Erros sem alertas
**Solução:** Integrar Sentry
```python
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    integrations=[FlaskIntegration()],
    traces_sample_rate=1.0
)
```

### 5.3 Request/Response Tracing (NICE-TO-HAVE)
**Problema:** Sem correlation IDs para rastrear requisições
**Solução:** Adicionar middleware
```python
import uuid

@app.before_request
def add_request_id():
    request.id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
    logger.info(f"Request {request.id}: {request.method} {request.path}")
```

---

## 6. MELHORIAS DE TESTES

### 6.1 Test Coverage (IMPORTANTE)
**Atual:** ~95% cobertura, faltam edge cases
**Solução:** Adicionar testes
- [ ] Test rate limiting
- [ ] Test CSRF token
- [ ] Test paginated response
- [ ] Test soft delete
- [ ] Test concurrent requests
- [ ] Test large datasets

### 6.2 Integration Tests (IMPORTANTE)
**Problema:** Testes apenas unitários
**Solução:** Adicionar testes de integração
```python
class TestIntegration:
    def test_full_workflow(self, client):
        # Create -> List -> Update -> Summary -> Delete
```

### 6.3 Load Testing (NICE-TO-HAVE)
**Problema:** Sem teste de performance
**Solução:** Usar Locust/k6
```bash
pip install locust
locust -f locustfile.py --host=http://localhost:5000
```

---

## 7. MELHORIAS DE CÓDIGO

### 7.1 Remover parse_json não-utilizado (CLEANUP)
```python
def parse_json(schema: Schema, payload: dict):
    try:
        return schema.load(payload)
    except ValidationError as err:
        raise BadRequest(err.messages)
```
✗ Não está sendo usado efetivamente. Remover ou refatorar.

### 7.2 Consolidar constantes (CLEANUP)
**Problema:** Valores mágicos espalhados
**Solução:** Criar constants.py
```python
# constants.py
TRANSACTION_TYPES = ["income", "expense"]
CONSENT_STATUSES = ["active", "revoked", "expired"]
CORS_ORIGINS = ["http://localhost:5000", "http://127.0.0.1:5000"]
```

### 7.3 Separar schemas em arquivo (REFACTOR)
**Problema:** schemas.py muito grande
**Solução:** schemas.py dedicado
```python
# schemas.py
from marshmallow import Schema, fields, validate

class TransactionSchema(Schema):
    ...
    
class InstallmentSchema(Schema):
    ...
```

### 7.4 Adicionar docstrings (DOCUMENTATION)
```python
@app.route("/api/users/<user_id>/transactions", methods=["POST"])
def create_transaction(user_id: str) -> tuple:
    """
    Cria uma nova transação para o usuário.
    
    Args:
        user_id: ID do usuário (obtido via OAuth)
        
    Returns:
        tuple: (JSON response, status_code)
        
    Raises:
        BadRequest: Se dados inválidos
        Unauthorized: Se usuário não autenticado
    """
```

---

## 8. PRIORITIZAÇÃO

### 🔴 CRÍTICO (Fazer agora):
1. Rate Limiting + CSRF
2. Gunicorn para produção
3. Database pooling
4. Input validation melhorado

### 🟠 IMPORTANTE (Sprint próxima):
5. Paginação
6. Soft Delete
7. Filtros avançados
8. Alembic migrations
9. Integration tests

### 🟡 NICE-TO-HAVE (Roadmap):
10. Categorias
11. Alertas/Metas
12. Prometheus metrics
13. Sentry integration
14. Load testing

---

## 9. CHECKLIST DE IMPLEMENTAÇÃO

- [ ] Rate Limiting com Flask-Limiter
- [ ] CSRF com Flask-WTF
- [ ] Paginação em endpoints de lista
- [ ] Índices em date, type, status
- [ ] Soft delete com deleted_at
- [ ] Gunicorn setup
- [ ] Database pooling
- [ ] Alembic migrations
- [ ] Documentação de APIs
- [ ] Integration tests
- [ ] Load tests

---

**Próximos passos recomendados:**
1. Implementar rate limiting + CSRF (1-2 horas)
2. Adicionar paginação (30 minutos)
3. Configurar Gunicorn (15 minutos)
4. Adicionar Alembic (1 hora)
