# 🏦 Integração Open Finance Brasil - Guia Completo

## 📋 Visão Geral

O sistema agora suporta integração **real** com APIs do **Open Finance Brasil**, permitindo sincronização automática de transações bancárias de múltiplas instituições financeiras.

### Modos de Operação

| Modo | Descrição | Quando Usar |
|------|-----------|-------------|
| **Simulado** | Provider fictício com dados estáticos | Desenvolvimento, testes, demonstrações |
| **Real** | Integração com APIs reais do Open Finance | Produção, homologação com bancos reais |

---

## 🔧 Configuração

### 1. Variáveis de Ambiente

Adicione as seguintes variáveis ao arquivo `.env`:

```bash
# Habilitar modo real (false = simulado, true = real)
OPENFINANCE_ENABLE_REAL=true

# URL base da API do banco
OPENFINANCE_BASE_URL=https://api.banco.com.br/open-banking

# Credenciais do aplicativo
OPENFINANCE_CLIENT_ID=seu-client-id-aqui
OPENFINANCE_CLIENT_SECRET=seu-client-secret-aqui

# Certificados mTLS (obrigatórios para produção)
OPENFINANCE_CERT_PATH=/caminho/para/certificado.pem
OPENFINANCE_KEY_PATH=/caminho/para/chave-privada.key
```

### 2. Certificados mTLS

O Open Finance Brasil exige **autenticação mútua TLS (mTLS)**:

#### Obter Certificados

1. **Registrar aplicativo** no diretório do Open Finance Brasil
2. **Gerar par de chaves** (certificado + chave privada)
3. **Validar certificado** pela instituição financeira

#### Formato dos Arquivos

```bash
# Certificado (formato PEM)
certificado.pem
-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAKL0UG...
-----END CERTIFICATE-----

# Chave Privada (formato PEM)
chave-privada.key
-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEF...
-----END PRIVATE KEY-----
```

---

## 🚀 Como Funciona

### Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (Cliente)                                     │
└────────────┬────────────────────────────────────────────┘
             │
             │ 1. POST /openfinance/sync
             ▼
┌─────────────────────────────────────────────────────────┐
│  Backend (Flask)                                        │
│  ├─ Valida consent ativo                               │
│  ├─ Escolhe provider (Simulated ou Real)               │
│  └─ Chama provider.sync()                              │
└────────────┬────────────────────────────────────────────┘
             │
             │ 2. OpenFinanceProvider
             ▼
┌─────────────────────────────────────────────────────────┐
│  Open Finance Brasil API                                │
│  ├─ OAuth 2.0 (Client Credentials)                     │
│  ├─ GET /accounts (lista contas)                       │
│  ├─ GET /accounts/{id}/transactions (transações)       │
│  └─ Autenticação mTLS                                  │
└────────────┬────────────────────────────────────────────┘
             │
             │ 3. Normaliza e retorna
             ▼
┌─────────────────────────────────────────────────────────┐
│  Backend (Flask)                                        │
│  ├─ Deduplicação (evita duplicatas)                   │
│  ├─ Salva no banco local (SQLite)                     │
│  └─ Retorna transações importadas                     │
└─────────────────────────────────────────────────────────┘
```

### Fluxo de Sincronização

#### Passo 1: Obter Access Token (OAuth 2.0)
```python
POST {base_url}/oauth2/token
Content-Type: application/x-www-form-urlencoded
Authorization: Basic {client_id}:{client_secret}

grant_type=client_credentials
scope=accounts transactions
consent_id={consent_id}
```

**Resposta:**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

#### Passo 2: Listar Contas
```python
GET {base_url}/accounts/v1/accounts
Authorization: Bearer {access_token}
```

**Resposta:**
```json
{
  "data": [
    {
      "accountId": "12345-67890",
      "type": "CHECKING",
      "currency": "BRL"
    }
  ]
}
```

#### Passo 3: Buscar Transações
```python
GET {base_url}/accounts/v1/accounts/{accountId}/transactions
Authorization: Bearer {access_token}
```

**Parâmetros:**
- `fromBookingDate`: YYYY-MM-DD (default: 90 dias atrás)
- `toBookingDate`: YYYY-MM-DD (default: hoje)

**Resposta:**
```json
{
  "data": [
    {
      "transactionId": "TXN-123",
      "type": "PIX",
      "creditDebitType": "DEBIT",
      "transactionName": "Transferência PIX",
      "amount": 150.00,
      "bookingDate": "2025-11-24",
      "creditorName": "João Silva"
    }
  ]
}
```

#### Passo 4: Normalização
Transações são convertidas do formato Open Finance para formato interno:

**Formato Open Finance:**
```json
{
  "transactionName": "Transferência PIX",
  "creditDebitType": "DEBIT",
  "amount": 150.00,
  "bookingDate": "2025-11-24",
  "creditorName": "João Silva"
}
```

**Formato Interno:**
```json
{
  "description": "Transferência PIX (João Silva)",
  "amount": 150.00,
  "type": "expense",
  "date": "2025-11-24"
}
```

---

## 📝 Uso da API

### Criar Consentimento

```bash
POST /api/users/{user_id}/openfinance/consents
Content-Type: application/json
X-CSRFToken: {token}

