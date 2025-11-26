# 🔧 TROUBLESHOOTING - Erro 503 no Azure

## 🎯 Seu URL:
```
https://xn--gesto-bxcyhfgmhuengmeb-g4b.brazilsouth-01.azurewebsites.net
```

## ❌ Status Atual:
```
Erro 503: Servidor Não Disponível
```

---

## 🔍 CAUSAS POSSÍVEIS:

1. **Deployment ainda em andamento**
   - Azure está fazendo deploy
   - Pode levar 5-10 minutos

2. **Erro na configuração do banco**
   - DATABASE_URL inválido
   - Firewall bloqueando

3. **Variáveis de ambiente faltando**
   - FLASK_ENV não definido
   - SECRET_KEY ausente

4. **Application não está iniciando**
   - requirements.txt incompleto
   - backend.py com erro

---

## ✅ SOLUÇÃO PASSO A PASSO:

### PASSO 1: Verificar Status do Deployment

1. Abra Azure Portal: https://portal.azure.com
2. Procure seu App Service
3. Clique em **"Deployment Center"**
4. Veja o status:
   - 🟢 Verde = Sucesso
   - 🔴 Vermelho = Erro
   - ⏳ Azul = Em progresso

### PASSO 2: Verificar Logs

1. No App Service, clique em **"Log stream"**
2. Procure por:
   ```
   Application started successfully
   ERROR
   Exception
   ```

**Se vir ERROR**:
- Copie a mensagem de erro
- Passe para o PASSO 3

**Se vir "Application started"**:
- Aguarde mais 2 minutos
- Recarregue no navegador

### PASSO 3: Verificar Variáveis de Ambiente

1. No App Service, clique em **"Configuration"**
2. Verifique se tem estas variáveis:
   - ✅ DATABASE_URL
   - ✅ FLASK_ENV = production
   - ✅ DEBUG = False
   - ✅ SECRET_KEY

**Se faltar alguma**:
- Clique em **"+ New application setting"**
- Adicione a variável faltante
- Clique em **"OK"**
- Clique em **"Save"** (topo)
- Clique em **"Continue"** (se pedir restart)

### PASSO 4: Verificar Banco de Dados

1. No Azure Portal, procure **"Azure Database for PostgreSQL"**
2. Clique no seu servidor (meu-gestor-financeiro-db)
3. Verifique:
   - **Status**: Verde/Online
   - **Networking**: Firewall configurado

**Se Firewall não tiver "Allow public access from Azure"**:
1. Clique em **"Networking"**
2. Marque: "Allow public access from any Azure service..."
3. Clique em **"Save"**

### PASSO 5: Testar Conexão com Banco

No seu computador, teste:

```powershell
# Instalar psycopg2 se não tiver
pip install psycopg2-binary

# Testar conexão
python -c "
import psycopg2
conn = psycopg2.connect(
    'postgresql://postgres:Senha123!@#@meu-gestor-financeiro-db.postgres.database.azure.com:5432/postgres?sslmode=require'
)
print('Conectado com sucesso!')
conn.close()
"
```

**Se conectar**: Banco está OK
**Se falhar**: Problema no DATABASE_URL

### PASSO 6: Reiniciar App Service

1. No App Service, clique em **"Restart"** (topo)
2. Aguarde 1-2 minutos
3. Tente acessar novamente

### PASSO 7: Verificar requirements.txt

1. Volte para seu computador
2. Abra `requirements.txt`
3. Verifique se tem:
   ```
   Flask==3.0.2
   SQLAlchemy==2.0.31
   psycopg2-binary==2.9.9
   python-dotenv
   marshmallow
   Flask-Cors
   Flask-Limiter
   Flask-WTF
   requests
   gunicorn
   ```

**Se faltar** `gunicorn`:
1. Edite requirements.txt
2. Adicione no final: `gunicorn==21.2.0`
3. Salve
4. Faça push: `git push origin main`
5. Azure fará novo deploy automaticamente

---

## 🚨 ERRO 503 MAIS COMUM:

### Causa: Falta de `gunicorn`

**Solução**:
```
1. Edite requirements.txt
2. Adicione: gunicorn==21.2.0
3. git add requirements.txt
4. git commit -m "Fix: Adicionar gunicorn"
5. git push origin main
6. Aguarde 3-5 minutos
```

---

## 📋 CHECKLIST:

- [ ] Verificar status deployment (verde)
- [ ] Ler logs (sem ERROR)
- [ ] Todas as 4 variáveis definidas
- [ ] Firewall do banco configurado
- [ ] Banco está online
- [ ] requirements.txt tem gunicorn
- [ ] Fazer git push (se mudou)
- [ ] Aguardar 5 minutos
- [ ] Recarregar página no navegador

---

## 🔄 SE TUDO ACIMA NÃO FUNCIONAR:

### Nuclear Option (Recomeçar):

1. Delete App Service
2. Delete PostgreSQL
3. Delete Resource Group
4. Comece novamente com AZURE_GUIA_COMPLETO.md
5. Desta vez, verifique cada passo 2x

---

## 💡 DICA:

Enquanto testa, deixe o **Log stream** aberto em uma aba do navegador.
Você verá erros em tempo real!

```
App Service → Log stream → (deixe aberto enquanto testa)
```

---

## ✅ PRÓXIMO PASSO:

1. Abra Log stream
2. Procure por ERROR
3. Se tiver ERROR, copie e cole aqui
4. Vou ajudar a resolver!

---

## 📞 INFORMAÇÕES DO SEU APP:

```
URL: https://xn--gesto-bxcyhfgmhuengmeb-g4b.brazilsouth-01.azurewebsites.net
Region: Brazil South
Status: 503 Unavailable
Next: Verificar logs e variáveis
```

---

**Vamos resolver! Comece pelo PASSO 1** 🚀
