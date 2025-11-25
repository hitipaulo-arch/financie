# 🚀 Guia: Como Colocar Online

## 3 Opções Principais

### 1️⃣ **AZURE** (Recomendado - Mais Fácil)
- Free tier: 1 App Service + 1 PostgreSQL grátis
- Suporta Python nativo
- Escalável

### 2️⃣ **HEROKU** (Gratuito com Limitações)
- Free tier: 550h/mês
- Dyno tipo eco (hibernação após 30min sem uso)
- Rápido de deployar

### 3️⃣ **VPS** (DigitalOcean/Linode - Mais Controle)
- Começa em $5/mês
- Controle total
- Mais complexo

---

## ✅ Opção 1: AZURE (Recomendado)

### Pré-requisitos
1. Criar conta em https://azure.microsoft.com (inclui $200 crédito gratuito)
2. Instalar Azure CLI: https://aka.ms/azurecli

### Passos

#### 1. Login no Azure CLI
```bash
az login
```

#### 2. Criar grupo de recursos
```bash
az group create --name financeiro-rg --location "Southeast Asia"
```

#### 3. Criar banco de dados PostgreSQL
```bash
az postgres flexible-server create \
  --resource-group financeiro-rg \
  --name financeiro-db \
  --admin-user admin \
  --admin-password "Senha@123456" \
  --sku-name Standard_B1ms \
  --tier Burstable
```

#### 4. Preparar aplicação
```bash
cd gestor-financeiro

# Criar arquivo requirements.txt
pip freeze > requirements.txt

# Criar runtime.txt
echo "python-3.11.4" > runtime.txt
```

#### 5. Configurar variáveis de ambiente
Criar arquivo `.env` para produção:
```
FLASK_ENV=production
DATABASE_URL=postgresql://admin:Senha@123456@financeiro-db.postgres.database.azure.com:5432/financeiro
SECRET_KEY=sua-chave-secreta-aqui
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=Strict
```

#### 6. Criar App Service
```bash
# Criar plano de serviço
az appservice plan create \
  --name financeiro-plan \
  --resource-group financeiro-rg \
  --sku FREE --is-linux

# Criar Web App
az webapp create \
  --resource-group financeiro-rg \
  --plan financeiro-plan \
  --name gestor-financeiro-app \
  --runtime "PYTHON:3.11"
```

#### 7. Deploy
```bash
# Compactar aplicação
zip -r gestor-financeiro.zip . -x ".venv/*" ".git/*" "__pycache__/*" "*.pyc"

# Deploy
az webapp deployment source config-zip \
  --resource-group financeiro-rg \
  --name gestor-financeiro-app \
  --src gestor-financeiro.zip
```

#### 8. Configurar variáveis de ambiente
```bash
az webapp config appsettings set \
  --resource-group financeiro-rg \
  --name gestor-financeiro-app \
  --settings \
    FLASK_ENV=production \
    DATABASE_URL="postgresql://admin:Senha@123456@financeiro-db.postgres.database.azure.com:5432/financeiro" \
    SECRET_KEY="sua-chave-secreta"
```

#### 9. Acessar aplicação
```
https://gestor-financeiro-app.azurewebsites.net
```

---

## ✅ Opção 2: HEROKU (Gratuito)

### Pré-requisitos
1. Criar conta em https://www.heroku.com
2. Instalar Heroku CLI: https://devcenter.heroku.com/articles/heroku-cli

### Passos

#### 1. Login
```bash
heroku login
```

#### 2. Criar app
```bash
heroku create gestor-financeiro-app
```

#### 3. Preparar arquivo Procfile
Criar arquivo `Procfile` na raiz:
```
web: gunicorn backend:app
```

#### 4. Preparar requirements.txt
```bash
pip install gunicorn
pip freeze > requirements.txt
```

#### 5. Configurar banco de dados (add-on gratuito)
```bash
heroku addons:create heroku-postgresql:mini --app gestor-financeiro-app
```

#### 6. Configurar variáveis
```bash
heroku config:set FLASK_ENV=production --app gestor-financeiro-app
heroku config:set SECRET_KEY="sua-chave-secreta" --app gestor-financeiro-app
```

#### 7. Deploy
```bash
git add .
git commit -m "Deploy para Heroku"
git push heroku main
```

#### 8. Acessar
```
https://gestor-financeiro-app.herokuapp.com
```

---

## ✅ Opção 3: VPS (DigitalOcean/Linode)

### Pré-requisitos
1. Criar conta e droplet ($5/mês)
2. SSH access

### Passos

#### 1. SSH no servidor
```bash
ssh root@seu_ip_do_servidor
```

