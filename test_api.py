"""Script para testar os endpoints da API manualmente"""
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def print_response(title, response):
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

def test_api():
    session = requests.Session()
    
    # 1. Test health endpoint
    print("\n🔍 TESTANDO ENDPOINTS DE SAÚDE")
    r = session.get(f"{BASE_URL}/")
    print_response("GET /", r)
    
    r = session.get(f"{BASE_URL}/api/health")
    print_response("GET /api/health", r)
    
    # 2. Get CSRF token
    print("\n🔒 OBTENDO CSRF TOKEN")
    r = session.get(f"{BASE_URL}/api/csrf-token")
    print_response("GET /api/csrf-token", r)
    csrf_token = r.json()["csrf_token"]
    
    # 3. Test transactions (empty list)
    print("\n📊 TESTANDO TRANSAÇÕES")
    r = session.get(f"{BASE_URL}/api/transactions")
    print_response("GET /api/transactions (vazio)", r)
    
    # 4. Create a transaction
    transaction_data = {
        "description": "Teste de transação via API",
        "amount": 150.75,
        "type": "income",
        "category": "Salário"
    }
    headers = {"X-CSRFToken": csrf_token}
    r = session.post(f"{BASE_URL}/api/transactions", 
                     json=transaction_data, 
                     headers=headers)
    print_response("POST /api/transactions", r)
    
    if r.status_code == 201:
        transaction_id = r.json()["id"]
        
        # 5. Get transactions (with data)
        r = session.get(f"{BASE_URL}/api/transactions")
        print_response("GET /api/transactions (com dados)", r)
        
        # 6. Test pagination
        print("\n📄 TESTANDO PAGINAÇÃO")
        r = session.get(f"{BASE_URL}/api/transactions?page=1&per_page=5")
        print_response("GET /api/transactions?page=1&per_page=5", r)
        
        # 7. Get summary
        print("\n📈 TESTANDO RESUMO")
        r = session.get(f"{BASE_URL}/api/summary")
        print_response("GET /api/summary", r)
        
        # 8. Update transaction
        print("\n✏️ TESTANDO ATUALIZAÇÃO")
        update_data = {
            "description": "Transação atualizada via API",
            "amount": 200.00
        }
        r = session.put(f"{BASE_URL}/api/transactions/{transaction_id}", 
                       json=update_data, 
                       headers=headers)
        print_response(f"PUT /api/transactions/{transaction_id}", r)
        
        # 9. Test soft delete
        print("\n🗑️ TESTANDO SOFT DELETE")
        r = session.delete(f"{BASE_URL}/api/transactions/{transaction_id}", 
                          headers=headers)
        print_response(f"DELETE /api/transactions/{transaction_id}", r)
        
        # 10. Verify soft delete
        r = session.get(f"{BASE_URL}/api/transactions")
        print_response("GET /api/transactions (após soft delete)", r)
    
    # 11. Test Open Finance
    print("\n🏦 TESTANDO OPEN FINANCE")
    consent_data = {
        "institution": "Banco Exemplo",
        "consent_id": "consent-123-test"
    }
    r = session.post(f"{BASE_URL}/api/openfinance/consent", 
                     json=consent_data, 
                     headers=headers)
    print_response("POST /api/openfinance/consent", r)
    
    if r.status_code == 201:
        r = session.post(f"{BASE_URL}/api/openfinance/sync", 
                        headers=headers)
        print_response("POST /api/openfinance/sync", r)
    
    print("\n" + "="*60)
    print("✅ TESTES CONCLUÍDOS!")
    print("="*60 + "\n")

if __name__ == "__main__":
    try:
        test_api()
    except requests.exceptions.ConnectionError:
        print("❌ ERRO: Não foi possível conectar ao servidor.")
        print("   Certifique-se de que o backend está rodando em http://127.0.0.1:5000")
    except Exception as e:
        print(f"❌ ERRO: {e}")
