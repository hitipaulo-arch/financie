#!/usr/bin/env python
"""Script de teste para visualizar logging estruturado em JSON."""
import sys
sys.path.insert(0, '.')

from logger import logger

# Exemplos de logs estruturados
logger.info("Login iniciado", extra={"endpoint": "/auth/login", "method": "GET"})
logger.warning("Tentativa de sync sem consent", extra={"user_id": "user123", "endpoint": "/openfinance/sync", "error_code": "no_active_consent"})
logger.info("Sincronização concluída", extra={"user_id": "user123", "imported": 3, "skipped": 1, "duration_ms": 125.5})

try:
    raise ValueError("Erro simulado de teste")
except ValueError as e:
    logger.error("Erro ao processar transação", extra={"user_id": "user123", "error_code": "invalid_transaction"})

print("\n✓ Logs estruturados em JSON acima.\n")
