# Deploy no Azure App Service

Este diretório contém o necessário para publicar o Gestor Financeiro num
**App Service Linux (Python)**. O workflow `.github/workflows/main_gestão.yml`
já faz o build e o publish; o que ele **não** faz é configurar as variáveis de
ambiente nem o comando de inicialização — e sem isso a aplicação sobe, responde
200 no health check e não funciona para ninguém.

> ⚠️ **Não aplique `azure-appsettings.example.json` como está.** Todo valor
> começando com `TROQUE_` é um placeholder. Confira antes:
>
> ```bash
> grep -c TROQUE_ deploy/azure-appsettings.example.json   # deve ser 0 antes de aplicar
> ```

## 1. Configurar as variáveis de ambiente

Copie o exemplo, preencha e aplique:

```bash
cp deploy/azure-appsettings.example.json /tmp/appsettings.json
# edite /tmp/appsettings.json

az webapp config appsettings set \
  --name gestao --resource-group SEU_RG \
  --slot Production \
  --settings @/tmp/appsettings.json
```

Confira o resultado (o Azure mascara segredos):

```bash
az webapp config appsettings list --name gestao --resource-group SEU_RG \
  --query "[].name" -o table
```

### Segredos no Key Vault (recomendado)

Em vez de gravar o segredo como texto no App Service, aponte para o Key Vault.
A referência precisa ser o **valor inteiro** da configuração:

```json
{
  "FLASK_SECRET_KEY": "@Microsoft.KeyVault(SecretUri=https://SEU-VAULT.vault.azure.net/secrets/flask-secret-key/)",
  "GOOGLE_CLIENT_SECRET": "@Microsoft.KeyVault(SecretUri=https://SEU-VAULT.vault.azure.net/secrets/google-client-secret/)",
  "OPENFINANCE_WEBHOOK_SECRET": "@Microsoft.KeyVault(SecretUri=https://SEU-VAULT.vault.azure.net/secrets/openfinance-webhook-secret/)"
}
```

Requisitos: a **managed identity** do App Service precisa de `get` no segredo
(`Key Vault Secrets User`) e o vault deve aceitar acesso por RBAC. Não dá para
embutir a referência no meio de uma connection string — para o banco, use uma
senha curta ou autenticação por identidade.

### O que cada variável faz

| Variável | Por que existe |
| --- | --- |
| `APP_ENV=production` | Sem ela o backend **já assume produção** (fail-closed), mas defina explicitamente. Controla dev-login e cookie `Secure`. |
| `FLASK_SECRET_KEY` | Assina o cookie de sessão e o token CSRF. **Se faltar, o backend gera uma chave aleatória e registra um log CRITICAL**: todo restart invalida as sessões e, com mais de uma instância, cada uma tem uma chave diferente — login e CSRF falham intermitentemente. Gere com `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `GF_DB_URL` | Connection string do banco. Aceita `postgresql+psycopg2://…` (psycopg2 já está no `requirements.txt`) ou `sqlite:////home/data/financie.db`. Veja a seção **Banco de dados**. |
| `APP_BASE_URL` | URL pública (`https://SEU-APP.azurewebsites.net`). Base do redirect pós-login e de URLs absolutas. Sem ela o backend deriva do request — o que só sai correto porque aplicamos `ProxyFix`. |
| `FRONTEND_ORIGINS` | Origens autorizadas no CORS **com credenciais**. Sem isto o navegador não recebe `Access-Control-Allow-Origin` e nenhuma chamada da UI funciona. Como o frontend é servido pelo próprio app (`/static/…`), basta o domínio do app. Separe várias por vírgula. |
| `POST_LOGIN_PATH` | Destino interno após o callback do Google. Padrão `/static/index.html`, que é o frontend deste repositório. Valores absolutos ou `//host` são revertidos para `/` (anti open-redirect). |
| `TRUSTED_PROXY_COUNT=1` | Quantos proxies confiáveis existem na frente. Azure App Service = **1**. É o que faz `request.is_secure` e `request.host` refletirem o HTTPS público. |
| `SESSION_COOKIE_*` | `Secure=true` em produção é obrigatório (o tráfego é HTTPS). `SameSite=Lax` permite o redirect do Google. |
| `WTF_CSRF_SSL_STRICT` | Em HTTPS, exige que o `Referer` confira com o host. É o default do Flask-WTF e o navegador sempre envia; mantenha `true`. Só desligue se integrar um cliente que não é navegador. |
| `ENABLE_DEV_LOGIN=false` | `POST /auth/dev-login` permite assumir a sessão de qualquer `user_id`. O backend **já ignora** este valor em produção e quando `WEBSITE_SITE_NAME` existe (ou seja, no Azure), mas deixe explícito. |
| `RATELIMIT_STORAGE_URI` | `memory://` conta por processo/instância. **Com mais de uma instância ou worker, use Redis** (`redis://…`) e adicione o extra `limits[redis]` ao `requirements.txt`, senão o boot falha com `ConfigurationError`. |
| `OPENFINANCE_*` | Sem `OPENFINANCE_WEBHOOK_SECRET` o endpoint de webhook responde **503** (fail-closed) em vez de aceitar eventos não autenticados. `OPENFINANCE_ENABLE_REAL=true` só com certificado e chave mTLS montados. |
| `LOG_LEVEL` | `INFO` em produção; `DEBUG` só para investigar um incidente. |

