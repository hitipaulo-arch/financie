# Guia Rápido - Como Usar o Gestor Financeiro

## 🚀 Iniciando o Servidor

### Opção 1: Script Simples
```bash
cd gestor-financeiro
python start_server.py
```

### Opção 2: Comando Direto
```bash
cd gestor-financeiro
python backend.py
```

O servidor iniciará em: **http://127.0.0.1:5000**

## 📝 Testando os Endpoints

### ⚠️ IMPORTANTE: Login de Desenvolvimento

Antes de testar qualquer endpoint, você precisa fazer login:

```powershell
$body = @{
    user_id = "test_user"
    email = "test@example.com"
    name = "Test User"
} | ConvertTo-Json

Invoke-RestMethod -Uri http://127.0.0.1:5000/auth/dev-login -Method POST -Body $body -ContentType "application/json" -SessionVariable websession

# Agora use a variável $websession em todas as requisições
```

### Opção 1: Script de Teste Automático
```bash
# Em outro terminal (deixe o servidor rodando)
cd gestor-financeiro
python test_openfinance.py
```

### Opção 2: Usando cURL (PowerShell)

#### 0. Login (OBRIGATÓRIO)
```powershell
$body = @{
    user_id = "test_user"
    email = "test@example.com"
    name = "Test User"
} | ConvertTo-Json

$login = Invoke-RestMethod -Uri http://127.0.0.1:5000/auth/dev-login -Method POST -Body $body -ContentType "application/json" -SessionVariable websession

Write-Host "✅ Login bem-sucedido: $($login.user.email)"
```

#### 1. Health Check
```powershell
Invoke-RestMethod -Uri http://127.0.0.1:5000/api/health
```

#### 2. Criar Transação
```powershell
$body = @{
    description = "Salário"
    amount = 5000.00
    type = "income"
    date = "2025-11-25"
} | ConvertTo-Json

Invoke-RestMethod -Uri http://127.0.0.1:5000/api/users/test_user/transactions -Method POST -Body $body -ContentType "application/json" -WebSession $websession
```

#### 3. Listar Transações
```powershell
Invoke-RestMethod -Uri http://127.0.0.1:5000/api/users/test_user/transactions -WebSession $websession
```

#### 4. Criar Consent Open Finance
```powershell
$body = @{} | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:5000/api/users/test_user/openfinance/consents -Method POST -Body $body -ContentType "application/json" -WebSession $websession
```

#### 5. Listar Consents
```powershell
Invoke-RestMethod -Uri http://127.0.0.1:5000/api/users/test_user/openfinance/consents -WebSession $websession
```

#### 6. Sincronizar Transações do Open Finance
```powershell
Invoke-RestMethod -Uri http://127.0.0.1:5000/api/users/test_user/openfinance/sync -Method POST -ContentType "application/json" -WebSession $websession
```

### Opção 3: Usando Postman ou Insomnia

1. **Criar uma Collection** com a base URL: `http://127.0.0.1:5000`

2. **Adicionar Requests:**

**Health Check**
- Method: `GET`
- URL: `{{base_url}}/api/health`

**Criar Transação**
- Method: `POST`
- URL: `{{base_url}}/api/users/test_user/transactions`
- Body (JSON):
```json
{
    "description": "Compra no supermercado",
    "amount": 150.50,
    "type": "expense",
    "date": "2025-11-25"
}
```

**Criar Consent**
- Method: `POST`
- URL: `{{base_url}}/api/users/test_user/openfinance/consents`
- Body (JSON):
```json
{}
```

**Sincronizar Open Finance**
- Method: `POST`
- URL: `{{base_url}}/api/users/test_user/openfinance/sync`

**Listar Transações com Paginação**
- Method: `GET`
- URL: `{{base_url}}/api/users/test_user/transactions?page=1&per_page=10`

## 🐛 Problemas Comuns

### 1. "Impossível conectar ao servidor"
**Solução:** Certifique-se de que o servidor está rodando:
```bash
python backend.py
```

### 2. "ModuleNotFoundError: No module named 'flask'"
**Solução:** Instale as dependências:
```bash
pip install -r requirements.txt
```

### 3. "Port 5000 já está em uso"
**Solução:** Mate o processo ou use outra porta:
```bash
# Descobrir processo na porta 5000
netstat -ano | findstr :5000

# Matar processo (substitua PID)
taskkill /PID <numero_do_pid> /F
```

