#!/usr/bin/env python
"""
Teste específico de variáveis de ambiente para Azure
"""

import os
print("=" * 70)
print("VARIÁVEIS DE AMBIENTE DETECTADAS")
print("=" * 70)

# Variáveis que backend.py espera
backend_vars = {
    'GF_DB_URL': 'Banco de dados (se não definir, usa SQLite)',
    'FLASK_SECRET_KEY': 'Chave secreta do Flask',
    'GOOGLE_CLIENT_ID': 'Google OAuth Client ID',
    'GOOGLE_CLIENT_SECRET': 'Google OAuth Secret',
}

# Variáveis que Azure envia
azure_vars = {
    'DATABASE_URL': 'Banco PostgreSQL do Azure',
    'FLASK_ENV': 'Ambiente (production/development)',
    'DEBUG': 'Debug mode',
    'SECRET_KEY': 'Chave secreta',
    'WEBSITE_INSTANCE_ID': 'ID da instância (Azure)',
}

print("\n📋 VARIÁVEIS ESPERADAS POR backend.py:")
for var, desc in backend_vars.items():
    value = os.getenv(var)
    if value:
        print(f"  ✅ {var} = {value[:30]}...")
    else:
        print(f"  ❌ {var} = NÃO DEFINIDO")
        print(f"     └─ {desc}")

print("\n📋 VARIÁVEIS ENVIADAS PELO AZURE:")
for var, desc in azure_vars.items():
    value = os.getenv(var)
    if value:
        print(f"  ✅ {var} = {value[:30]}...")
    else:
        print(f"  ❌ {var} = NÃO DEFINIDO")
        print(f"     └─ {desc}")

print("\n" + "=" * 70)
print("PROBLEMA IDENTIFICADO:")
print("=" * 70)
print("""
Azure envia:
  - DATABASE_URL (postgres://...)
  - SECRET_KEY (sua chave secreta)

backend.py espera:
  - GF_DB_URL (se quiser usar DB customizado)
  - FLASK_SECRET_KEY (para Flask internamente)

SOLUÇÃO:
  backend.py precisa ler DATABASE_URL e SECRET_KEY do Azure
  e mapear para GF_DB_URL e FLASK_SECRET_KEY
""")

print("\n" + "=" * 70)
print("AÇÕES NECESSÁRIAS:")
print("=" * 70)
print("""
1. Modificar backend.py para ler as variáveis corretas do Azure
2. Ou
   Adicionar variáveis no Azure com nomes: GF_DB_URL, FLASK_SECRET_KEY
""")