{
  "consent_id": "CONSENT-ABC123",
  "provider": "banco_exemplo",
  "scopes": "accounts transactions",
  "status": "active"
}
```

### Sincronizar Transações

```bash
POST /api/users/{user_id}/openfinance/sync
X-CSRFToken: {token}
```

**Resposta (Sucesso):**
```json
{
  "status": "success",
  "source": "open_finance_brasil",
  "imported": 15,
  "skipped_duplicates": 3,
  "transactions": [...],
  "consent_id": "CONSENT-ABC123"
}
```

**Resposta (Erro - Sem Consent):**
```json
{
  "error": "no_active_consent",
  "details": "Nenhum consent ativo encontrado para este usuário."
}
```

**Resposta (Erro - Falha API):**
```json
{
  "error": "sync_failed",
  "details": "Open Finance não configurado. Configurações faltantes: OPENFINANCE_BASE_URL, OPENFINANCE_CLIENT_ID"
}
```

---

## 🔐 Segurança

### Rate Limiting
- **Sincronização:** 10 requisições/hora
- Protege contra uso excessivo da API externa
- Headers retornados: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After`

### CSRF Protection
- Token obrigatório em todas as requisições POST
- Endpoint para obter token: `GET /api/csrf-token`

### mTLS (Mutual TLS)
- Autenticação bidirecional cliente-servidor
- Certificado validado pela instituição financeira
- Previne ataques man-in-the-middle

### Token Caching
- Access tokens são reutilizados até expiração
- Reduz chamadas ao endpoint OAuth
- Buffer de 60 segundos antes da expiração

---

## 🧪 Testes

### Modo Simulado (Desenvolvimento)

```bash
# .env
OPENFINANCE_ENABLE_REAL=false
```

**Comportamento:**
- Usa `SimulatedProvider`
- Retorna 3 transações fictícias
- Não requer configuração de API
- Ideal para testes unitários

### Modo Real (Produção)

```bash
# .env
OPENFINANCE_ENABLE_REAL=true
OPENFINANCE_BASE_URL=https://api.banco.com.br/open-banking
OPENFINANCE_CLIENT_ID=abc123
OPENFINANCE_CLIENT_SECRET=xyz789
OPENFINANCE_CERT_PATH=/path/to/cert.pem
OPENFINANCE_KEY_PATH=/path/to/key.key
```

**Comportamento:**
- Usa `OpenFinanceProvider`
- Conecta com API real
- Requer certificados mTLS válidos
- Rate limiting aplicado

---

## 📊 Mapeamento de Dados

### Tipo de Transação

| Open Finance `creditDebitType` | Tipo Interno |
|-------------------------------|--------------|
| `CREDIT` | `income` |
| `DEBIT` | `expense` |
| (vazio) | `expense` se amount < 0, senão `income` |

### Descrição

Composição da descrição:
1. `transactionName` (obrigatório)
2. `creditorName` entre parênteses (se disponível)

**Exemplos:**
- `"Transferência PIX (João Silva)"`
- `"Compra Supermercado"`
- `"Boleto Energia (Cemig)"`

### Valor

- Sempre convertido para positivo (`abs(amount)`)
- Tipo (`income`/`expense`) determina se é entrada ou saída

### Data

- Campo: `bookingDate` (data de lançamento)
- Formato: `YYYY-MM-DD`
- Fallback: data atual se não informado

---

## ⚠️ Troubleshooting

### Erro: "Open Finance não configurado"

**Causa:** Variáveis de ambiente faltantes

