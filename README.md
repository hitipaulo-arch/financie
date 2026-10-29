# Gestor Financeiro (Backend + Frontend)

Aplicação para gestão de finanças pessoais com:
- Frontend HTML + Tailwind + Google OAuth
- Backend Flask com persistência em SQLite e API REST
- Autenticação via Google OAuth 2.0

## Arquitetura
| Camada | Tecnologia | Descrição |
|--------|------------|-----------|
| Backend | Flask + SQLAlchemy | API REST, persistência em `data.db` |
| Autenticação | Authlib + Google OAuth | Login com conta Google |
| Serialização | Marshmallow | Validação e formatação JSON |
| Frontend | `index_api.html` | Interface REST com sessão autenticada |
| Importação Simulada | Endpoint `/api/users/<user_id>/import` | Gera transações fictícias (Open Finance) |
| Open Finance Sync | Endpoint `/api/users/<user_id>/openfinance/sync` | Sincroniza transações via Open Finance (simulado) |
| Provider Abstração | `providers.py` | Facilita troca de provedor (simulado → real) |

## Instalação
No diretório `gestor-financeiro`:
```powershell
pip install -r requirements.txt
```

## Configuração OAuth

### 1. Criar Credenciais Google
1. Acesse [Google Cloud Console](https://console.cloud.google.com/)
2. Crie um novo projeto ou selecione existente
3. Vá em **APIs & Services > Credentials**
4. Clique **Create Credentials > OAuth 2.0 Client ID**
5. Configure a tela de consentimento se necessário
6. Tipo de aplicação: **Web application**
7. Authorized redirect URIs: `http://localhost:5000/auth/callback`
8. Copie **Client ID** e **Client Secret**

### 2. Configurar Variáveis de Ambiente
Crie um arquivo `.env` na raiz do projeto:
```bash
FLASK_SECRET_KEY=sua_chave_secreta_aqui
GOOGLE_CLIENT_ID=seu_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=seu_client_secret
GF_DB_URL=sqlite:///data.db
OPEN_FINANCE_BASE_URL=https://api.openfinance.local
OPEN_FINANCE_CLIENT_ID=seu_of_client_id
OPEN_FINANCE_CLIENT_SECRET=seu_of_client_secret
```

**Gerar chave secreta:**
```python
import secrets
print(secrets.token_hex(32))
```

## Executar Backend
```powershell
python backend.py
```
Serve em `http://localhost:5000`.

Para desenvolvimento local com login sem Google:
```powershell
$env:APP_ENV = "development"
$env:ENABLE_DEV_LOGIN = "true"
python backend.py
```

O modo debug do Werkzeug **fica desligado por padrão** (`FLASK_DEBUG=true` para
ligar). Ele nunca deve ser ativado num host acessível: o console interativo
permite execução remota de código.

Host/porta configuráveis por `FLASK_RUN_HOST` e `PORT`.

**Entry points:**
| Uso | Comando |
|-----|---------|
| Produção (Azure/gunicorn) | `gunicorn ... wsgi:app` (ver `startup.txt`) |
| Flask CLI | `flask --app backend:create_app run` |
| Desenvolvimento | `python backend.py` |

> O módulo `backend` **não** cria o app no import (`from backend import Base`,
> usado pelo Alembic, não abre mais conexão com o banco). `backend.app` ainda
> existe por compatibilidade, mas é criado sob demanda.

## Testar Backend
```powershell
# Executar a suite de testes (regressões de segurança da Fase 1)
pytest tests/ -v

# Com coverage
pytest tests/ -v --cov=backend --cov-report=term-missing
```

**Resultado esperado:** 31 testes passando (`tests/test_phase1_security.py`).

A auditoria de dependências roda localmente com:
```powershell
pip install pip-audit
pip-audit --strict -r requirements.txt
```

> Ambos os comandos também rodam no GitHub Actions antes do deploy para o
> Azure (job `build`), e **bloqueiam a publicação** em caso de falha.

## Base de Dados
SQLite criada automaticamente (`data.db`). Para redefinir: apagar o ficheiro antes de iniciar.

## Arquivos Estáticos
Somente o conteúdo de `static/` é servido pela web, sob `/static/<arquivo>`.

> ⚠️ **Não** volte a configuração para `static_folder='.'`: isso expõe pela web
> qualquer arquivo da raiz do projeto (`backend.py`, `.env`, `.git/config`).
> Coloque o frontend dentro de `static/`.

## Endpoints de Autenticação
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/auth/login` | Redireciona para login Google |
| GET | `/auth/callback` | Callback OAuth após autenticação |
| GET | `/auth/logout` | Encerra sessão do usuário |
| GET | `/auth/me` | Retorna dados do usuário logado |

**Exemplo resposta `/auth/me`:**
```json
{
  "user_id": "112233445566778899",
  "email": "usuario@gmail.com",
  "name": "Nome do Usuário",
  "picture": "https://lh3.googleusercontent.com/..."
}
```

## Endpoints Principais
Todos os endpoints são namespaced por `user_id` (obtido via OAuth). Requer sessão autenticada.

### Health
- `GET /api/health` → Status simples.

### Transações
- `GET /api/users/<user_id>/transactions` → Lista transações.
- `POST /api/users/<user_id>/transactions` → Cria.
  - Campos: `description`, `amount`, `type` (income|expense), opcional `date` (YYYY-MM-DD).
- `PUT/PATCH /api/users/<user_id>/transactions/<id>` → Atualiza parcial.
- `DELETE /api/users/<user_id>/transactions/<id>` → Remove.

### Parcelas (Compras Parceladas)
- `GET /api/users/<user_id>/installments`
- `POST /api/users/<user_id>/installments`
  - Campos: `description`, `monthly_value`, `total_months`, opcional `date_added`.
- `PUT/PATCH /api/users/<user_id>/installments/<id>`
- `DELETE /api/users/<user_id>/installments/<id>`

### Resumo
- `GET /api/users/<user_id>/summary` → `{ income, expenses_avulsa, expenses_parcelas, expenses_total, balance }`.

### Importação Simulada
- `POST /api/users/<user_id>/import` → Cria lote de 3 transações fictícias.

### Open Finance (Sincronização Simulada)
- `POST /api/users/<user_id>/openfinance/sync` → Busca transações em instituições financeiras (simulado) e insere no banco.

#### Como funciona (simulado)
1. Endpoint chama serviço em `open_finance.py`.
2. Serviço gera lista estática de transações (substituir por chamadas reais).
3. Cada transação é validada via `TransactionSchema` e persistida.
4. Retorno inclui quantidade importada e origem.

#### Para integrar de verdade
- Obtenha credenciais junto a provedores/aggregators de Open Finance.
- Implemente fluxo de consentimento do usuário.
- Armazene consentId e refresh tokens conforme especificação BACEN.
- Substitua `fetch_transactions` por requisições reais (ex: `/accounts/{id}/transactions`).
- Trate paginação, datas e reconciliação (evitar duplicados).

#### Exemplo de resposta
```json
{
  "status": "success",
  "source": "open_finance_simulated",
  "imported": 3,
  "transactions": [
    {"id": 42, "description": "Depósito Open Finance", "amount": 987.65, "type": "income", "date": "2025-11-24"},
    {"id": 43, "description": "Supermercado Open Finance", "amount": 152.30, "type": "expense", "date": "2025-11-24"},
    {"id": 44, "description": "Boleto Energia", "amount": 210.15, "type": "expense", "date": "2025-11-24"}
  ]
}
```

### Consentimento Open Finance (Simulado)
Antes de sincronizar é necessário um consentimento ativo do usuário.

Endpoints:
- `POST /api/users/<user_id>/openfinance/consents` cria consentimento (gera `consent_id` se omitido).
- `GET /api/users/<user_id>/openfinance/consents` lista consentimentos (mais recente primeiro).

Campos ao criar (POST):
| Campo | Obrigatório | Default se omitido |
|-------|-------------|--------------------|
| `consent_id` | não | hash aleatório (token_hex) |
| `provider` | não | `simulated` |
| `scopes` | não | `accounts:read transactions:read` |
| `status` | não | `active` |

Fluxo para sync:
1. Criar consent ativo.
2. Chamar `POST /api/users/<user_id>/openfinance/sync`.
3. Resposta inclui `consent_id` usado.

Erro sem consentimento:
```json
{"error": "no_active_consent", "details": "Nenhum consent ativo encontrado para este usuário."}
```

### Deduplicação de Transações
Durante a sincronização, transações já existentes são ignoradas usando uma "impressão digital" composta de:
`date | type | amount | description(normalizada em minúsculas)`.

Resposta da sync inclui campo `skipped_duplicates` com a quantidade ignorada.

### Provider Abstração
Arquivo `providers.py` define:
- `BaseProvider` (interface mínima)
- `SimulatedProvider` (retorna lista fixa)

O endpoint de sync usa a abstração (`provider.sync(...)`). Para integrar um provedor real, criar nova classe implementando `fetch_transactions`.

## CSRF (obrigatório em toda escrita)

Toda requisição `POST`, `PUT`, `PATCH` ou `DELETE` exige um token CSRF. `GET`,
`HEAD` e `OPTIONS` nunca exigem.

Fluxo do cliente:
```js
// 1) obter o token (uma vez por sessão — ele é reutilizável)
const { csrf_token } = await fetch('/api/csrf-token', { credentials: 'include' }).then(r => r.json());

// 2) enviar no header em toda escrita
await fetch(`/api/users/${userId}/transactions`, {
  method: 'POST',
  credentials: 'include',
  headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf_token },
  body: JSON.stringify({ description: 'Salário', amount: 5000, type: 'income' }),
});
```

Headers aceitos: `X-CSRFToken` ou `X-CSRF-Token`. Em formulários, o campo
`csrf_token`.

O token não expira antes da sessão (`WTF_CSRF_TIME_LIMIT=None`); a sessão dura
`SESSION_LIFETIME_MINUTES` (padrão 120).

**Únicas isenções** (documentadas no decorador):
| Rota | Por quê |
|------|---------|
| `POST /api/openfinance/webhook` | Chamada por serviço externo; autenticada por HMAC (`X-Webhook-Signature`) |
| `POST /auth/dev-login` | Só existe fora de produção e o chamador ainda não tem sessão |

Sem token a resposta é `400`:
```json
{"error": "bad_request", "details": "The CSRF token is missing."}
```

> Em produção (HTTPS), o Flask-WTF também exige que o header `Referer` confira
> com o host (`WTF_CSRF_SSL_STRICT`, padrão `true`). Clientes de API que não são
> navegador precisam enviar `Referer` ou definir `WTF_CSRF_SSL_STRICT=false`.

## Exemplos `curl`
```bash
BASE=http://localhost:5000
JAR=/tmp/cookies.txt

