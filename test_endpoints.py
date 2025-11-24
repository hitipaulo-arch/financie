#!/usr/bin/env python
"""Script de teste de endpoints - simula requests com sessão autenticada."""
import requests
import json

BASE_URL = "http://localhost:5000"
USER_ID = "test_user_123"

print("=" * 70)
print("TESTE DE ENDPOINTS - GESTOR FINANCEIRO")
print("=" * 70)

# 1. Criar transação de renda
print("\n1️⃣ CRIANDO TRANSAÇÃO (RENDA)...")
payload = {
    "description": "Salário Novembro",
    "amount": 5000.0,
    "type": "income",
    "date": "2025-11-24"
}
try:
    # Em modo teste, não precisa de autenticação
    r = requests.post(f"{BASE_URL}/api/users/{USER_ID}/transactions", json=payload)
    print(f"Status: {r.status_code}")
    if r.status_code in [200, 201]:
        data = r.json()
        print(f"✅ Criada transação ID: {data.get('id')}")
        print(f"   Descrição: {data.get('description')}")
        print(f"   Valor: R$ {data.get('amount')}")
    else:
        print(f"❌ Erro: {r.text}")
except Exception as e:
    print(f"❌ Erro de conexão: {e}")

# 2. Criar despesa
print("\n2️⃣ CRIANDO TRANSAÇÃO (DESPESA)...")
payload = {
    "description": "Supermercado",
    "amount": 150.75,
    "type": "expense",
    "date": "2025-11-24"
}
try:
    r = requests.post(f"{BASE_URL}/api/users/{USER_ID}/transactions", json=payload)
    if r.status_code in [200, 201]:
        data = r.json()
        print(f"✅ Criada transação ID: {data.get('id')}")
        print(f"   Descrição: {data.get('description')}")
        print(f"   Valor: R$ {data.get('amount')}")
    else:
        print(f"❌ Erro: {r.text}")
except Exception as e:
    print(f"❌ Erro: {e}")

# 3. Listar transações
print("\n3️⃣ LISTANDO TRANSAÇÕES...")
try:
    r = requests.get(f"{BASE_URL}/api/users/{USER_ID}/transactions")
    if r.status_code == 200:
        txns = r.json()
        print(f"✅ Total de transações: {len(txns)}")
        for txn in txns[:3]:  # Mostrar primeiras 3
            print(f"   • {txn.get('description')} ({txn.get('type')}) - R$ {txn.get('amount')}")
    else:
        print(f"❌ Erro: {r.text}")
except Exception as e:
    print(f"❌ Erro: {e}")

# 4. Resumo financeiro
print("\n4️⃣ RESUMO FINANCEIRO...")
try:
    r = requests.get(f"{BASE_URL}/api/users/{USER_ID}/summary")
    if r.status_code == 200:
        summary = r.json()
        print(f"✅ Resumo:")
        print(f"   Renda: R$ {summary.get('income')}")
        print(f"   Despesas Avulsas: R$ {summary.get('expenses_avulsa')}")
        print(f"   Saldo: R$ {summary.get('balance')}")
    else:
        print(f"❌ Erro: {r.text}")
except Exception as e:
    print(f"❌ Erro: {e}")

# 5. Criar consentimento Open Finance
print("\n5️⃣ CRIANDO CONSENTIMENTO OPEN FINANCE...")
payload = {
    "provider": "simulated",
    "scopes": "accounts:read transactions:read"
}
try:
    r = requests.post(f"{BASE_URL}/api/users/{USER_ID}/openfinance/consents", json=payload)
    if r.status_code in [200, 201]:
        consent = r.json()
        consent_id = consent.get('consent_id')
        print(f"✅ Consentimento criado!")
        print(f"   ID: {consent_id}")
        print(f"   Status: {consent.get('status')}")
        print(f"   Provider: {consent.get('provider')}")
    else:
        print(f"❌ Erro: {r.text}")
except Exception as e:
    print(f"❌ Erro: {e}")

# 6. Sincronizar Open Finance
print("\n6️⃣ SINCRONIZANDO OPEN FINANCE...")
try:
    r = requests.post(f"{BASE_URL}/api/users/{USER_ID}/openfinance/sync")
    if r.status_code in [200, 201]:
        sync = r.json()
        print(f"✅ Sincronização concluída!")
        print(f"   Importadas: {sync.get('imported')} transações")
        print(f"   Duplicadas ignoradas: {sync.get('skipped_duplicates')}")
        print(f"   Fonte: {sync.get('source')}")
    else:
        print(f"❌ Erro: {r.text}")
except Exception as e:
    print(f"❌ Erro: {e}")

# 7. Listar transações após sync
print("\n7️⃣ LISTANDO TRANSAÇÕES APÓS SYNC...")
try:
    r = requests.get(f"{BASE_URL}/api/users/{USER_ID}/transactions")
    if r.status_code == 200:
        txns = r.json()
        print(f"✅ Total de transações agora: {len(txns)}")
    else:
        print(f"❌ Erro: {r.text}")
except Exception as e:
    print(f"❌ Erro: {e}")

print("\n" + "=" * 70)
print("TESTES CONCLUÍDOS")
print("=" * 70)
