# Gestor Financeiro (Backend + Frontend)

Aplicação para gestão de finanças pessoais com:
- Frontend em HTML/CSS/JS puro, servido pelo próprio Flask em `/static/index.html`
- Backend Flask com persistência em SQLite ou PostgreSQL e API REST
- Autenticação via Google OAuth 2.0

## Arquitetura
| Camada | Tecnologia | Descrição |
|--------|------------|-----------|
| Backend | Flask + SQLAlchemy | API REST, persistência em `data.db` |
| Autenticação | Authlib + Google OAuth | Login com conta Google |
| Serialização | Marshmallow | Validação e formatação JSON |
| Frontend | `static/index.html` + `app.js` + `styles.css` | SPA em JS puro, sem build; consome a API com sessão autenticada e CSRF |
| Importação Simulada | Endpoint `/api/users/<user_id>/import` | Gera transações fictícias (Open Finance) |
| Open Finance Sync | Endpoint `/api/users/<user_id>/openfinance/sync` | Sincroniza transações via Open Finance (simulado) |
| Provider Abstração | `providers.py` | Facilita troca de provedor (simulado → real) |

## Instalação
Requer **Python 3.10 ou mais novo** (é o mínimo que os pinos de
`requirements.txt` aceitam).

Os launchers da seção **Executar** criam o ambiente virtual e instalam as
dependências sozinhos — normalmente você não precisa destes passos. Para fazer à
mão:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt    # Windows
```
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt        # Linux / macOS
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

### Jeito curto: os launchers

```powershell
start_backend.bat          # Windows — dá para executar com duplo clique
```
```bash
./run.sh                   # Linux / macOS / WSL
```

Os dois fazem exatamente o mesmo, nesta ordem, e são **idempotentes** — da
segunda vez em diante só sobem o servidor:

1. Acham o Python e conferem se é **3.10+** (o mínimo dos pinos em `requirements.txt`).
2. Criam `.venv/` se não existir.
3. Instalam `requirements.txt` **só quando o arquivo mudou** — o carimbo é um
   SHA-256 gravado em `.venv/.requirements-sha256`, calculado pelo mesmo
   one-liner Python nos dois sistemas (nada de `certutil` num e `sha256sum` no
   outro, que divergem em formato).
4. Criam um `.env` de desenvolvimento **se não existir um**, com
   `APP_ENV=development`, `ENABLE_DEV_LOGIN=true` e uma `FLASK_SECRET_KEY`
   gerada por `secrets.token_hex(32)`. O seu `.env` nunca é modificado. Sem
   chave fixa o backend gera uma aleatória a cada start e registra `CRITICAL`:
   sessão e token CSRF morrem em todo restart.
5. Rodam `alembic upgrade head`.
6. Sobem o servidor em **`http://127.0.0.1:5000`**.

| Opção | Efeito |
|---|---|
| `--port 8080` | muda a porta (padrão `5000`) |
| `--host 0.0.0.0` | muda o bind (padrão `127.0.0.1`) |
| `--reinstall` | força a reinstalação das dependências |
| `--no-migrate` | pula o `alembic upgrade head` |
| `--help` | imprime o resumo |

Precedência das variáveis, da mais forte para a mais fraca: **o seu ambiente →
o `.env` → o padrão do script**. Definir `PORT` no shell e rodar sem `--port`
respeita o seu `PORT`.

> **`127.0.0.1` e não `0.0.0.0` é deliberado.** O default do `backend.py` é
> `0.0.0.0`, o que exporia na rede local um servidor com `ENABLE_DEV_LOGIN=true`
> — e esse endpoint permite assumir a sessão de qualquer `user_id`. Passe
> `--host 0.0.0.0` conscientemente se precisar.

> **O bind em loopback também explica por que o launcher não serve para o
> preview/produção.** Nesses casos o bind precisa ser `0.0.0.0` e o servidor é o
> gunicorn — veja `startup.txt` e `deploy/README.md`.

