# 🚀 CRIAR APP SERVICE NO AZURE - Passo a Passo

## ⏱️ Tempo: 15 minutos

---

## 📋 O que você vai fazer:

1. ✅ Acessar Azure Portal
2. ✅ Criar Resource Group
3. ✅ Criar App Service (com Python 3.11)
4. ✅ Criar Banco de Dados PostgreSQL
5. ✅ Configurar variáveis de ambiente
6. ✅ Conectar GitHub
7. ✅ Deploy automático!

---

## 🌐 PASSO 1: Abrir Azure Portal

1. Abra: **https://portal.azure.com**
2. Faça login com sua conta Microsoft
3. Pressione `F5` se ficar em branco

---

## 📁 PASSO 2: Criar Resource Group

1. Na página inicial, clique em **"Resource groups"**
2. Clique em **"+ Create"**
3. Preencha:
   - **Resource group name**: `meu-gestor-financeiro`
   - **Region**: `East US`
4. Clique em **"Review + create"**
5. Clique em **"Create"**

✅ Pronto! Seu grupo de recursos foi criado.

---

## 🌍 PASSO 3: Criar App Service

### 3.1 Ir para App Services

1. No menu esquerdo, clique em **"App Services"**
2. Clique em **"+ Create"**
3. Selecione **"Web App"**

### 3.2 Preencher Basics

| Campo | Valor |
|-------|-------|
| **Subscription** | Sua assinatura |
| **Resource Group** | `meu-gestor-financeiro` |
| **Name** | `meu-gestor-financeiro` |
| **Publish** | Code |
| **Runtime stack** | Python 3.11 |
| **Operating System** | Linux |
| **Region** | East US |

### 3.3 Preencher App Service Plan

| Campo | Valor |
|-------|-------|
| **Linux Plan** | Criar novo → `AppServicePlan-free` |
| **Sku and size** | F1 (Free) |

### 3.4 Clique em "Review + create"

1. Revise os dados
2. Clique em **"Create"**

⏳ Aguarde 2-3 minutos...

✅ App Service criado!

---

## 🗄️ PASSO 4: Criar Banco de Dados PostgreSQL

### 4.1 Ir para Databases

1. Clique em **"+ Create a resource"**
2. Procure: **"PostgreSQL"**
3. Selecione **"Azure Database for PostgreSQL"**
4. Clique em **"Flexible server"**
5. Clique em **"Create"**

### 4.2 Preencher Configuração

| Campo | Valor |
|-------|-------|
| **Subscription** | Sua assinatura |
| **Resource Group** | `meu-gestor-financeiro` |
| **Server name** | `meu-gestor-financeiro-db` |
| **Region** | East US |
| **PostgreSQL version** | 14 |
| **Admin username** | `postgres` |
| **Password** | Crie uma senha forte: `Senha123!@#` |
| **Confirm password** | `Senha123!@#` |

### 4.3 Compute + Storage

- **Compute tier**: Burstable (B1ms)
- **Storage**: 32 GB

### 4.4 Criar

1. Clique em **"Review + create"**
2. Clique em **"Create"**

⏳ Aguarde 5-10 minutos...

✅ Banco de dados criado!

---

## 🔒 PASSO 5: Configurar Firewall do Banco

### 5.1 Ir para o Banco de Dados

1. No Portal, vá para **"Azure Database for PostgreSQL"**
2. Clique em seu servidor: `meu-gestor-financeiro-db`

### 5.2 Permitir Azure

1. No menu esquerdo, clique em **"Networking"**
2. Em **"Firewall rules"**, marque a caixa:
   - ☑️ **"Allow public access from any Azure service within Azure to this server"**
3. Clique em **"Save"**

✅ Firewall configurado!

---

## 🔑 PASSO 6: Obter String de Conexão

### 6.1 No seu Banco PostgreSQL

1. No menu esquerdo, clique em **"Connection strings"**
2. Procure por **"Connections String"** (aba Python)
3. Copie a URL

Deve parecer com:
```
postgresql://postgres:Senha123!@#@meu-gestor-financeiro-db.postgres.database.azure.com:5432/postgres?sslmode=require
```

**Guarde essa string! Você vai usar em breve.**

---

## ⚙️ PASSO 7: Configurar App Service

### 7.1 Ir para App Service

1. No Portal, vá para **"App Services"**
2. Clique em: `meu-gestor-financeiro`

### 7.2 Configurar Variáveis de Ambiente

1. No menu esquerdo, clique em **"Configuration"**
2. Clique na aba **"Application settings"**
3. Clique em **"+ New application setting"**

### 7.3 Adicionar Variáveis

Adicione cada uma:

