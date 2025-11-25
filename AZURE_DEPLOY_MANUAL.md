# 🚀 Deploy no Azure - Guia Passo a Passo (Sem CLI)

## ⏱️ Tempo: 10-15 minutos

---

## 📋 Pré-Requisitos

- ✅ Conta Microsoft (grátis em https://azure.microsoft.com)
- ✅ Seu projeto Git pronto
- ✅ Arquivo `requirements.txt` configurado

---

## 🔧 Passo 1: Preparar o Projeto

Verifique se tem estes arquivos na raiz do projeto:

```bash
✅ Procfile           # Para Heroku, também funciona no Azure
✅ runtime.txt        # Python 3.11.4
✅ requirements.txt   # Todas as dependências
✅ .env               # Variáveis configuradas
```

---

## 🌐 Passo 2: Fazer Commit e Push para GitHub

```bash
cd c:\Users\automacao\my-project\Gestão_financeiro2.0\gestor-financeiro

git add .
git commit -m "Deploy para Azure"
git push origin main
```

Se não tiver repositório GitHub:

```bash
git init
git add .
git commit -m "Inicial"
git remote add origin https://github.com/seu-usuario/seu-repo.git
git branch -M main
git push -u origin main
```

---

## 🏢 Passo 3: Criar Aplicação no Azure (Via Portal Web)

### 3.1 Ir para Azure Portal

1. Abra: https://portal.azure.com
2. Faça login com sua conta Microsoft
3. Se for primeira vez, crie conta grátis

### 3.2 Criar App Service

1. Clique em **"+ Criar um recurso"**
2. Procure por **"App Service"**
3. Clique em **Criar**

### 3.3 Preencher Formulário

| Campo | Valor |
|-------|-------|
| **Assinatura** | Selecione sua assinatura |
| **Grupo de recursos** | Novo → `meu-gestor-financeiro` |
| **Nome** | `meu-gestor-financeiro` (único) |
| **Publicar** | Código |
| **Pilha de tempo de execução** | Python 3.11 |
| **Sistema operacional** | Linux |
| **Região** | East US (ou Brasil) |
| **Plano do Serviço de Aplicativo** | Criar novo → `AppServicePlan-free` |
| **SKU e tamanho** | F1 (grátis) |

### 3.4 Avançado (Importante!)

1. Deixe **Application Insights** como padrão
2. Clique em **Avançado**
3. Em **Stack settings**:
   - Startup Command: `gunicorn --bind 0.0.0.0:8000 backend:app`

### 3.5 Criar

Clique em **Revisar + Criar → Criar**

⏳ Aguarde 2-3 minutos...

---

## 📊 Passo 4: Criar Banco de Dados PostgreSQL

### 4.1 No Portal Azure

1. Clique em **"+ Criar um recurso"**
2. Procure: **"Banco de Dados do Azure para PostgreSQL"**
3. Clique em **Servidor flexível**

### 4.2 Configurar Banco de Dados

| Campo | Valor |
|-------|-------|
| **Grupo de recursos** | `meu-gestor-financeiro` |
| **Nome do servidor** | `meu-gestor-financeiro-db` |
| **Região** | East US (mesma do App Service) |
| **Versão** | 14 |
| **Admin username** | `postgres` |
| **Senha** | `Senha123!@#` (guarde!) |
| **SKU** | B1ms (burstable - grátis) |

### 4.3 Criar

Clique em **Revisar + Criar → Criar**

⏳ Aguarde 5-10 minutos...

---

## 🔑 Passo 5: Configurar Conexão com Banco de Dados

### 5.1 Obter String de Conexão

1. No Portal, vá para seu PostgreSQL
2. Em **Configurações**, clique em **Strings de conexão**
3. Copie a URL PostgreSQL

Deve ser algo como:
```
postgresql://postgres:Senha123!@#@meu-gestor-financeiro-db.postgres.database.azure.com:5432/postgres
```

### 5.2 Configurar App Service

1. Volte para seu **App Service**
2. Em **Configurações**, clique em **Variáveis de ambiente**
3. Clique em **+ Adicionar**

Adicione estas variáveis:

```
DATABASE_URL = postgresql://postgres:Senha123!@#@meu-gestor-financeiro-db.postgres.database.azure.com:5432/postgres
FLASK_ENV = production
SECRET_KEY = sua-chave-secreta-aleatoria-40-caracteres
DEBUG = False
```

4. Clique em **Salvar**

---

## 🔗 Passo 6: Conectar Repositório GitHub

### 6.1 No App Service

1. Em **Central de Implantação**, clique em **Configurações**
2. Selecione **GitHub** como origem
3. Clique em **Autorizar Azure**

### 6.2 Autorizar

1. Faça login no GitHub
2. Autorize Azure a acessar seus repositórios

### 6.3 Configurar Deploy

| Campo | Valor |
|-------|-------|
| **Organização** | Sua organização |
| **Repositório** | Seu repositório |
| **Branch** | main |

4. Clique em **Salvar**

⏳ Aguarde... O Azure fará o primeiro deploy automaticamente!

---

## ✅ Passo 7: Verificar Deployment

### 7.1 Acompanhar Logs

1. No App Service, clique em **Log de streaming**
2. Você verá os logs em tempo real

Procure por:
```
WARNING in app.run(): This is a development server. Do not use in production.
2025-11-25 12:34:56.789 INFO Application started
```

### 7.2 Testar Aplicação

1. No App Service, copie a **URL**
2. Abra no navegador: `https://meu-gestor-financeiro.azurewebsites.net`

Deve ver a página inicial!

---

## 🚨 Se der erro:

### Erro 502 (Bad Gateway)

**Solução:**
1. Volte a **App Service → Configuração**
2. Verifique se `DATABASE_URL` está correto
3. Clique em **Reiniciar**

### Erro "ModuleNotFoundError"

**Solução:**
1. Vá para **SSH** (em Ferramentas de Desenvolvimento)
2. Execute: `pip install -r requirements.txt`

### Erro de Banco de Dados

**Solução:**
1. Vá para seu PostgreSQL
2. Em **Segurança**, clique em **Configuração de firewall**
3. Marque **Permitir acesso dos serviços do Azure**
4. Clique em **Salvar**

---

## 🎯 Próximos Passos

Após deploy bem-sucedido:

```bash
# 1. Executar migrações
az webapp remote-build-from-zip ...

# 2. Criar usuário admin
# 3. Acessar em https://seu-app.azurewebsites.net
# 4. Configurar domínio próprio (opcional)
```

---

## 📱 Deploy Automático (Contínuo)

A partir de agora:

- ✅ Cada `git push` faz deploy automaticamente
- ✅ Não precisa fazer mais nada manualmente
- ✅ Azure detecta mudanças e redeploy

```bash
git add .
git commit -m "Nova feature"
git push origin main   # Deploy automático!
```

---

## 🔐 Segurança em Produção

Antes de usar em produção:

```python
# backend.py - Verificar:
app.config['DEBUG'] = False
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
```

---

## 💰 Custo

Tier F1 (grátis):
- ✅ 60 minutos/dia CPU compartilhada
- ✅ Perfeito para teste/prototipagem

Para produção 24/7:
- Upgrade para **B1** (~$10/mês)

---

## ✨ Parabéns! 

Sua aplicação está online no Azure! 🎉

**URL**: `https://meu-gestor-financeiro.azurewebsites.net`

---

## 📞 Próximas Melhorias

1. Configurar SSL/TLS (automático no Azure)
2. Adicionar domínio personalizado
3. Configurar backups automáticos
4. Monitorar performance com Application Insights
5. Escalar para múltiplas instâncias

---

**Pronto para usar? Vamos começar!** 🚀