### 4. "CSRF token missing"
**Solução:** Para testes, obtenha o token primeiro:
```powershell
# Obter CSRF token
$token = (Invoke-RestMethod -Uri http://127.0.0.1:5000/api/csrf-token).csrf_token

# Usar em requisições POST
$headers = @{"X-CSRFToken" = $token}
Invoke-RestMethod -Uri http://127.0.0.1:5000/api/users/test_user/transactions -Method POST -Headers $headers -Body $body -ContentType "application/json"
```

### 5. "No active consent found"
**Solução:** Crie um consent antes de sincronizar:
```powershell
# 1. Criar consent
Invoke-RestMethod -Uri http://127.0.0.1:5000/api/users/test_user/openfinance/consents -Method POST -Body "{}" -ContentType "application/json"

# 2. Depois sincronizar
Invoke-RestMethod -Uri http://127.0.0.1:5000/api/users/test_user/openfinance/sync -Method POST
```

## 📊 Exemplo Completo de Uso

```powershell
# 1. Login de desenvolvimento
$body = @{
    user_id = "test_user"
    email = "test@example.com"
    name = "Test User"
} | ConvertTo-Json

$login = Invoke-RestMethod -Uri http://127.0.0.1:5000/auth/dev-login -Method POST -Body $body -ContentType "application/json" -SessionVariable websession
Write-Host "✅ Login: $($login.user.email)"

# 2. Verificar se servidor está rodando
$health = Invoke-RestMethod -Uri http://127.0.0.1:5000/api/health
Write-Host "✅ Servidor: $($health.status)"

# 3. Criar algumas transações
$transacoes = @(
    @{description="Salário"; amount=5000; type="income"; date="2025-11-25"},
    @{description="Aluguel"; amount=1500; type="expense"; date="2025-11-25"},
    @{description="Supermercado"; amount=450; type="expense"; date="2025-11-24"}
)

foreach ($txn in $transacoes) {
    $body = $txn | ConvertTo-Json
    Invoke-RestMethod -Uri http://127.0.0.1:5000/api/users/test_user/transactions -Method POST -Body $body -ContentType "application/json" -WebSession $websession
}
Write-Host "✅ 3 transações criadas"

# 4. Ver resumo financeiro
$resumo = Invoke-RestMethod -Uri http://127.0.0.1:5000/api/users/test_user/summary -WebSession $websession
Write-Host "💰 Receitas: R$ $($resumo.total_income)"
Write-Host "💸 Despesas: R$ $($resumo.total_expense)"
Write-Host "📊 Saldo: R$ $($resumo.balance)"

# 5. Criar consent para Open Finance
$consent = Invoke-RestMethod -Uri http://127.0.0.1:5000/api/users/test_user/openfinance/consents -Method POST -Body "{}" -ContentType "application/json" -WebSession $websession
Write-Host "✅ Consent criado: $($consent.consent_id)"

# 6. Sincronizar transações do banco (simulado)
$resultado = Invoke-RestMethod -Uri http://127.0.0.1:5000/api/users/test_user/openfinance/sync -Method POST -ContentType "application/json" -WebSession $websession
Write-Host "✅ Importadas: $($resultado.imported) transações"

# 7. Ver todas as transações
$dados = Invoke-RestMethod -Uri http://127.0.0.1:5000/api/users/test_user/transactions -WebSession $websession
Write-Host "📋 Total: $($dados.pagination.total) transações"
$dados.items | Format-Table description, amount, type, date -AutoSize
```

## 🎯 Próximos Passos

1. **Frontend:** Criar interface web com React/Vue/Angular
2. **Autenticação:** Implementar login com Google OAuth
3. **Deploy:** Hospedar na nuvem (Azure, AWS, Heroku)
4. **Mobile:** Criar app mobile com React Native

## 📚 Documentação Completa

- `README.md` - Visão geral do projeto
- `API_USAGE_GUIDE.md` - Guia completo da API
- `OPENFINANCE_INTEGRATION.md` - Integração com Open Finance Brasil
- `MULTIPLE_BANKS.md` - Suporte a múltiplos bancos
- `AUTO_CATEGORIZATION.md` - Categorização automática

## ❓ Precisa de Ajuda?

Execute o script de teste para verificar se tudo está funcionando:
```bash
python test_openfinance.py
```

Esse script testa automaticamente todos os endpoints principais!
