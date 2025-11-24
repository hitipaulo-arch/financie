"""Testes automatizados para API do Gestor Financeiro."""
import pytest
import os
import tempfile
from datetime import date
from backend import create_app, Base, engine


@pytest.fixture
def app():
    """Cria app Flask para testes com DB temporária."""
    # Usar DB em memória para testes
    os.environ["GF_DB_URL"] = "sqlite:///:memory:"
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False  # Desabilitar CSRF em testes
    
    with app.app_context():
        Base.metadata.create_all(engine)
    
    yield app
    
    # Cleanup
    with app.app_context():
        Base.metadata.drop_all(engine)


@pytest.fixture
def client(app):
    """Cliente de testes Flask."""
    return app.test_client()


class TestHealth:
    def test_health_endpoint(self, client):
        """Testa endpoint /api/health."""
        response = client.get('/api/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'ok'

    def test_root_endpoint(self, client):
        """Testa endpoint raiz /."""
        response = client.get('/')
        assert response.status_code == 200
        data = response.get_json()
        assert 'message' in data


class TestTransactions:
    def test_list_empty_transactions(self, client):
        """Testa listagem vazia inicial (com paginação)."""
        response = client.get('/api/users/test_user/transactions')
        assert response.status_code == 200
        data = response.get_json()
        # Estrutura paginada
        assert 'items' in data
        assert 'pagination' in data
        assert data['items'] == []
        assert data['pagination']['total'] == 0
        assert data['pagination']['pages'] == 0

    def test_create_transaction(self, client):
        """Testa criação de transação."""
        payload = {
            "description": "Salário Teste",
            "amount": 3000.50,
            "type": "income"
        }
        response = client.post(
            '/api/users/test_user/transactions',
            json=payload,
            content_type='application/json'
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data['description'] == "Salário Teste"
        assert data['amount'] == 3000.50
        assert data['type'] == "income"
        assert 'id' in data
        assert 'date' in data

    def test_create_transaction_with_date(self, client):
        """Testa criação com data específica."""
        payload = {
            "description": "Compra Antiga",
            "amount": 150.00,
            "type": "expense",
            "date": "2025-11-01"
        }
        response = client.post('/api/users/test_user/transactions', json=payload)
        assert response.status_code == 201
        data = response.get_json()
        assert data['date'] == "2025-11-01"

    def test_create_invalid_transaction(self, client):
        """Testa validação de campos inválidos."""
        payload = {"description": "", "amount": -100, "type": "invalid"}
        response = client.post('/api/users/test_user/transactions', json=payload)
        assert response.status_code == 400

    def test_update_transaction(self, client):
        """Testa atualização de transação."""
        # Criar
        payload = {"description": "Original", "amount": 100, "type": "income"}
        create_resp = client.post('/api/users/test_user/transactions', json=payload)
        txn_id = create_resp.get_json()['id']
        
        # Atualizar
        update_payload = {"description": "Atualizado", "amount": 200}
        response = client.patch(f'/api/users/test_user/transactions/{txn_id}', json=update_payload)
        assert response.status_code == 200
        data = response.get_json()
        assert data['description'] == "Atualizado"
        assert data['amount'] == 200

    def test_delete_transaction(self, client):
        """Testa remoção de transação."""
        # Criar
        payload = {"description": "Para Deletar", "amount": 50, "type": "expense"}
        create_resp = client.post('/api/users/test_user/transactions', json=payload)
        txn_id = create_resp.get_json()['id']
        
        # Deletar
        response = client.delete(f'/api/users/test_user/transactions/{txn_id}')
        assert response.status_code == 200
        
        # Verificar que foi deletado (com paginação)
        list_resp = client.get('/api/users/test_user/transactions')
        data = list_resp.get_json()
        assert len(data['items']) == 0
        assert data['pagination']['total'] == 0

    def test_delete_nonexistent_transaction(self, client):
        """Testa deletar transação inexistente."""
        response = client.delete('/api/users/test_user/transactions/9999')
        assert response.status_code == 404


class TestInstallments:
    def test_list_empty_installments(self, client):
        """Testa listagem vazia de parcelas (com paginação)."""
        response = client.get('/api/users/test_user/installments')
        assert response.status_code == 200
        data = response.get_json()
        assert 'items' in data
        assert 'pagination' in data
        assert data['items'] == []
        assert data['pagination']['total'] == 0

    def test_create_installment(self, client):
        """Testa criação de parcela."""
        payload = {
            "description": "Notebook Parcelado",
            "monthly_value": 299.90,
            "total_months": 12
        }
        response = client.post('/api/users/test_user/installments', json=payload)
        assert response.status_code == 201
        data = response.get_json()
        assert data['description'] == "Notebook Parcelado"
        assert data['monthly_value'] == 299.90
        assert data['total_months'] == 12

    def test_update_installment(self, client):
        """Testa atualização de parcela."""
        # Criar
        payload = {"description": "Original", "monthly_value": 100, "total_months": 6}
        create_resp = client.post('/api/users/test_user/installments', json=payload)
        inst_id = create_resp.get_json()['id']
        
        # Atualizar
        update_payload = {"total_months": 10}
        response = client.patch(f'/api/users/test_user/installments/{inst_id}', json=update_payload)
        assert response.status_code == 200
        data = response.get_json()
        assert data['total_months'] == 10

    def test_delete_installment(self, client):
        """Testa remoção de parcela."""
        payload = {"description": "Para Deletar", "monthly_value": 50, "total_months": 3}
        create_resp = client.post('/api/users/test_user/installments', json=payload)
        inst_id = create_resp.get_json()['id']
        
        response = client.delete(f'/api/users/test_user/installments/{inst_id}')
        assert response.status_code == 200


class TestSummary:
    def test_empty_summary(self, client):
        """Testa resumo sem transações."""
        response = client.get('/api/users/test_user/summary')
        assert response.status_code == 200
        data = response.get_json()
        assert data['income'] == 0
        assert data['expenses_total'] == 0
        assert data['balance'] == 0

    def test_summary_with_transactions(self, client):
        """Testa cálculo de resumo com transações."""
        # Criar receita
        client.post('/api/users/test_user/transactions', 
                   json={"description": "Salário", "amount": 5000, "type": "income"})
        
        # Criar despesa avulsa
        client.post('/api/users/test_user/transactions',
                   json={"description": "Aluguel", "amount": 1500, "type": "expense"})
        
        # Criar parcela
        client.post('/api/users/test_user/installments',
                   json={"description": "Cartão", "monthly_value": 500, "total_months": 12})
        
        response = client.get('/api/users/test_user/summary')
        data = response.get_json()
        
        assert data['income'] == 5000
        assert data['expenses_avulsa'] == 1500
        assert data['expenses_parcelas'] == 500
        assert data['expenses_total'] == 2000
        assert data['balance'] == 3000


class TestImport:
    def test_import_simulated_data(self, client):
        """Testa importação simulada de extrato."""
        response = client.post('/api/users/test_user/import')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'success'
        assert data['imported'] == 3
        assert len(data['transactions']) == 3
        
        # Verificar que foram criadas (com paginação)
        list_resp = client.get('/api/users/test_user/transactions')
        list_data = list_resp.get_json()
        assert len(list_data['items']) == 3
        assert list_data['pagination']['total'] == 3


class TestOpenFinanceSync:
    def test_open_finance_sync(self, client):
        """Testa sincronização simulada via Open Finance."""
        # Criar consent primeiro
        consent_resp = client.post('/api/users/test_user/openfinance/consents', json={})
        assert consent_resp.status_code == 201
        response = client.post('/api/users/test_user/openfinance/sync')
        assert response.status_code == 201
        data = response.get_json()
        assert data['status'] == 'success'
        assert data['source'] == 'open_finance_simulated'
        assert data['imported'] == 3
        assert len(data['transactions']) == 3
        # Verifica persistência (com paginação)
        list_resp = client.get('/api/users/test_user/transactions')
        list_data = list_resp.get_json()
        assert len(list_data['items']) == 3  # não duplica além das importadas
        assert list_data['pagination']['total'] == 3

    def test_open_finance_sync_dedup(self, client):
        """Segunda sincronização não deve duplicar transações."""
        client.post('/api/users/test_user/openfinance/consents', json={})
        first = client.post('/api/users/test_user/openfinance/sync')
        assert first.status_code == 201
        data1 = first.get_json()
        assert data1['imported'] == 3
        second = client.post('/api/users/test_user/openfinance/sync')
        assert second.status_code == 201
        data2 = second.get_json()
        assert data2['imported'] == 0
        assert data2['skipped_duplicates'] == 3
        list_resp = client.get('/api/users/test_user/transactions')
        list_data = list_resp.get_json()
        assert len(list_data['items']) == 3
        assert list_data['pagination']['total'] == 3

    def test_open_finance_sync_without_consent(self, client):
        """Sync sem consent deve falhar."""
        response = client.post('/api/users/test_user/openfinance/sync')
        assert response.status_code == 400
        data = response.get_json()
        assert data['error'] == 'no_active_consent'


class TestMultiUser:
    def test_user_isolation(self, client):
        """Testa isolamento de dados entre usuários."""
        # Criar transação para user1
        client.post('/api/users/user1/transactions',
                   json={"description": "User1 Txn", "amount": 100, "type": "income"})
        
        # Criar transação para user2
        client.post('/api/users/user2/transactions',
                   json={"description": "User2 Txn", "amount": 200, "type": "income"})
        
        # Verificar isolamento (com paginação)
        user1_resp = client.get('/api/users/user1/transactions')
        user2_resp = client.get('/api/users/user2/transactions')
        
        user1_data = user1_resp.get_json()
        user2_data = user2_resp.get_json()
        
        assert len(user1_data['items']) == 1
        assert len(user2_data['items']) == 1
        assert user1_data['items'][0]['amount'] == 100
        assert user2_data['items'][0]['amount'] == 200


class TestPagination:
    """Testes de paginação dos endpoints GET."""
    
    def test_pagination_default(self, client):
        """Testa paginação com parâmetros padrão."""
        # Criar 5 transações
        for i in range(5):
            client.post('/api/users/test_user/transactions',
                       json={"description": f"Txn {i}", "amount": 100 + i, "type": "income"})
        
        # Requisitar sem parâmetros (deve retornar página 1, 20 itens por padrão)
        response = client.get('/api/users/test_user/transactions')
        data = response.get_json()
        
        assert data['pagination']['current_page'] == 1
        assert data['pagination']['per_page'] == 20
        assert data['pagination']['total'] == 5
        assert data['pagination']['pages'] == 1
        assert len(data['items']) == 5
    
    def test_pagination_with_params(self, client):
        """Testa paginação com query params."""
        # Criar 25 transações
        for i in range(25):
            client.post('/api/users/test_user/transactions',
                       json={"description": f"Txn {i}", "amount": 100, "type": "income"})
        
        # Página 1, 10 itens por página
        response = client.get('/api/users/test_user/transactions?page=1&per_page=10')
        data = response.get_json()
        
        assert data['pagination']['current_page'] == 1
        assert data['pagination']['per_page'] == 10
        assert data['pagination']['total'] == 25
        assert data['pagination']['pages'] == 3
        assert len(data['items']) == 10
        
        # Página 2
        response = client.get('/api/users/test_user/transactions?page=2&per_page=10')
        data = response.get_json()
        
        assert data['pagination']['current_page'] == 2
        assert len(data['items']) == 10
        
        # Página 3 (última, com 5 itens)
        response = client.get('/api/users/test_user/transactions?page=3&per_page=10')
        data = response.get_json()
        
        assert data['pagination']['current_page'] == 3
        assert len(data['items']) == 5
    
    def test_pagination_max_per_page(self, client):
        """Testa limite máximo de itens por página (100)."""
        # Criar 150 transações
        for i in range(150):
            client.post('/api/users/test_user/transactions',
                       json={"description": f"Txn {i}", "amount": 100, "type": "income"})
        
        # Solicitar per_page=1000 (deve ser limitado a 100)
        response = client.get('/api/users/test_user/transactions?per_page=1000')
        data = response.get_json()
        
        assert data['pagination']['per_page'] == 100  # Limitado a 100
        assert len(data['items']) == 100
