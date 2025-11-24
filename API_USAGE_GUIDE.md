# 📖 Guia de Uso da API - Gestão Financeiro 2.0

## 🚀 Inicialização

### Iniciar o servidor
```bash
# No diretório do projeto
python backend.py

# Servidor estará disponível em: http://127.0.0.1:5000
```

### Testar saúde do servidor
```bash
curl http://localhost:5000/api/health
# Retorna: {"status": "ok"}
```

---

## 🔐 Segurança - Rate Limiting & CSRF

### 1. Obter CSRF Token (necessário para POST/PUT/DELETE)

**Endpoint:** `GET /api/csrf-token`

```bash
curl http://localhost:5000/api/csrf-token

# Resposta:
# {"csrf_token": "IjE4ZWY0N2Y0YjhhYWU0MWI0MjYxNGE0Yjg3YzQ4M2U1Ig.Z7-cEg.f8-_X..."}
```

### 2. Rate Limiting - Limites Aplicados

| Endpoint | Limite | Descrição |
|----------|--------|-----------|
| `/auth/login` | 5 req/min | Proteção contra brute-force |
| Operações de dados | 100 req/hora | Proteção de recursos |
| `/open-finance/sync` | 10 req/hora | Proteção de API externa |
| Global | 200 req/dia, 50 req/hora | Limite geral |

**Resposta ao exceder limite:**
```bash
curl -i http://localhost:5000/api/users/user1/transactions

# HTTP/1.1 429 Too Many Requests
# Retry-After: 3600
# {"error": "Rate limit exceeded"}
```

---

## 💰 Transações

### Listar Transações (com Paginação)

**Endpoint:** `GET /api/users/{user_id}/transactions`

**Parâmetros de query:**
- `page` (padrão: 1) - Número da página
- `per_page` (padrão: 20, máximo: 100) - Itens por página

```bash
# Página 1 (padrão: 20 itens)
curl "http://localhost:5000/api/users/user1/transactions"

# Página 2 com 30 itens por página
curl "http://localhost:5000/api/users/user1/transactions?page=2&per_page=30"

# Resposta:
{
  "items": [
    {
      "id": 1,
      "description": "Salário",
      "amount": 5000.00,
      "type": "income",
      "date": "2025-01-15",
      "user_id": "user1"
    },
    ...
  ],
  "pagination": {
    "current_page": 1,
    "per_page": 20,
    "total": 150,
    "pages": 8
  }
}
```

### Criar Transação

**Endpoint:** `POST /api/users/{user_id}/transactions`

**Headers:**
- `Content-Type: application/json`
- `X-CSRFToken: {token}` (obtido em `/api/csrf-token`)

**Body:**
```json
{
  "description": "Compra de supermercado",
  "amount": 150.50,
  "type": "expense",
  "date": "2025-01-20"
}
```

**Request:**
```bash
CSRF_TOKEN=$(curl -s http://localhost:5000/api/csrf-token | jq -r '.csrf_token')

curl -X POST http://localhost:5000/api/users/user1/transactions \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $CSRF_TOKEN" \
  -d '{
    "description": "Compra de supermercado",
    "amount": 150.50,
    "type": "expense",
    "date": "2025-01-20"
  }'

# Resposta (201 Created):
{
  "id": 42,
  "description": "Compra de supermercado",
  "amount": 150.50,
  "type": "expense",
  "date": "2025-01-20",
  "user_id": "user1"
}
```

### Atualizar Transação

**Endpoint:** `PUT /api/users/{user_id}/transactions/{transaction_id}`

```bash
CSRF_TOKEN=$(curl -s http://localhost:5000/api/csrf-token | jq -r '.csrf_token')

curl -X PUT http://localhost:5000/api/users/user1/transactions/42 \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $CSRF_TOKEN" \
  -d '{
    "description": "Compra atualizada",
    "amount": 155.75,
    "type": "expense"
  }'

# Resposta (200 OK):
{
  "id": 42,
  "description": "Compra atualizada",
  "amount": 155.75,
  "type": "expense",
  "date": "2025-01-20",
  "user_id": "user1"
}
```

### Deletar Transação

**Endpoint:** `DELETE /api/users/{user_id}/transactions/{transaction_id}`

```bash
CSRF_TOKEN=$(curl -s http://localhost:5000/api/csrf-token | jq -r '.csrf_token')

curl -X DELETE http://localhost:5000/api/users/user1/transactions/42 \
  -H "X-CSRFToken: $CSRF_TOKEN"

# Resposta (204 No Content)
```

---

## 📋 Parcelas (Installments)

### Listar Parcelas

**Endpoint:** `GET /api/users/{user_id}/installments`