Não defina `WEBSITE_SITE_NAME`: o Azure injeta sozinho. A presença dela é um dos
sinais que o backend usa para concluir que está no Azure e desativar o dev-login.

## 2. Comando de inicialização

O repositório já traz `startup.txt`, que o App Service usa automaticamente:

```
gunicorn --workers 1 --worker-class sync --bind 0.0.0.0:8000 --timeout 60 --access-logfile - --error-logfile - wsgi:app
```

Pontos que costumam derrubar o deploy:

- **`--bind 0.0.0.0:8000`** — o App Service encaminha para a porta 8000 por
  padrão. Bind em `127.0.0.1` resulta em "container didn't respond to HTTP
  pings" e o deploy falha.
- **`wsgi:app`** — o gunicorn importa o objeto `app` de `wsgi.py`. Não use
  `backend:app`: `backend.py` expõe `app` de forma preguiçosa (PEP 562) para não
  criar o aplicativo no import.
- **`--workers 1`** — com `RATELIMIT_STORAGE_URI=memory://` e sessões em cookie,
  mais workers ainda funcionam, mas o rate limit passa a contar por worker. Se
  escalar, use Redis e aí pode subir os workers.
- Se o portal tiver um **Startup Command** personalizado em
  *Configuration → General settings*, ele **sobrescreve** o `startup.txt`.
  Confira se não há nada antigo apontando para `backend:app` ou porta 5000.

Para aplicar manualmente via CLI:

```bash
az webapp config set --name gestao --resource-group SEU_RG \
  --startup-file "gunicorn --workers 1 --worker-class sync --bind 0.0.0.0:8000 --timeout 60 --access-logfile - --error-logfile - wsgi:app"
```

## 3. Banco de dados

O código é portátil entre **SQLite** e **PostgreSQL** (as migrações não usam
nada específico de dialeto). Escolha conforme o cenário:

| Cenário | `GF_DB_URL` | Observações |
| --- | --- | --- |
| Teste/avaliação, 1 instância | `sqlite:////home/data/financie.db` | Só `/home` persiste no App Service Linux; `/tmp` é apagado a cada restart. Não é compartilhado entre instâncias e não tem backup do Azure. |
| Produção | `postgresql+psycopg2://usuario:senha@SEU-SERVER.postgres.database.azure.com:5432/financie?sslmode=require` | Use *Azure Database for PostgreSQL Flexible Server*. Habilite `Enforce SSL` e permita o acesso pela rede do App Service. |

Crie o diretório antes do primeiro boot quando usar SQLite:

```bash
az webapp ssh --name gestao --resource-group SEU_RG   # mkdir -p /home/data
```

O backend também executa `Base.metadata.create_all()` no boot como rede de
segurança, então um deploy sem migração aplicada ainda cria as tabelas. O
mecanismo correto, porém, é o Alembic — veja a seção **Migrações** no README
principal.

## 4. Checklist pós-deploy

Substitua `https://SEU-APP.azurewebsites.net` pela URL real:

```bash
BASE=https://SEU-APP.azurewebsites.net

curl -s -o /dev/null -w '%{http_code}\n' $BASE/api/health          # 200
curl -s -o /dev/null -w '%{http_code}\n' $BASE/static/index.html   # 200
curl -s -o /dev/null -w '%{http_code}\n' $BASE/backend.py          # 404
curl -s -X POST $BASE/api/openfinance/webhook                      # 503 sem segredo
curl -s -X POST $BASE/auth/dev-login -H 'Content-Type: application/json' \
     -d '{"user_id":"x"}'                                           # 403 dev_login_disabled
curl -s $BASE/api/csrf-token                                       # token real, nunca "N/A"
```

Depois, no navegador: abra `/static/index.html`, clique em **Entrar com
Google**, confirme que volta para a mesma página (e não para um 404) e que o
painel carrega os números.

Se o login com Google falhar, confira no console do Google se
`https://SEU-APP.azurewebsites.net/auth/callback` está cadastrado como
*Authorized redirect URI*.

## 5. Diagnóstico rápido

| Sintoma | Causa provável |
| --- | --- |
| 403 `dev_login_disabled` ao testar localmente com `APP_ENV=production` | Correto: o endpoint está desativado em produção. |
| Login funciona, mas toda escrita devolve 400 `csrf_token_missing` | O cliente não enviou `X-CSRFToken`, ou o cookie de sessão não viajou (`FRONTEND_ORIGINS`/CORS ou `SameSite`). |
| Sessões caem sozinhas ou CSRF falha intermitentemente | `FLASK_SECRET_KEY` ausente (chave aleatória por boot) ou diferente entre instâncias. |
| `ConfigurationError` no boot | `RATELIMIT_STORAGE_URI=redis://…` sem o extra `limits[redis]` instalado. |
| Health check do Azure marca a app indisponível | Startup command apontando para a porta errada ou `backend:app`. |
| Redirect pós-login cai em 404 | `POST_LOGIN_PATH` aponta para um arquivo que não existe em `static/`. |