### Jeito longo: à mão

```bash
APP_ENV=development ENABLE_DEV_LOGIN=true .venv/bin/python backend.py
```

Sem `APP_ENV` o backend assume **produção** (fail-closed): o dev-login é
desativado e o cookie de sessão sai marcado como `Secure`. É por isso que os
launchers definem o ambiente em vez de só chamar `python backend.py`.

O modo debug do Werkzeug **fica desligado por padrão** (`FLASK_DEBUG=true` para
ligar). Ele nunca deve ser ativado num host acessível: o console interativo
permite execução remota de código.

Host/porta configuráveis por `FLASK_RUN_HOST` e `PORT`.

**Entry points:**
| Uso | Comando |
|-----|---------|
| Desenvolvimento (Windows) | `start_backend.bat` |
| Desenvolvimento (Linux/macOS) | `./run.sh` |
| Produção (Azure/gunicorn) | `gunicorn ... wsgi:app` (ver `startup.txt`) |
| Flask CLI | `flask --app backend:create_app run` |
| Direto | `python backend.py` |

> O `start_backend.bat` usa o servidor de desenvolvimento do Flask, não o
> gunicorn: o gunicorn depende de `os.fork()` e **não roda em Windows nativo**.
> Em produção o alvo é Linux/Azure, onde `startup.txt` usa gunicorn normalmente.

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

**Resultado esperado:** todos os testes passando.

| Arquivo | O que cobre |
| --- | --- |
| `tests/test_phase1_security.py` | Regressões de segurança da Fase 1 (exposição de arquivos, dev-login, erros genéricos, webhook, dependências) |
| `tests/test_phase2_api.py` | Contrato da API da Fase 2 (CSRF, sessão de banco, rate limit, CORS, redirects) |
| `tests/test_phase2_frontend.py` | Frontend de referência e o fluxo completo que ele executa |
| `tests/test_deploy_config.py` | Artefatos de deploy (template de app settings do Azure, `startup.txt`) |

A auditoria de dependências roda localmente com:
```powershell
pip install pip-audit
pip-audit --strict -r requirements.txt
```

> Ambos os comandos também rodam no GitHub Actions antes do deploy para o
> Azure (job `build`), e **bloqueiam a publicação** em caso de falha.

## Deploy (Azure App Service)

O workflow `.github/workflows/main_gestão.yml` faz o build e o publish, mas **não
configura as variáveis de ambiente nem o comando de inicialização** — sem isso a
app sobe, responde 200 no health check e não funciona para ninguém.

Tudo o que é preciso está em **[`deploy/README.md`](deploy/README.md)**:

- `deploy/azure-appsettings.example.json` — template completo das 25+ variáveis
  que o backend lê, com o valor de produção recomendado para cada uma
  (placeholders marcados com `TROQUE_`);
- referências a **Key Vault** para os segredos;
- comando de inicialização e as armadilhas que derrubam o deploy
  (`--bind 0.0.0.0:8000`, `wsgi:app` e não `backend:app`, Startup Command do
  portal sobrescrevendo o `startup.txt`);
- escolha do banco (SQLite em `/home/data` para avaliação, PostgreSQL em
  produção) — o código é portátil entre os dois;
- **checklist pós-deploy** com os `curl` esperados e uma tabela de diagnóstico
  por sintoma.

## Base de Dados

O código é portátil entre **SQLite** e **PostgreSQL** — nada nas migrações ou nas
consultas usa recurso de um dialeto só. A connection string vem de
`DATABASE_URL` (padrão do Azure) ou `GF_DB_URL` (local), caindo em
`sqlite:///data.db`:

```powershell
$env:GF_DB_URL = "sqlite:///data.db"                                  # local
$env:GF_DB_URL = "postgresql+psycopg2://u:s@host:5432/financie"       # produção
```

### Tipos monetários