```bash
curl "http://localhost:5000/api/users/user1/installments?page=1&per_page=20"

# Resposta:
{
  "items": [
    {
      "id": 1,
      "transaction_id": 42,
      "installment_number": 1,
      "total_installments": 3,
      "amount": 51.92,
      "due_date": "2025-02-20",
      "paid": false
    },
    ...
  ],
  "pagination": {
    "current_page": 1,
    "per_page": 20,
    "total": 45,
    "pages": 3
  }
}
```

### Criar Parcela

**Endpoint:** `POST /api/users/{user_id}/installments`

```bash
CSRF_TOKEN=$(curl -s http://localhost:5000/api/csrf-token | jq -r '.csrf_token')

curl -X POST http://localhost:5000/api/users/user1/installments \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $CSRF_TOKEN" \
  -d '{
    "transaction_id": 42,
    "installment_number": 1,
    "total_installments": 3,
    "amount": 51.92,
    "due_date": "2025-02-20",
    "paid": false
  }'

# Resposta (201 Created)
```

---

## 📊 Resumo Financeiro

### Obter Resumo

**Endpoint:** `GET /api/users/{user_id}/summary`

```bash
curl http://localhost:5000/api/users/user1/summary

# Resposta:
{
  "total_income": 5000.00,
  "total_expenses": 1250.50,
  "balance": 3749.50,
  "month": "2025-01",
  "transactions_count": 15,
  "installments_count": 5
}
```

---

## 🔄 Sincronização Open Finance

### Criar Consentimento

**Endpoint:** `POST /api/users/{user_id}/consents`

```bash
CSRF_TOKEN=$(curl -s http://localhost:5000/api/csrf-token | jq -r '.csrf_token')

curl -X POST http://localhost:5000/api/users/user1/consents \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $CSRF_TOKEN" \
  -d '{
    "bank": "Banco do Brasil",
    "auth_code": "AUTH123456"
  }'

# Resposta:
{
  "id": 1,
  "bank": "Banco do Brasil",
  "auth_code": "AUTH123456",
  "status": "active"
}
```

### Sincronizar com Open Finance

**Endpoint:** `POST /api/users/{user_id}/open-finance/sync`

Nota: Rate-limitado a 10 req/hora

```bash
CSRF_TOKEN=$(curl -s http://localhost:5000/api/csrf-token | jq -r '.csrf_token')

curl -X POST http://localhost:5000/api/users/user1/open-finance/sync \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $CSRF_TOKEN" \
  -d '{
    "consent_id": 1
  }'

# Resposta:
{
  "synced_transactions": 12,
  "duplicates_found": 2,
  "status": "success",
  "timestamp": "2025-01-20T15:30:00Z"
}
```

---

## 🔐 Autenticação

### Login (com rate limiting)

**Endpoint:** `POST /auth/login`

Nota: Rate-limitado a 5 req/minuto

```bash
CSRF_TOKEN=$(curl -s http://localhost:5000/api/csrf-token | jq -r '.csrf_token')

curl -X POST http://localhost:5000/auth/login \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $CSRF_TOKEN" \
  -d '{
    "email": "user@example.com",
    "password": "senha123"
  }'

# Resposta:
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user_id": "user1",
  "email": "user@example.com"
}
```

---

## ✅ Checklist de Teste Manual

- [ ] Health check (`/api/health`)
- [ ] Obter CSRF token (`/api/csrf-token`)
- [ ] Listar transações com paginação (página 1, depois página 2)
- [ ] Criar transação (com CSRF token)
- [ ] Atualizar transação
- [ ] Deletar transação
- [ ] Criar parcela
- [ ] Obter resumo financeiro
- [ ] Testar rate limiting (mais de 5 requests em /auth/login)
- [ ] Sincronizar Open Finance (com consentimento)

---

## 🛠️ Troubleshooting

### Erro: "Rate limit exceeded"
- **Causa:** Muitas requisições em pouco tempo
- **Solução:** Aguarde antes de fazer novas requisições. Ver header `Retry-After`

### Erro: "CSRF token missing"
- **Causa:** Sem header `X-CSRFToken` em POST/PUT/DELETE
- **Solução:** Obter token em `/api/csrf-token` e incluir no header

### Erro: "User not found"
- **Causa:** `{user_id}` inválido na URL
- **Solução:** Verificar ID do usuário

### Erro: "Invalid date format"
- **Causa:** Data em formato incorreto
- **Solução:** Usar formato ISO 8601: `YYYY-MM-DD`

---

## 📚 Referências

- [TESTING_RESULTS.md](./TESTING_RESULTS.md) - Resultados de testes
- [SECURITY_IMPROVEMENTS.md](./SECURITY_IMPROVEMENTS.md) - Detalhes de segurança
- [PAGINATION_SUMMARY.md](./PAGINATION_SUMMARY.md) - Guia de paginação
- [STATUS_IMPLEMENTACAO.md](./STATUS_IMPLEMENTACAO.md) - Status geral

---

**Última atualização:** 2025-01-XX  
**Versão da API:** 2.0  
**Ambiente:** Desenvolvimento (http://127.0.0.1:5000)
