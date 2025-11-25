"""Script de teste simples para verificar endpoints do Open Finance"""
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def test_endpoints():
    print("=" * 60)
    print("TESTANDO ENDPOINTS DO OPEN FINANCE")
    print("=" * 60)
    
    # Criar sessão
    session = requests.Session()
    
    # 0. Login de desenvolvimento
    print("\n0. Fazendo login de desenvolvimento...")
    try:
        response = session.post(f"{BASE_URL}/auth/dev-login", json={
            "user_id": "test_user",
            "email": "test@example.com",
            "name": "Test User"
        })
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   ✅ Login bem-sucedido: {response.json()['user']['email']}")
        else:
            print(f"   ❌ Erro no login: {response.text}")
            return
    except Exception as e:
        print(f"   ❌ Erro de conexão: {e}")
        print("\n   Certifique-se de que o servidor está rodando:")
        print("   python backend.py")
        return
    
    # 1. Testar criação de transação (sem CSRF para teste)
    print("\n1. Criar uma transação de teste...")
    try:
        response = session.post(f"{BASE_URL}/api/users/test_user/transactions", json={
            "description": "Teste",
            "amount": 100.0,
            "type": "income",
            "date": "2025-11-25"
        })
        print(f"   Status: {response.status_code}")
        if response.status_code == 201:
            print(f"   ✅ Transação criada: {response.json()}")
        else:
            print(f"   ❌ Erro: {response.text}")
    except Exception as e:
        print(f"   ❌ Erro de conexão: {e}")
    
    # 2. Testar criação de consent
    print("\n2. Criar consent do Open Finance...")
    try:
        response = session.post(f"{BASE_URL}/api/users/test_user/openfinance/consents", json={})
        print(f"   Status: {response.status_code}")
        if response.status_code == 201:
            data = response.json()
            print(f"   ✅ Consent criado!")
            print(f"   Consent ID: {data.get('consent_id')}")
            print(f"   Provider: {data.get('provider')}")
        else:
            print(f"   ❌ Erro: {response.text}")
    except Exception as e:
        print(f"   ❌ Erro de conexão: {e}")
    
    # 3. Listar consents
    print("\n3. Listar consents...")
    try:
        response = session.get(f"{BASE_URL}/api/users/test_user/openfinance/consents")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Total de consents: {len(data.get('consents', []))}")
            for consent in data.get('consents', []):
                print(f"      - {consent.get('provider')}: {consent.get('status')}")
        else:
            print(f"   ❌ Erro: {response.text}")
    except Exception as e:
        print(f"   ❌ Erro de conexão: {e}")
    
    # 4. Sincronizar transações
    print("\n4. Sincronizar transações do Open Finance...")
    try:
        response = session.post(f"{BASE_URL}/api/users/test_user/openfinance/sync")
        print(f"   Status: {response.status_code}")
        if response.status_code == 201:
            data = response.json()
            print(f"   ✅ Sincronização concluída!")
            print(f"   Importadas: {data.get('imported')}")
            print(f"   Duplicadas: {data.get('skipped_duplicates')}")
            print(f"   Source: {data.get('source')}")
        else:
            print(f"   ❌ Erro: {response.text}")
    except Exception as e:
        print(f"   ❌ Erro de conexão: {e}")
    
    # 5. Listar transações
    print("\n5. Listar todas as transações...")
    try:
        response = session.get(f"{BASE_URL}/api/users/test_user/transactions")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Total: {data['pagination']['total']} transações")
            for txn in data['items'][:5]:  # Mostrar primeiras 5
                print(f"      - {txn['date']}: {txn['description']} - R$ {txn['amount']}")
        else:
            print(f"   ❌ Erro: {response.text}")
    except Exception as e:
        print(f"   ❌ Erro de conexão: {e}")
    
    print("\n" + "=" * 60)
    print("TESTES CONCLUÍDOS")
    print("=" * 60)
    print("\nSe houver erros de conexão, certifique-se de que o servidor")
    print("está rodando com: python backend.py")

if __name__ == "__main__":
    test_endpoints()