| Coluna | Tipo | Por quê |
| --- | --- | --- |
| `transactions.amount`, `installments.monthly_value` | `NUMERIC(14,2)` | Dinheiro. `FLOAT` é binário: `0.1` não tem representação exata e somar centavos deriva (`0.1 + 0.2 = 0.30000000000000004`). O resumo do usuário é exatamente uma soma longa de centavos. |
| `investments.amount`, `purchase_price`, `current_price` | `NUMERIC(20,8)` | Quantidade e cotação. Duas casas aqui **zerariam** uma posição de `0.00012345 BTC`. |

No PostgreSQL o valor é exato de ponta a ponta. No SQLite, que não tem tipo
decimal, o SQLAlchemy grava como real e devolve `Decimal` quantizado na leitura —
as somas em Python continuam exatas. A função `money()` normaliza `Decimal` e
`float` na borda JSON (`jsonify` não serializa `Decimal`).

### Migrações

O mecanismo oficial é o **Alembic**, e o `startup.txt` o aplica antes de servir:

```
alembic upgrade head && gunicorn ... wsgi:app
```

```powershell
alembic upgrade head        # aplica
alembic current             # em que revisão estou
alembic downgrade -1        # volta um passo
alembic upgrade head --sql   # só gera o SQL, sem tocar no banco (para um DBA revisar)
```

A URL **não** fica no `alembic.ini`: `alembic/env.py` chama `resolve_db_url()`, a
mesma resolução do aplicativo. Um valor fixo no `.ini` fazia `alembic upgrade
head` migrar o `data.db` local quando a intenção era o banco de produção.

As três revisões são idempotentes e portáveis:

| Revisão | O que faz |
| --- | --- |
| `46d24e28829d` | Cria as quatro tabelas (nasceu com `upgrade(): pass`, o que fazia a revisão seguinte falhar com *no such table* num banco novo) |
| `6a8a71d3da19` | Cria os índices de performance, inspecionando via `sa.inspect()` (a versão original consultava `sqlite_master`, que não existe no PostgreSQL) |
| `8f2c41ab7d05` | Converte `FLOAT` → `NUMERIC` nas colunas monetárias |

Um banco que já existia — criado pelo `create_all()` de um deploy anterior —
atravessa as três sem erro: cada criação é protegida por inspeção, e as guardas de
índice são separadas das de tabela (senão um banco existente nunca ganharia os
índices novos). A conversão de tipo usa `batch_alter_table`, que é o que permite
alterar coluna no SQLite.

O `Base.metadata.create_all()` continua no boot como **rede de segurança**: o
portal do Azure permite sobrescrever o comando de inicialização, e sem isto um
deploy com o comando errado não criaria tabela alguma. A diferença é que agora uma
falha de banco **derruba o boot** em vez de ser engolida — antes o aplicativo subia
"verde", o health check passava, o Azure trocava o slot e todo request devolvia
500.

Para redefinir um banco local: apague o ficheiro e rode `alembic upgrade head`.

## Arquivos Estáticos e Frontend
Somente o conteúdo de `static/` é servido pela web, sob `/static/<arquivo>`.

> ⚠️ **Não** volte a configuração para `static_folder='.'`: isso expõe pela web
> qualquer arquivo da raiz do projeto (`backend.py`, `.env`, `.git/config`).
> Coloque o frontend dentro de `static/`.

### O frontend de referência

`static/` contém a interface que consome esta API — **HTML, CSS e JavaScript
puros, sem build, sem npm e sem CDN**. Basta servir o app e abrir
`/static/index.html` no navegador.

| Arquivo | Papel |
| --- | --- |
| `static/index.html` | Estrutura: tela de login, abas, formulários e tabelas |
| `static/styles.css` | Tema escuro em CSS puro (variáveis CSS, sem framework) |
| `static/app.js` | Toda a lógica: CSRF, CRUD, painel, Open Finance |

Cobertura funcional:

