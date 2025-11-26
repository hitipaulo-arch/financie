# ⚡ AÇÃO IMEDIATA - Erro 503

## 🎯 Seu App:
```
https://xn--gesto-bxcyhfgmhuengmeb-g4b.brazilsouth-01.azurewebsites.net
Status: 503 (Não disponível)
```

---

## ✅ FAÇA AGORA:

### 1️⃣ VERIFICAR LOGS (5 minutos)

```
1. Azure Portal: https://portal.azure.com
2. Procure seu App Service
3. Menu Esquerdo: "Log stream"
4. Procure por "ERROR" ou "Exception"
5. Copie qualquer erro que apareça
```

### 2️⃣ VERIFICAR VARIÁVEIS (5 minutos)

```
1. App Service → "Configuration"
2. Procure por: DATABASE_URL, FLASK_ENV, DEBUG, SECRET_KEY
3. Se faltar alguma, adicione
4. Clique "Save"
```

### 3️⃣ VERIFICAR BANCO (5 minutos)

```
1. PostgreSQL → Seu servidor
2. "Networking" → Marque "Allow public access"
3. "Status" → Deve estar "Online" (verde)
```

### 4️⃣ REINICIAR APP (2 minutos)

```
1. App Service → Clique "Restart" (topo)
2. Aguarde 1-2 minutos
3. Recarregue página no navegador
```

---

## 🆘 PROBLEMA MAIS COMUM:

**Falta `gunicorn` em requirements.txt**

**Solução rápida**:
```powershell
cd c:\Users\automacao\my-project\Gestão_financeiro2.0\gestor-financeiro

# Adicionar gunicorn
echo "gunicorn==21.2.0" >> requirements.txt

# Fazer commit
git add requirements.txt
git commit -m "Fix: Adicionar gunicorn para Azure"
git push origin main

# Aguarde 5 minutos para Azure fazer novo deploy
```

---

## 📊 PRÓXIMAS AÇÕES:

```
1. Ler TROUBLESHOOTING_503.md (Completo)
2. Seguir PASSO 1 do guia
3. Se tiver ERROR nos logs, reportar
4. Corrigir e fazer git push
5. Aguardar novo deployment
```

---

**Qual é o primeiro erro que você vê nos logs?**

Copie e cole aqui para eu ajudar! 👇
