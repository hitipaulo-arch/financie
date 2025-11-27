#!/usr/bin/env python
"""
WSGI entry point para gunicorn.
Azure/gunicorn procura por 'app' neste arquivo.
"""

import os
import sys
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("=" * 60)
logger.info("WSGI: Iniciando wsgi.py")
logger.info("=" * 60)

try:
    logger.info("Importando backend...")
    from backend import create_app
    
    logger.info("Criando Flask app...")
    app = create_app()
    
    logger.info(f"✅ WSGI ready - Flask app criado com sucesso")
    logger.info(f"✅ Rotas disponíveis: {len([r for r in app.url_map.iter_rules()])}")
    logger.info("=" * 60)
    
except Exception as e:
    logger.error("=" * 60)
    logger.error(f"❌ ERRO ao criar app em wsgi.py")
    logger.error(f"   Tipo: {type(e).__name__}")
    logger.error(f"   Msg: {str(e)}")
    logger.error("=" * 60)
    import traceback
    traceback.print_exc()
    raise

# Export 'app' para gunicorn encontrar
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
