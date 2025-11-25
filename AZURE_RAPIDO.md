# ⚡ LINKS RÁPIDOS - Azure Portal

## 🔗 Acesse Direto:

**Azure Portal**: https://portal.azure.com

---

## 📋 Checklist - Criar App

### PASSO 1: Resource Group
```
1. Azure Portal
2. Menu → "Resource groups"
3. "+ Create"
4. Name: meu-gestor-financeiro
5. Region: East US
6. Create
```

### PASSO 2: App Service
```
1. Menu → "App Services"
2. "+ Create" → "Web App"
3. Resource Group: meu-gestor-financeiro
4. Name: meu-gestor-financeiro
5. Runtime: Python 3.11
6. OS: Linux
7. Region: East US
8. App Service Plan: F1 (Free)
9. Review + Create → Create
⏳ Aguarde 2-3 minutos
```

### PASSO 3: PostgreSQL Banco
```
1. "+ Create a resource"
2. Procure: PostgreSQL
3. "Azure Database for PostgreSQL"
4. "Flexible server"
5. Create
6. Resource Group: meu-gestor-financeiro
7. Server name: meu-gestor-financeiro-db
8. Version: 14
9. Admin: postgres
10. Password: Senha123!@#
11. Compute: B1ms (Burstable)
12. Storage: 32 GB
13. Review + Create → Create
⏳ Aguarde 5-10 minutos
```

### PASSO 4: Configurar Firewall
```
1. PostgreSQL → meu-gestor-financeiro-db
2. Menu Esquerdo → "Networking"
3. Marcar: "Allow public access from Azure services"
4. Save
```

### PASSO 5: Obter Connection String
```
1. PostgreSQL → Connection strings
2. Copie a URL Python
3. Cole em um bloco de notas
```

### PASSO 6: Adicionar Variáveis no App Service
```
1. App Service → meu-gestor-financeiro
2. Menu Esquerdo → "Configuration"
3. "+ New application setting"

Adicione 4 variáveis:

DATABASE_URL
postgresql://postgres:Senha123!@#@meu-gestor-financeiro-db.postgres.database.azure.com:5432/postgres?sslmode=require

FLASK_ENV
production

DEBUG
False

SECRET_KEY
(gere em: https://www.random.org/strings/?num=1&len=40&digits=on&loweralpha=on&upperalpha=on&unique=on)

4. Save
```

### PASSO 7: Conectar GitHub
```
1. App Service → "Deployment Center"
2. Source: GitHub
3. Click "Authorize"
4. Login no GitHub
5. Authorize Azure
6. Organization: (seu)
7. Repository: financie
8. Branch: main
9. Save

⏳ Aguarde deploy automático
```

### PASSO 8: Verificar
```
1. App Service → "Log stream"
2. Procure: "Application started"
3. Se sucesso: URL está pronta!
4. Se erro: Verifique DATABASE_URL
```

### PASSO 9: Testar
```
1. App Service → "Overview"
2. Copie a URL
3. Abra no navegador
4. Pronto! 🎉
```

---

## 📊 Resumo Rápido

| Item | Valor |
|------|-------|
| **App Service Name** | meu-gestor-financeiro |
| **DB Server Name** | meu-gestor-financeiro-db |
| **Resource Group** | meu-gestor-financeiro |
| **Region** | East US |
| **Python** | 3.11 |
| **PostgreSQL** | 14 |
| **Runtime** | F1 Free (550h/mês) |
| **Database Tier** | B1ms (Free) |

---

## 🔐 Variáveis de Ambiente

```
DATABASE_URL = postgresql://postgres:Senha123!@#@meu-gestor-financeiro-db.postgres.database.azure.com:5432/postgres?sslmode=require
FLASK_ENV = production
DEBUG = False
SECRET_KEY = (sua chave aleatória)
```

---

## 🌐 URLs Importantes

- **Azure Portal**: https://portal.azure.com
- **Resource Groups**: https://portal.azure.com/#browse/resourcegroups
- **App Services**: https://portal.azure.com/#browse/appservices
- **PostgreSQL**: https://portal.azure.com/#browse/Microsoft.DBforPostgreSQL/flexibleServers
- **Seu App** (após criar): https://meu-gestor-financeiro.azurewebsites.net

---

## ⏱️ Tempo Estimado

- Resource Group: 1 min
- App Service: 3 min
- PostgreSQL: 10 min
- Configurações: 3 min
- Deploy: 3 min
- **Total: 20 minutos**

---

## ✅ Depois de Pronto

1. Testar: https://seu-app.azurewebsites.net
2. Fazer login
3. Testar endpoints
4. Configurar domínio (opcional)

---

## 🎯 Próximo Passo

Abra: **AZURE_GUIA_COMPLETO.md** para instruções detalhadas!

---

**Pronto? Vamos começar no Azure Portal!** 🚀