**Solução:**
```bash
# Verificar configuração
echo $OPENFINANCE_BASE_URL
echo $OPENFINANCE_CLIENT_ID
echo $OPENFINANCE_CLIENT_SECRET

# Adicionar ao .env
OPENFINANCE_ENABLE_REAL=true
OPENFINANCE_BASE_URL=...
OPENFINANCE_CLIENT_ID=...
OPENFINANCE_CLIENT_SECRET=...
```

### Erro: "SSL: CERTIFICATE_VERIFY_FAILED"

**Causa:** Certificado mTLS inválido ou não encontrado

**Solução:**
1. Verificar se arquivos existem:
```bash
ls -la /path/to/cert.pem
ls -la /path/to/key.key
```

2. Validar formato PEM:
```bash
openssl x509 -in cert.pem -text -noout
openssl rsa -in key.key -check
```

3. Atualizar caminhos no `.env`

### Erro: "401 Unauthorized"

**Causa:** Credenciais OAuth inválidas

**Solução:**
1. Validar `client_id` e `client_secret`
2. Verificar se aplicativo está registrado no banco
3. Confirmar escopos solicitados (`accounts transactions`)

### Erro: "429 Too Many Requests"

**Causa:** Rate limit excedido (10 sync/hora)

**Solução:**
1. Aguardar tempo indicado no header `Retry-After`
2. Reduzir frequência de sincronizações
3. Verificar logs para sincronizações desnecessárias

### Erro: "no_active_consent"

**Causa:** Nenhum consentimento ativo para o usuário

**Solução:**
1. Criar consent via `POST /openfinance/consents`
2. Verificar status do consent (deve ser `active`)
3. Confirmar que consent não foi soft-deleted

---

## 📚 Referências

### Documentação Oficial

- [Open Finance Brasil - Documentação](https://openfinancebrasil.atlassian.net/wiki/spaces/OF/overview)
- [APIs de Dados - Especificação](https://openbanking-brasil.github.io/areadesenvolvedor/)
- [Certificação - Diretório](https://web.directory.openbankingbrasil.org.br/)

### Endpoints Padrão

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/oauth2/token` | POST | Obter access token |
| `/accounts/v1/accounts` | GET | Listar contas |
| `/accounts/v1/accounts/{id}/transactions` | GET | Listar transações |
| `/consents/v1/consents` | POST | Criar consentimento |

### Escopos OAuth

| Escopo | Descrição |
|--------|-----------|
| `accounts` | Acesso a dados de contas |
| `transactions` | Acesso a transações |
| `consents` | Gerenciar consentimentos |

---

## 🔮 Melhorias Futuras

### 1. Múltiplos Bancos
```python
# Suporte a múltiplos providers por usuário
providers = {
    "banco_brasil": OpenFinanceProvider(base_url="..."),
    "itau": OpenFinanceProvider(base_url="..."),
    "nubank": OpenFinanceProvider(base_url="...")
}
```

### 2. Webhooks
```python
@app.route("/webhooks/openfinance", methods=["POST"])
def openfinance_webhook():
    """Recebe notificações de novas transações."""
    # Auto-sync quando banco notifica mudanças
```

### 3. Cache Inteligente
```python
# Evitar sync se última sincronização foi recente
if last_sync < (datetime.now() - timedelta(hours=1)):
    provider.sync(...)
```

### 4. Reconciliação Manual
```python
# UI para revisar transações antes de importar
@app.route("/openfinance/review", methods=["GET"])
def review_transactions():
    """Exibe transações para aprovação manual."""
```

### 5. Categorização Automática
```python
# Machine learning para categorizar transações
def categorize_transaction(description: str) -> str:
    # Usar NLP para identificar categoria
    return "supermercado" | "transporte" | "saúde" | ...
```

---

## ✅ Checklist de Implementação

- [x] Provider base (`BaseProvider`)
- [x] Provider simulado (`SimulatedProvider`)
- [x] Provider real (`OpenFinanceProvider`)
- [x] OAuth 2.0 Client Credentials
- [x] Suporte mTLS
- [x] Listagem de contas
- [x] Busca de transações
- [x] Normalização de dados
- [x] Deduplicação
- [x] Rate limiting
- [x] Logging estruturado
- [x] Tratamento de erros
- [x] Configuração via .env
- [x] Documentação completa
- [ ] Webhooks (futuro)
- [ ] Múltiplos bancos (futuro)
- [ ] Categorização automática (futuro)

---

**Versão:** 2.2  
**Data:** 25 de Novembro de 2025  
**Status:** ✅ Pronto para Produção  
**Provider:** SimulatedProvider (dev) + OpenFinanceProvider (prod)
