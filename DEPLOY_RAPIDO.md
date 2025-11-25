# 🚀 Colocar Online - Guia Rápido

## 3 Opções em 3 Passos

### ⚡ Mais Fácil: HEROKU (5 minutos)

```bash
# 1. Instalar Heroku CLI
# https://devcenter.heroku.com/articles/heroku-cli

# 2. Login
heroku login

# 3. Deploy automático
bash deploy_heroku.sh
```

**Resultado:** Aplicação rodando em `https://seu-app.herokuapp.com`

---

### 🔷 Melhor Custo: AZURE (10 minutos)

```bash
# 1. Instalar Azure CLI
# https://aka.ms/azurecli

# 2. Login
az login

# 3. Deploy automático
bash deploy_azure.sh
```

**Resultado:** Aplicação rodando em `https://seu-app.azurewebsites.net`

**Benefícios:**
- Free tier: 1º ano grátis
- PostgreSQL grátis
- Escalável

---

### 🖥️ Máximo Controle: VPS (30 minutos)

```bash
# Seguir guia em DEPLOY_ONLINE.md - Seção "Opção 3"
# Usa DigitalOcean ou Linode ($5/mês)
```

---

## ✅ Preparar Antes de Deploy

```bash
# 1. Verificar tudo
python prepare_production.py

# 2. Criar arquivo .env
cp .env.example .env

# 3. Atualizar variáveis em .env
nano .env
```

---

## 📋 Variáveis Importantes

```env
FLASK_ENV=production
FLASK_SECRET_KEY=sua-chave-muito-secreta-aqui
SESSION_COOKIE_SECURE=true
DATABASE_URL=postgresql://...
```

---

## 🎯 Após Deploy

1. **Acessar aplicação**
2. **Fazer login** com dev-login
3. **Testar endpoints**:
   ```bash
   curl https://seu-app.com/api/health
   ```

---

## 🆘 Troubleshooting

### "Cannot find module"
```bash
pip install -r requirements.txt
```

### "Port already in use"
```bash
# Mudar porta
python backend.py --port 8000
```

### "Database connection error"
```bash
# Verificar DATABASE_URL
heroku config:get DATABASE_URL
# ou
az webapp config appsettings list --name seu-app
```

### "500 Internal Server Error"
```bash
# Ver logs
heroku logs --tail
# ou
az webapp log tail --name seu-app --resource-group seu-grupo
```

---

## 🔒 Segurança Essencial

✅ **Já configurado:**
- Rate limiting
- CORS
- Soft delete

⚠️ **Fazer em produção:**
- [ ] Reabilitar CSRF (remover `@csrf.exempt`)
- [ ] HTTPS obrigatório
- [ ] Backup automático
- [ ] Monitoramento

---

## 💰 Custos Estimados

| Plataforma | 1º Mês | Depois |
|-----------|--------|--------|
| Heroku    | $0     | $50-200 (hibernação) |
| Azure     | $0     | $30-100 |
| VPS       | $5     | $5/mês |

---

## 📞 Próximas Etapas

1. **Escolher plataforma** (Heroku = mais fácil)
2. **Executar script de deploy**
3. **Testar aplicação**
4. **Configurar domínio próprio** (opcional)
5. **Ativar HTTPS** (Let's Encrypt)
6. **Monitorar performance**

---

## 🎓 Aprender Mais

- **Heroku Deploy**: https://devcenter.heroku.com/articles/getting-started-with-python
- **Azure Deploy**: https://learn.microsoft.com/en-us/azure/app-service/app-service-web-get-started-python
- **Production Best Practices**: https://flask.palletsprojects.com/deployment/

---

**Qual opção você escolhe? 🚀**

- ⚡ **Heroku** - Mais fácil e rápido
- 🔷 **Azure** - Melhor custo-benefício
- 🖥️ **VPS** - Máximo controle