#### 2. Instalar dependências
```bash
apt update && apt upgrade -y
apt install -y python3.11 python3-pip nginx postgresql postgresql-contrib supervisor
```

#### 3. Clonar aplicação
```bash
cd /var/www
git clone seu-repositorio gestor-financeiro
cd gestor-financeiro
```

#### 4. Criar ambiente virtual
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

#### 5. Configurar PostgreSQL
```bash
sudo -u postgres createdb financeiro
sudo -u postgres createuser financeiro_user
sudo -u postgres psql -c "ALTER USER financeiro_user WITH PASSWORD 'senha_segura';"
```

#### 6. Configurar Supervisor (auto-restart)
Criar `/etc/supervisor/conf.d/financeiro.conf`:
```ini
[program:financeiro]
directory=/var/www/gestor-financeiro
command=/var/www/gestor-financeiro/.venv/bin/gunicorn --bind 127.0.0.1:5000 backend:app
user=www-data
autostart=true
autorestart=true
stderr_logfile=/var/log/financeiro.err.log
stdout_logfile=/var/log/financeiro.out.log
```

```bash
supervisorctl reread
supervisorctl update
supervisorctl start financeiro
```

#### 7. Configurar Nginx
Criar `/etc/nginx/sites-available/financeiro`:
```nginx
server {
    listen 80;
    server_name seu-dominio.com www.seu-dominio.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/financeiro /etc/nginx/sites-enabled/
nginx -t
systemctl restart nginx
```

#### 8. SSL com Let's Encrypt
```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d seu-dominio.com
```

---

## 🔐 Segurança em Produção

### 1. Variáveis de Ambiente
```bash
# NUNCA commit no git
echo ".env" >> .gitignore
echo "*.pyc" >> .gitignore
echo "__pycache__/" >> .gitignore
```

### 2. Desabilitar Debug
```python
# backend.py
if __name__ == "__main__":
    app.run(debug=False)  # SEMPRE False em produção
```

### 3. Usar WSGI Server
```bash
# Em vez de: python backend.py
# Use: gunicorn backend:app
```

### 4. Reabilitar CSRF
```python
# backend.py
# Remover @csrf.exempt dos endpoints POST (exceto webhooks)
```

### 5. HTTPS Obrigatório
```python
# backend.py
@app.before_request
def enforce_https():
    if not request.is_secure and not app.debug:
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)
```

### 6. Rate Limiting (já implementado)
```python
@limiter.limit("100 per hour")  # Protege contra abuso
```

---

## 🗄️ Migrações de Banco de Dados

### Preparar para produção
```bash
# Executar migrações
python -m alembic upgrade head

# Se usar ORM, criar tabelas
python -c "from backend import Base, engine; Base.metadata.create_all(engine)"
```

---

## 📊 Comparação das Opções

| Feature | Azure | Heroku | VPS |
|---------|-------|--------|-----|
| **Custo** | Grátis (1º ano) | Grátis (550h/mês) | $5/mês |
| **Facilidade** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| **Performance** | ⭐⭐⭐⭐ | ⭐⭐ (hibernação) | ⭐⭐⭐⭐ |
| **Escalabilidade** | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| **Controle** | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |

---

## 🎯 Minha Recomendação

### Para começar rapidamente:
1. **Heroku** - Deploy em 5 minutos, grátis
2. Deploy com `git push heroku main`

### Para uso profissional:
1. **Azure** - Melhor custo-benefício
2. 1º ano grátis, depois ~$50/mês
3. Escalável e confiável

### Para máximo controle:
1. **VPS** - Full control
2. Gerenciar tudo manualmente
3. Mais seguro se bem configurado

---

## 🔗 Links Úteis

- **Azure**: https://azure.microsoft.com
- **Heroku**: https://www.heroku.com
- **DigitalOcean**: https://www.digitalocean.com
- **Linode**: https://www.linode.com
- **Let's Encrypt**: https://letsencrypt.org

---

## ✅ Checklist Pre-Deploy

- [ ] Variáveis de ambiente configuradas
- [ ] Debug desabilitado (`debug=False`)
- [ ] HTTPS configurado
- [ ] Banco de dados em produção
- [ ] Backup automático
- [ ] Logs centralizados
- [ ] Monitoramento ativo
- [ ] CSRF reabilitado
- [ ] Testes passando
- [ ] Documentação atualizada

---

## 🚨 Após Deploy

1. **Acessar aplicação** e fazer login
2. **Testar endpoints** principais
3. **Verificar logs** para erros
4. **Configurar alertas** de erro
5. **Backup regular** do banco de dados
6. **Monitorar performance**

---

Qual opção você prefere? Posso detalhar os passos para sua escolha! 🚀
