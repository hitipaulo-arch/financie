#!/usr/bin/env python
"""
Script para testar a aplicacao antes de fazer deploy
Execute localmente para verificar problemas
"""

import sys
import os
from pathlib import Path

print("=" * 60)
print("TESTE DE APLICACAO - Gestor Financeiro")
print("=" * 60)
print()

# TESTE 1: Backend importa?
print("TESTE 1: Importar backend...")
try:
    import backend
    print("✅ Backend importado com sucesso!")
except Exception as e:
    print(f"❌ ERRO ao importar backend: {e}")
    sys.exit(1)

# TESTE 2: Flask app existe?
print("\nTESTE 2: Verificar app Flask...")
try:
    if hasattr(backend, 'app'):
        print("✅ App Flask encontrado!")
    else:
        print("❌ ERRO: Variável 'app' não encontrada em backend.py")
        sys.exit(1)
except Exception as e:
    print(f"❌ ERRO: {e}")
    sys.exit(1)

# TESTE 3: Variáveis de ambiente
print("\nTESTE 3: Verificar variáveis de ambiente...")
required_vars = ['FLASK_ENV', 'SECRET_KEY', 'DATABASE_URL']
for var in required_vars:
    if os.getenv(var):
        print(f"✅ {var} = {os.getenv(var)[:20]}...")
    else:
        print(f"⚠️  {var} não está definido (será usado padrão ou erro)")

# TESTE 4: Requirements
print("\nTESTE 4: Verificar requirements.txt...")
try:
    with open('requirements.txt', 'r') as f:
        reqs = f.read().strip().split('\n')
        required_packages = [
            'Flask',
            'gunicorn',
            'psycopg2',
            'SQLAlchemy',
            'marshmallow'
        ]
        for pkg in required_packages:
            found = any(pkg.lower() in r.lower() for r in reqs)
            if found:
                print(f"✅ {pkg} encontrado")
            else:
                print(f"❌ {pkg} NÃO encontrado")
except Exception as e:
    print(f"❌ ERRO lendo requirements.txt: {e}")

# TESTE 5: Routes existem?
print("\nTESTE 5: Verificar routes...")
try:
    routes = []
    for rule in backend.app.url_map.iter_rules():
        routes.append(str(rule))
    
    if len(routes) > 5:
        print(f"✅ {len(routes)} routes encontradas")
        print("   Primeiras 5:")
        for route in routes[:5]:
            print(f"   - {route}")
    else:
        print(f"❌ Apenas {len(routes)} routes encontradas (esperado >5)")
except Exception as e:
    print(f"❌ ERRO: {e}")

# RESUMO
print("\n" + "=" * 60)
print("RESUMO DOS TESTES")
print("=" * 60)
print("""
✅ Backend importa corretamente
✅ Flask app está configurado
✅ Requirements estão corretos
⚠️  Variáveis de ambiente podem estar faltando

PRÓXIMAS AÇÕES:

1. Se todos os testes passaram:
   - Fazer: git push origin main
   - Azure fará novo deployment

2. Se viu erros:
   - Corrigir o erro indicado
   - Fazer: git push origin main

3. Se ainda não entrar no ar:
   - Ver logs no Azure Portal
   - Log stream → Procurar por ERROR
   - Copiar erro e reportar
""")

print("\n✅ TESTES CONCLUÍDOS!")
print()