# 0) autenticar (apenas em desenvolvimento, com ENABLE_DEV_LOGIN=true)
curl -c $JAR -X POST $BASE/auth/dev-login \
  -H "Content-Type: application/json" -d '{"user_id":"demo"}'

# 1) obter o token CSRF
TOKEN=$(curl -s -b $JAR -c $JAR $BASE/api/csrf-token | python -c "import sys,json;print(json.load(sys.stdin)['csrf_token'])")

# 2) criar transação
curl -b $JAR -c $JAR -X POST $BASE/api/users/demo/transactions \
  -H "Content-Type: application/json" -H "X-CSRFToken: $TOKEN" \
  -d '{"description":"Salário","amount":5000,"type":"income"}'

# 3) atualizar / remover
curl -b $JAR -c $JAR -X PUT $BASE/api/users/demo/transactions/1 \
  -H "Content-Type: application/json" -H "X-CSRFToken: $TOKEN" -d '{"amount":6000}'
curl -b $JAR -c $JAR -X DELETE $BASE/api/users/demo/transactions/1 -H "X-CSRFToken: $TOKEN"

# Leituras não precisam de token
curl -b $JAR $BASE/api/users/demo/transactions
curl -b $JAR $BASE/api/users/demo/summary

# Importar extrato simulado
curl -b $JAR -c $JAR -X POST $BASE/api/users/demo/import -H "X-CSRFToken: $TOKEN"
```

## Variáveis de Ambiente
| Nome | Função | Default |
|------|--------|---------|
| `APP_ENV` | `production` ou `development`. Sem ela o backend assume **produção** (fail-closed) | `production` |
| `SECRET_KEY` / `FLASK_SECRET_KEY` | Chave de sessão. Obrigatória em produção (sem ela as sessões caem a cada restart) | aleatória ⚠️ |
| `DATABASE_URL` / `GF_DB_URL` | URL da base (SQLAlchemy) | `sqlite:///data.db` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Credenciais OAuth do Google | — |
| `ENABLE_DEV_LOGIN` | Libera `POST /auth/dev-login`. **Ignorada em produção** | `false` |
| `OPENFINANCE_ENABLE_REAL` | Usa o provider real de Open Finance em vez do simulado | `false` |
| `OPENFINANCE_WEBHOOK_SECRET` | Segredo HMAC do webhook. Sem ele o endpoint responde **503** | — |
| `SESSION_COOKIE_SECURE` | Cookie de sessão só por HTTPS | `true` em produção |
| `SESSION_COOKIE_HTTPONLY` | Cookie inacessível via JavaScript | `true` |
| `SESSION_COOKIE_SAMESITE` | Política SameSite do cookie | `Lax` |
| `SESSION_LIFETIME_MINUTES` | Duração da sessão | `120` |
| `LOG_LEVEL` | Nível do log estruturado JSON | `INFO` |
| `FRONTEND_ORIGINS` | Origens autorizadas no CORS (separadas por vírgula) | `http://localhost:5000,http://127.0.0.1:5000` |
| `APP_BASE_URL` | URL pública da app; base do redirect pós-login | derivada do request |
| `POST_LOGIN_PATH` | Caminho interno para onde ir após o login Google | `/static/index.html` |
| `TRUSTED_PROXY_COUNT` | Proxies reversos confiáveis (Azure App Service = 1) | `1` |
| `RATELIMIT_STORAGE_URI` | Backend do rate limiter. `memory://` conta por instância; use Redis se escalar | `memory://` |
| `RATELIMIT_ENABLED` | Liga/desliga o rate limiting (útil em testes) | `true` |
| `WTF_CSRF_SSL_STRICT` | Em HTTPS, exige `Referer` igual ao host | `true` |
| `FLASK_DEBUG` | Modo debug do Werkzeug **apenas** em `python backend.py` | `false` |
| `FLASK_RUN_HOST` / `PORT` | Host e porta do servidor de desenvolvimento | `0.0.0.0` / `5000` |

