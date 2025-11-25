#!/usr/bin/env python3
"""Script de teste para endpoints de investimentos e dicas."""

import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def test_investments():
    print("=" * 70)
    print("TESTANDO ENDPOINTS DE INVESTIMENTOS")
    print("=" * 70)
    
    session = requests.Session()
    
    # 0. Login
    print("\n0. Fazendo login...")
    try:
        response = session.post(f"{BASE_URL}/auth/dev-login", json={
            "user_id": "test_user",
            "email": "test@example.com",
            "name": "Test User"
        })
        if response.status_code == 200:
            print(f"   ✅ Login bem-sucedido")
        else:
            print(f"   ❌ Erro: {response.status_code}")
            return
    except Exception as e:
        print(f"   ❌ Erro de conexão: {e}")
        return
    
    # 1. Criar investimentos
    print("\n1. Criando investimentos...")
    investments = [
        {
            "name": "Tesla",
            "asset_type": "stocks",
            "amount": 10,
            "purchase_price": 250.00,
            "current_price": 280.00,
            "purchase_date": "2025-09-15",
            "target_return": 15,
            "notes": "Ação de tecnologia"
        },
        {
            "name": "Fundo Imobiliário XYZ",
            "asset_type": "reit",
            "amount": 50,
            "purchase_price": 100.00,
            "current_price": 105.00,
            "purchase_date": "2025-08-20",
            "target_return": 8,
            "notes": "Rendimento mensal"
        },
        {
            "name": "Bitcoin",
            "asset_type": "crypto",
            "amount": 0.5,
            "purchase_price": 45000.00,
            "current_price": 42000.00,
            "purchase_date": "2025-10-01",
            "target_return": 50
        },
        {
            "name": "Fundo de Índice B3",
            "asset_type": "funds",
            "amount": 1000,
            "purchase_price": 50.00,
            "current_price": 52.00,
            "purchase_date": "2025-07-10",
            "target_return": 12
        }
    ]
    
    created_ids = []
    for inv in investments:
        try:
            response = session.post(
                f"{BASE_URL}/api/users/test_user/investments",
                json=inv
            )
            if response.status_code == 201:
                data = response.json()
                created_ids.append(data['id'])
                print(f"   ✅ {inv['name']}: ID {data['id']} (R$ {data['current_price']})")
            else:
                print(f"   ❌ Erro ao criar {inv['name']}: {response.text}")
        except Exception as e:
            print(f"   ❌ Erro: {e}")
    
    # 2. Listar investimentos
    print("\n2. Listando investimentos...")
    try:
        response = session.get(f"{BASE_URL}/api/users/test_user/investments")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Total: {data['pagination']['total']} investimentos")
            for item in data['items'][:3]:
                print(f"      - {item['name']}: {item['asset_type']} (R$ {item['current_price']})")
        else:
            print(f"   ❌ Erro: {response.text}")
    except Exception as e:
        print(f"   ❌ Erro: {e}")
    
    # 3. Atualizar investimento
    if created_ids:
        print(f"\n3. Atualizando investimento...")
        try:
            response = session.patch(
                f"{BASE_URL}/api/users/test_user/investments/{created_ids[0]}",
                json={"current_price": 290.00, "notes": "Preço atualizado"}
            )
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ {data['name']} atualizado (novo preço: R$ {data['current_price']})")
            else:
                print(f"   ❌ Erro: {response.text}")
        except Exception as e:
            print(f"   ❌ Erro: {e}")
    
    # 4. Análise do portfólio
    print("\n4. Analisando portfólio...")
    try:
        response = session.get(f"{BASE_URL}/api/users/test_user/investments/portfolio")
        if response.status_code == 200:
            data = response.json()
            portfolio = data['portfolio']
            print(f"   ✅ Portfólio:")
            print(f"      Investido: R$ {portfolio['total_invested']:.2f}")
            print(f"      Valor atual: R$ {portfolio['current_value']:.2f}")
            print(f"      Ganho/Perda: R$ {portfolio['total_return']:.2f}")
            print(f"      Retorno: {portfolio['return_percentage']:.2f}%")
            print(f"\n   Por tipo de ativo:")
            for asset_type, info in portfolio['by_asset_type'].items():
                print(f"      {asset_type}: R$ {info['current_value']:.2f} ({info['return_percentage']:.1f}%)")
            
            print(f"\n   Recomendações:")
            for rec in data['recommendations']:
                print(f"      {rec['icon']} {rec['title']}")
        else:
            print(f"   ❌ Erro: {response.text}")
    except Exception as e:
        print(f"   ❌ Erro: {e}")
    
    # 5. Obter dicas de investimento
    print("\n5. Consultando dicas de investimento...")
    try:
        response = requests.get(f"{BASE_URL}/api/investments/tips")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Total de dicas: {data['total']}")
            print(f"   Categorias: {', '.join(data['categories'])}")
            print(f"\n   Primeiras 3 dicas:")
            for tip in data['tips'][:3]:
                print(f"      {tip['icon']} {tip['title']}")
                print(f"         {tip['description']}")
        else:
            print(f"   ❌ Erro: {response.text}")
    except Exception as e:
        print(f"   ❌ Erro: {e}")
    
    # 6. Filtrar por tipo de ativo
    print("\n6. Filtrando por tipo de ativo (stocks)...")
    try:
        response = session.get(f"{BASE_URL}/api/users/test_user/investments?asset_type=stocks")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ {data['pagination']['total']} investimentos em stocks")
            for item in data['items']:
                print(f"      - {item['name']}")
        else:
            print(f"   ❌ Erro: {response.text}")
    except Exception as e:
        print(f"   ❌ Erro: {e}")
    
    # 7. Deletar um investimento
    if created_ids and len(created_ids) > 1:
        print(f"\n7. Deletando um investimento...")
        try:
            response = session.delete(
                f"{BASE_URL}/api/users/test_user/investments/{created_ids[-1]}"
            )
            if response.status_code == 200:
                print(f"   ✅ Investimento deletado (ID {created_ids[-1]})")
            else:
                print(f"   ❌ Erro: {response.text}")
        except Exception as e:
            print(f"   ❌ Erro: {e}")
    
    print("\n" + "=" * 70)
    print("TESTES DE INVESTIMENTOS CONCLUÍDOS")
    print("=" * 70)
    print("\nResumo dos endpoints testados:")
    print("  ✓ GET  /api/users/{id}/investments")
    print("  ✓ POST /api/users/{id}/investments")
    print("  ✓ PATCH /api/users/{id}/investments/{inv_id}")
    print("  ✓ DELETE /api/users/{id}/investments/{inv_id}")
    print("  ✓ GET /api/users/{id}/investments/portfolio")
    print("  ✓ GET /api/investments/tips")

if __name__ == "__main__":
    test_investments()