**1. DATABASE_URL**
- Name: `DATABASE_URL`
- Value: `postgresql://postgres:Senha123!@#@meu-gestor-financeiro-db.postgres.database.azure.com:5432/postgres?sslmode=require`
- Clique em **OK**

**2. FLASK_ENV**
- Name: `FLASK_ENV`
- Value: `production`
- Clique em **OK**

**3. DEBUG**
- Name: `DEBUG`
- Value: `False`
- Clique em **OK**

**4. SECRET_KEY**
- Name: `SECRET_KEY`
- Value: `sua-chave-secreta-aleatoria-de-40-caracteres`
- (Gere em: https://www.random.org/strings/?num=1&len=40&digits=on&loweralpha=on&upperalpha=on&unique=on)
- Clique em **OK**

### 7.4 Salvar

Clique em **"Save"** (topo da página)
Clique em **"Continue"** se pedir para reiniciar

✅ Variáveis configuradas!

---

## 🔗 PASSO 8: Conectar GitHub

### 8.1 No App Service

1. No menu esquerdo, clique em **"Deployment Center"**
2. Em **"Source"**, selecione **"GitHub"**
3. Clique em **"Authorize"**

### 8.2 Autorizar Azure

1. Faça login no GitHub
2. Autorize Azure a acessar seus repositórios
3. Clique em **"Authorize AzureAppServiceOnGitHub"**

### 8.3 Configurar Repositório

De volta ao Portal:

| Campo | Valor |
|-------|-------|
| **Organization** | Sua organização |
| **Repository** | `financie` (seu repositório) |
| **Branch** | `main` |

### 8.4 Salvar

Clique em **"Save"**

⏳ Azure fará o primeiro deploy automaticamente!

✅ GitHub conectado!

---

## ✅ PASSO 9: Verificar Deployment

### 9.1 Acompanhar Logs

1. No App Service, clique em **"Log stream"**
2. Você verá os logs em tempo real

Procure por:
```
Application started successfully
```

### 9.2 Verificar Status

Em **"Deployment Center"**:
- ✅ Verde = Sucesso
- ❌ Vermelho = Erro

### 9.3 Se Tiver Erro 502

1. Volte para **"Configuration"**
2. Verifique se `DATABASE_URL` está correto
3. Clique em **"Restart"** (topo da página)

---

## 🌐 PASSO 10: Acessar sua App

### 10.1 Obter URL

1. No App Service, clique em **"Overview"**
2. Copie a **URL** no topo
3. Deve ser: `https://meu-gestor-financeiro.azurewebsites.net`

### 10.2 Testar

1. Abra a URL no navegador
2. Você deve ver a página inicial

✅ Sua app está online!

---

## 🎯 Próximos Passos

1. ✅ Criar App Service (feito!)
2. ✅ Criar Banco PostgreSQL (feito!)
3. ✅ Configurar Variáveis (feito!)
4. ✅ Conectar GitHub (feito!)
5. 🔄 Deploy Automático (em andamento)
6. 📱 Testar API
7. 🔐 Configurar HTTPS (automático!)

---

## 🆘 Se Tiver Problemas

### Erro: "502 Bad Gateway"

**Solução:**
1. Vá para Configuration
2. Verifique DATABASE_URL
3. Clique em Restart

### Erro: "ModuleNotFoundError"

**Solução:**
1. Vá para Deployment Center
2. Veja os logs
3. Verifique se requirements.txt está completo

### Erro: "Connection refused"

**Solução:**
1. Vá para PostgreSQL
2. Em Networking, marque "Allow public access..."
3. Clique Save

---

## 💡 Dicas Importantes

✅ **Backup Automático**
- PostgreSQL > Backups > Ative retenção diária

✅ **Monitorar Performance**
- App Service > Application Insights

✅ **Auto-Deploy**
- Cada `git push` faz deploy automático!

```bash
git add .
git commit -m "Nova feature"
git push origin main  # Deploy automático!
```

✅ **Domínio Personalizado** (opcional)
- App Service > Custom domains
- Aponte seu domínio

---

## 🎉 Parabéns!

Sua aplicação está online no Azure! 🚀

**URL**: `https://meu-gestor-financeiro.azurewebsites.net`

**Próximo**: Testar endpoints da API e criar usuário admin.

---

## 📞 Referência Rápida

- **App Service**: https://portal.azure.com → App Services
- **PostgreSQL**: https://portal.azure.com → Azure Database for PostgreSQL
- **Logs**: App Service → Log stream
- **Variáveis**: App Service → Configuration
- **Deploy**: App Service → Deployment Center

---

**Pronto? Comece pelo PASSO 1!** 🚀