- **Login** com Google (`/auth/login`) e, quando `ENABLE_DEV_LOGIN=true` em
  desenvolvimento, o botão *Entrar como dev*.
- **Painel** com resumo (renda, despesas avulsas, parcelas, saldo), sugestões
  geradas pelo backend e portfólio de investimentos.
- **CRUD completo** de transações, compras parceladas e investimentos, com
  filtros (`asset_type`, `status`) e paginação.
- **Open Finance**: criação de consentimento e sincronização, listando as
  sugestões importadas.

O frontend é a implementação de referência do contrato de segurança da Fase 2 e
serve de exemplo para qualquer cliente:

1. `GET /api/csrf-token` ao carregar a página — e **rejeita** o valor literal
   `N/A` que o endpoint devolvia antes da correção.
2. Envia o header **`X-CSRFToken`** em toda escrita (`POST`/`PUT`/`PATCH`/`DELETE`).
3. Usa `credentials: 'include'` para o cookie de sessão viajar.
4. Se uma escrita devolver **400 por CSRF**, renova o token e tenta **uma** vez.
5. Todas as URLs são **relativas** — o mesmo código roda em `localhost` e no
   Azure sem alteração.
6. Renderiza os `details` do Marshmallow em erros de validação e o `error_id` em
   erros 500 (para cruzar com o log), **sem** expor stack trace.

Como o backend serve o frontend, `FRONTEND_ORIGINS` em produção precisa conter
apenas o domínio do próprio app — não há origem diferente para autorizar.

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

