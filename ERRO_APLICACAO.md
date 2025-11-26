# 🔧 ERRO DE APLICAÇÃO - Diagnosticar e Resolver

## ❌ Erro Atual:
```
Application Error
```

---

## 🔍 DIAGNÓSTICO RÁPIDO:

### PASSO 1: Ver os Logs Detalhados

1. Abra Azure Portal: https://portal.azure.com
2. Vá para seu App Service
3. Clique em **"Log stream"**
4. Procure por:
   - `ERROR`
   - `Exception`
   - `Traceback`
   - `ModuleNotFoundError`

**Cole aqui o erro que você vê nos logs!** 👇

---

## 🚨 ERROS MAIS COMUNS:

### 1️⃣ ModuleNotFoundError: No module named 'xxx'

**Solução:**
```
requirements.txt incompleto
Adicione o módulo faltante
git push
Azure fará novo deploy
```

### 2️⃣ psycopg2 ImportError

**Solução:**
```powershell
# Adicionar ao requirements.txt:
psycopg2-binary==2.9.9
```

### 3️⃣ Flask ImportError

**Solução:**
```
requirements.txt corrompido
Recrie:
Flask==3.0.2
flask-cors==4.0.0
... etc
```

### 4️⃣ DATABASE_URL inválido

**Solução:**
1. App Service → Configuration
2. Verificar DATABASE_URL
3. Deve ter formato: `postgresql://...`

### 5️⃣ ImportError: cannot import name

**Solução:**
```
Erro no backend.py
Verificar sintaxe
Fazer git push
```

---

## ✅ AÇÕES IMEDIATAS:

### Opção A: Ver Logs (5 minutos)

```
1. Azure Portal
2. App Service → Log stream
3. Copiar primeiro ERROR
4. Colar aqui para eu ajudar
```

### Opção B: Reiniciar App (2 minutos)

```
1. App Service → Clique "Restart" (topo)
2. Aguarde 1-2 minutos
3. Recarregue página
```

### Opção C: Recriação Completa (Nuclear)

Se nada funcionar:
```
1. Deletar App Service
2. Deletar PostgreSQL
3. Deletar Resource Group
4. Começar do zero
```

---

## 🐛 DEBUGAR LOCALMENTE PRIMEIRO:

Teste seu app na máquina antes de fazer push:

```powershell
cd c:\Users\automacao\my-project\Gestão_financeiro2.0\gestor-financeiro

# Ativar ambiente
.\.venv\Scripts\Activate.ps1

# Instalar dependências
pip install -r requirements.txt

# Rodar servidor
python backend.py

# Testar em navegador
# http://localhost:5000
```

Se funcionar localmente → O problema é no Azure
Se não funcionar localmente → O problema é no código

---

## 🔧 SE VOCÊ VER "ModuleNotFoundError":

**Exemplo:**
```
ModuleNotFoundError: No module named 'flask'
```

**Solução:**

1. Verifique `requirements.txt`:
```
Flask==3.0.2
flask-cors==4.0.0
Flask-Limiter==3.5.0
Flask-WTF==1.2.1
SQLAlchemy==2.0.31
marshmallow==3.21.2
python-dotenv==1.0.1
pytest==8.3.3
pytest-cov==5.0.0
Authlib==1.3.2
requests==2.32.3
Pydantic==2.5.0
gunicorn==21.2.0
psycopg2-binary==2.9.9
```

2. Commit e push:
```powershell
git add requirements.txt
git commit -m "Fix: Adicionar módulos faltantes"
git push origin main
```

3. Aguarde 5-10 minutos

---

## 📋 CHECKLIST DE TROUBLESHOOTING:

- [ ] Ver logs completos em "Log stream"
- [ ] Copiar erro exato
- [ ] Verificar requirements.txt
- [ ] Verificar backend.py sintaxe
- [ ] Verificar DATABASE_URL
- [ ] Fazer git push com fixes
- [ ] Aguardar novo deployment
- [ ] Recarregar página

---

## 🆘 PRECISO DE SUA AJUDA:

**O que você vê nos logs?**

Copie a primeira mensagem de erro e cole aqui 👇

Será:
```
ERROR
Exception
ModuleNotFoundError
ImportError
ConnectionError
... etc
```

---

## 💾 VERIFICAR requirements.txt:

```powershell
cd c:\Users\automacao\my-project\Gestão_financeiro2.0\gestor-financeiro
cat requirements.txt
```

Deve mostrar:
```
Flask==3.0.2
flask-cors==4.0.0
... etc
gunicorn==21.2.0
psycopg2-binary==2.9.9
```

---

## 🚀 APÓS RESOLVER O ERRO:

1. ✅ Ver "Application started" nos logs
2. ✅ Recarregar página
3. ✅ Ver página inicial
4. ✅ Fazer login
5. ✅ Criar transação
6. ✅ Testar endpoints

---

**Qual é a primeira linha de erro que você vê nos logs?** 👇

Copie e cole para eu ajudar!