> `RATELIMIT_STORAGE_URI=redis://...` exige o extra `limits[redis]`
> (`pip install limits[redis]`), que não vem no `requirements.txt`. Sem o
> pacote o app **não sobe** — de propósito, para não silenciar a configuração.

Exemplo para usar outro ficheiro:
```powershell
$env:GF_DB_URL = "sqlite:///finance_test.db"
python backend.py
```

## Segurança

Regras em vigor desde a Fase 1 (2026-10-29):

| Tema | Comportamento |
|------|---------------|
| **Ambiente** | `APP_ENV` ausente ⇒ produção. No Azure (`WEBSITE_SITE_NAME` presente) o modo desenvolvimento nunca é ativado, mesmo com `APP_ENV=development`. |
| **Arquivos estáticos** | Só `static/` é público. Código-fonte, `.env` e `.git/` não são servidos. |
| **`/auth/dev-login`** | Desativado por padrão; exige `ENABLE_DEV_LOGIN=true` **e** ambiente não-produtivo. Caso contrário responde `403 dev_login_disabled`. |
| **Erros 500** | O corpo traz apenas `{"error":"internal_error","details":"Erro interno do servidor.","error_id":"<16 hex>"}`. O stack trace completo vai para o log com o mesmo `error_id` — cite esse código ao relatar um problema. |
| **Validação** | `ValidationError` do Marshmallow responde `400 bad_request` (nunca 500). |
| **Webhook Open Finance** | Exige `OPENFINANCE_WEBHOOK_SECRET`; sem ele responde `503`. Com ele, exige header `X-Webhook-Signature` (HMAC-SHA256 do corpo, aceito como `<hex>` ou `sha256=<hex>`), comparado em tempo constante. |
| **Cookies** | `Secure` por padrão em produção, `HttpOnly` sempre, `SameSite=Lax`. |
| **Dependências** | Todas fixadas em `requirements.txt`; `pip-audit --strict` roda no CI e bloqueia o deploy. |