### Ainda pendente (Fase 4)
- **`create_app()` tem ~1.400 linhas** com todas as rotas fechadas nela: quebrar em blueprints e extrair a lógica de negócio para serviços testáveis isoladamente.
- **Código morto**: `open_finance.py` (superseded por `providers.py`) e `LogContext` (importado, nunca usado).
- **Filtros em transações**: `?type=expense` e filtro por período não existem, embora `/suggestions` gere ações apontando para `?type=expense` — o link volta com a listagem completa.
- **Coluna `fingerprint` com índice único** `(user_id, fingerprint)` para a deduplicação do sync deixar de depender de varrer as transações do usuário.
- **Marcar parcelas como concluídas** explicitamente, em vez de derivar do tempo decorrido a cada leitura.
- **Lock completo de dependências** (`pip-compile`): hoje as transitivas (ex.: `limits`) são resolvidas no build.
- **`requirements-dev.txt`**: `pytest`/`pytest-cov` vão para produção junto com o resto.
- **`before_request` marca `session.permanent = True` em todo request**, inclusive anônimo e de asset estático.
- **`FLASK_SECRET_KEY` ainda gera chave aleatória** se ausente (com log CRITICAL): em produção isso invalida sessões a cada restart. Melhor seria falhar o boot.

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
{"error": "bad_request", "details": {"amount": ["Deve ser um valor positivo (mínimo 0.01)."]}}
```

Erros 500 nunca vazam stack trace nem configuração: devolvem
`{"error": "internal_error", "details": "Erro interno do servidor.", "error_id": "<16 hex>"}`,
e o `error_id` é o que permite cruzar a resposta com o log.

### Regras de entrada

`POST` e `PUT` usam **o mesmo schema**, então as regras são idênticas nos dois —
antes divergiam (o `PUT` rejeitava `amount <= 0` e o `POST` aceitava).

| Campo | Regra | Coluna no banco |
| --- | --- | --- |
| `amount`, `monthly_value` (transação/parcela) | `0.01` a `999999999999.99` | `NUMERIC(14,2)` |
| `amount` (investimento = quantidade) | `> 0`, aceita fração (`0.00012345`) | `NUMERIC(20,8)` |
| `purchase_price`, `current_price` | `>= 0` | `NUMERIC(20,8)` |
| `target_return` | `-100` a `10000` (%) | `FLOAT` |
| `description` | 1 a 255 caracteres | `String(255)` |
| `name` | 1 a 256 caracteres | `String(256)` |
| `notes` | até 1024 caracteres | `String(1024)` |
| `total_months` | 1 a 1200 | `Integer` |
| `type` | `income` \| `expense` | `String(16)` |
| `status` (investimento) | `active` \| `sold` \| `matured` | `String(32)` |
| `asset_type` | `stocks`, `reit`, `crypto`, `bonds`, `funds`, `savings`, `real_estate`, `commodities` | `String(64)` |

Os limites espelham as colunas de propósito: sem eles o SQLite aceitava uma
`description` de 5.000 caracteres enquanto o PostgreSQL devolveria 500 — a mesma
requisição funcionava ou não dependendo do dialeto.

Duas regras do `PUT` merecem destaque:

- **Campo desconhecido → 400.** Antes era ignorado em silêncio, então um erro de
  digitação (`ammount`) parecia ter funcionado.
- **`user_id` não é editável.** O campo existe no schema porque o `POST` precisa
  dele, mas a whitelist de atualização o exclui — sem isso um `PUT` transferiria o
  registro para outra conta.

### Sincronização Open Finance

Um item malformado vindo do banco **não aborta mais a importação inteira** (antes
um único item inválido devolvia 400 e nada era gravado). Ele é pulado, contado e
registrado em log:

```json
{"imported": 3, "skipped_duplicates": 0, "skipped_invalid": 1, "transactions": [...]}
```

A deduplicação agora considera **também** as linhas com soft delete: antes o filtro
`deleted_at IS NULL` fazia exatamente o oposto do esperado — apagar uma transação
importada a trazia de volta na sincronização seguinte.

## Limitações Atuais
- **Transações não têm filtro por período nem por tipo**, embora a paginação
  exista (investimentos filtram por `status` e `asset_type`). Como `/suggestions`
  gera ações apontando para `?type=expense`, o link volta com a listagem completa.
- **A deduplicação do sync varre as transações do usuário** a cada sincronização,
  em vez de usar uma coluna `fingerprint` com índice único.
- **Parcela concluída é derivada do tempo decorrido** a cada leitura, não marcada
  no registro.
- **`create_app()` tem ~1.400 linhas** com todas as rotas fechadas nela, o que
  dificulta testar a lógica de negócio isoladamente.
- `pytest` e `pytest-cov` estão no `requirements.txt` de produção, e as
  transitivas não têm lock completo.

## Próximos Passos Sugeridos
1. ~~Autenticação OAuth e derivar `user_id` da sessão~~ — **feito**
2. ~~Paginação~~ — **feito** · filtros por data/tipo em transações — pendente
3. ~~Considerar parcelas corretamente no summary~~ — **feito** (Fase 3) · marcar
   parcelas concluídas no registro — pendente
4. Exportação CSV / Excel
5. ~~Testes automatizados~~ — **197 testes** cobrindo resumo, sugestões,
   portfólio, validação, migrações, frontend, configuração de deploy e os
   launchers de desenvolvimento
6. ~~Rate limiting e logging estruturado (JSON)~~ — **feito**
7. ~~`Numeric(14,2)` para valores monetários + migração dos dados existentes~~ —
   **feito** (Fase 3, com `NUMERIC(20,8)` para quantidade/cotação de ativo)
8. ~~Alembic real (schema inicial portável, lendo `DATABASE_URL`)~~ — **feito**
   (Fase 3). O `create_all()` foi **mantido de propósito** como rede de segurança
   contra um Startup Command errado no portal; o que mudou é que falha de banco
   agora derruba o boot em vez de ser engolida.
9. Blueprints + camada de serviço
10. ~~Publicar o frontend em `static/`~~ — **feito** (Fase 2)
11. Redis como `RATELIMIT_STORAGE_URI` ao escalar para mais de uma instância

## Licença
Uso interno / educacional.
