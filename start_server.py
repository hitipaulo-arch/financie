"""Script para iniciar o servidor Flask facilmente"""
import os
import sys

# Garantir que estamos no diretório correto
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("INICIANDO SERVIDOR GESTOR FINANCEIRO")
print("=" * 60)
print("\n⚠️  IMPORTANTE: Faça login antes de usar os endpoints!")
print("\nPowerShell:")
print("  $body = @{user_id='test_user'; email='test@example.com'} | ConvertTo-Json")
print("  Invoke-RestMethod -Uri http://127.0.0.1:5000/auth/dev-login `")
print("    -Method POST -Body $body -ContentType 'application/json' `")
print("    -SessionVariable websession")
print("\nEndpoint: http://127.0.0.1:5000")
print("API Docs: http://127.0.0.1:5000/api/health")
print("\nEndpoints disponíveis:")
print("  POST /auth/dev-login (⚠️  LOGIN OBRIGATÓRIO)")
print("  GET  /api/health")
print("  GET  /api/users/<user_id>/transactions")
print("  POST /api/users/<user_id>/transactions")
print("  GET  /api/users/<user_id>/openfinance/consents")
print("  POST /api/users/<user_id>/openfinance/consents")
print("  POST /api/users/<user_id>/openfinance/sync")
print("\nOu execute: python test_openfinance.py (testes automáticos)")
print("\nPressione Ctrl+C para parar o servidor")
print("=" * 60)
print()

# Importar e iniciar o app
from backend import app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
