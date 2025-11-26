#!/usr/bin/env python
"""Verify all required imports are available."""

import sys

imports_required = [
    "flask",
    "flask_cors",
    "flask_limiter",
    "flask_wtf",
    "sqlalchemy",
    "marshmallow",
    "authlib",
    "dotenv",
    "requests",
    "pydantic"
]

print("[CHECK] Verificando imports requeridos...")
errors = []

for module in imports_required:
    try:
        __import__(module)
        print(f"✅ {module}")
    except ImportError as e:
        print(f"❌ {module}: {e}")
        errors.append(module)

if errors:
    print(f"\n❌ Faltam {len(errors)} módulos: {', '.join(errors)}")
    sys.exit(1)
else:
    print(f"\n✅ Todos os {len(imports_required)} módulos estão disponíveis!")
    
print("\n[CHECK] Verificando providers.py...")
try:
    from providers import SimulatedProvider, OpenFinanceProvider
    print("✅ providers.py imports OK")
except ImportError as e:
    print(f"❌ providers.py: {e}")
    sys.exit(1)

print("\n[CHECK] Verificando logger.py...")
try:
    from logger import logger, LogContext
    print("✅ logger.py imports OK")
except ImportError as e:
    print(f"❌ logger.py: {e}")
    sys.exit(1)

print("\n✅ TODOS OS ERROS VERIFICADOS - TUDO OK!")