Regras acrescentadas na Fase 2:

| Tema | Comportamento |
|------|---------------|
| **CSRF** | Política uniforme: toda rota que muda estado exige o token de `GET /api/csrf-token` no header `X-CSRFToken`. Só duas isenções, ambas documentadas (webhook e dev-login). Antes havia 18 `@csrf.exempt` avulsos e o endpoint de token devolvia `"N/A"` — 6 endpoints de escrita estavam inutilizáveis. |
| **Sessão de banco** | `teardown_appcontext` faz `rollback()` em erro e `remove()` ao fim de **todo** request. Antes a sessão scoped ficava presa à thread do worker e um request que falhava no meio deixava alterações pendentes que o request seguinte commitava. |
| **Rate limiting** | Default folgado (`500/hora`, `5000/dia`) e isenção para `/api/health`, `/`, `/api/csrf-token` e estáticos. Limites apertados ficam em autenticação (`/auth/login` 5/min, `/auth/callback` 10/min, `/auth/dev-login` 5/min) e nas rotas de escrita. |
| **Proxy reverso** | `ProxyFix` com `TRUSTED_PROXY_COUNT` (padrão 1, o do Azure). Sem isso `remote_addr` era o IP do balanceador — todos os usuários dividiam o mesmo balde de rate limit — e `url_for(_external=True)` gerava `http://` em vez de `https://`. |
| **CORS / redirect** | `FRONTEND_ORIGINS`, `APP_BASE_URL` e `POST_LOGIN_PATH` vêm de env. O caminho do redirect é sanitizado (`internal_path`) contra open redirect (`//evil.com`, URL absoluta). |
| **Debug** | `app.run(debug=True)` com bind `0.0.0.0` expunha o console do Werkzeug (RCE). Debug agora é opt-in via `FLASK_DEBUG` e nunca liga por padrão. |
| **Import sem efeitos colaterais** | `backend` não cria mais o app no import: o Alembic (`from backend import Base`) deixava de abrir conexão/`create_all()`, e o `wsgi.py` não inicializa tudo duas vezes. |

