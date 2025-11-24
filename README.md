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

**Atalho Windows:**
```powershell
.\start_backend.bat
# ou
.\start_backend.ps1
```

## Testar Backend
```powershell
# Executar suite de testes
pytest test_backend.py -v

# Com coverage
pytest test_backend.py -v --cov=backend --cov-report=term-missing
```

**Resultado esperado:** 20 testes passando, cobertura ~85%.

## Base de Dados
SQLite criada automaticamente (`data.db`). Para redefinir: apagar o ficheiro antes de iniciar.

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

## Exemplos `curl`
```bash
# Criar transação
curl -X POST http://localhost:5000/api/users/demo/transactions \
  -H "Content-Type: application/json" \
  -d '{"description":"Salário","amount":5000,"type":"income"}'

# Listar transações
curl http://localhost:5000/api/users/demo/transactions

# Resumo
curl http://localhost:5000/api/users/demo/summary

# Importar extrato simulado
curl -X POST http://localhost:5000/api/users/demo/import
```

## Variáveis de Ambiente
| Nome | Função | Default |
|------|--------|---------|
| `GF_DB_URL` | URL da base (SQLAlchemy) | `sqlite:///data.db` |

Exemplo para usar outro ficheiro:
```powershell
$env:GF_DB_URL = "sqlite:///finance_test.db"
python backend.py
```

## Validação & Erros
Erros retornam JSON:
```json
{"error": "bad_request", "details": {"amount": ["Valor inválido"]}}
```

## Limitações Atuais
- Sem autenticação real no backend.
- Frontend ainda usa Firestore; para integrar totalmente com a API seria necessário substituir chamadas por fetch aos endpoints.
- Sem paginação (adequado apenas para volume pequeno de registros).

## Próximos Passos Sugeridos
1. Autenticação JWT/OAuth e derivar `user_id` automaticamente.
2. Paginação e filtros (por data / tipo) em transações.
3. Marcar parcelas concluídas (reduzir `total_months`).
4. Exportação CSV / Excel.
5. Testes automatizados (Pytest) para endpoints críticos.
6. Rate limiting e logging estruturado (JSON) para produção.

## Licença
Uso interno / educacional.