### Ainda pendente (Fases 3–4)
- **Dinheiro em `Float`** e `amount` negativo/zero aceito no `POST` de transações (o `PUT` valida `> 0`).
- **Parcelas contadas para sempre** no summary: `expenses_parcelas` soma `monthly_value` de todas as parcelas, ignorando `total_months` e o tempo decorrido.
- **Dedup da sync ignora soft-deleted**: transação apagada volta na próxima sincronização.
- **Fallback silencioso para `sqlite:///:memory:`** quando o engine falha.
- **Migrações Alembic vazias** (`upgrade(): pass`) e específicas de SQLite (`sqlite_master`), com `alembic.ini` ignorando `DATABASE_URL`.
- **Fase 4**: quebrar `create_app()` (~1.400 linhas) em blueprints, remover código morto (`open_finance.py`, `LogContext`), agregações em SQL no summary/suggestions e reescrever as seções desatualizadas deste README.

## Rate limiting

| Rota | Limite |
|------|--------|
| `/auth/login` | 5/min |
| `/auth/callback` | 10/min |
| `/auth/dev-login` | 5/min |
| `/api/users/<id>/openfinance/sync` | 10/hora |
| `/api/users/<id>/openfinance/consents` (POST) | 20/hora |
| `/api/users/<id>/import` | 20/hora |
| `/api/users/<id>/suggestions` | 50/hora |
| `/api/users/<id>/investments/portfolio` | 50/hora |
| `/api/investments/tips` | 50/hora |
| `/api/openfinance/webhook` | 100/hora |
| escritas de transações/parcelas/investimentos | 100/hora |
| qualquer outra rota | 500/hora e 5000/dia |
| `/api/health`, `/`, `/api/csrf-token`, `/static/*` | isentas |

Contagem por IP real do cliente (via `ProxyFix`). Com `RATELIMIT_STORAGE_URI=memory://`
cada instância conta separadamente — aponte para Redis ao escalar horizontalmente.
Resposta ao exceder: `429`.

## Validação & Erros
Erros retornam JSON:
```json
{"error": "bad_request", "details": {"amount": ["Valor inválido"]}}
```

## Limitações Atuais
- **Não há frontend neste repositório**: `static/` está vazio, então o redirect
  pós-login (`POST_LOGIN_PATH`) aponta para um arquivo que ainda não existe.
- `amount` é armazenado como `Float` e o `POST` de transações aceita valor
  negativo/zero (o `PUT` valida `> 0`) — o summary pode ficar invertido.
- O summary soma `monthly_value` de **todas** as parcelas, ignorando
  `total_months` e o tempo decorrido: parcela quitada continua contando como
  despesa mensal.
- Listagens têm paginação, mas transações não têm filtro por período/tipo
  (investimentos filtram por `status` e `asset_type`).
- Agregações (summary, suggestions, portfolio) somam em Python sobre todas as
  linhas do usuário, não em SQL.
- Migrações Alembic são no-op e específicas de SQLite; quem cria o schema é o
  `create_all()` no boot.

## Próximos Passos Sugeridos
1. ~~Autenticação OAuth e derivar `user_id` da sessão~~ — **feito**
2. ~~Paginação~~ — **feito** · filtros por data/tipo em transações — pendente
3. Marcar parcelas concluídas e considerá-las corretamente no summary
4. Exportação CSV / Excel
5. ~~Testes automatizados~~ — **61 testes** (Fases 1 e 2); ampliar para
   summary, suggestions e portfolio
6. ~~Rate limiting e logging estruturado (JSON)~~ — **feito**
7. `Numeric(14,2)` para valores monetários + migração dos dados existentes
8. Alembic real (schema inicial portável, lendo `DATABASE_URL`) e remover o
   `create_all()` do boot
9. Blueprints + camada de serviço (`create_app()` tem ~1.400 linhas)
10. Publicar o frontend em `static/`
11. Redis como `RATELIMIT_STORAGE_URI` ao escalar para mais de uma instância

## Licença
Uso interno / educacional.
