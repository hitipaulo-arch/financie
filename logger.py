"""Módulo de logging estruturado em JSON para ambiente de produção.

Fornece formatação JSON com campos contextuais (user_id, endpoint, duration, error_code).
"""
import logging
import json
import sys
from datetime import datetime, UTC
from typing import Optional
import os

class StructuredFormatter(logging.Formatter):
    """Formata logs como JSON estruturado."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Adiciona campos customizados se presentes em record.__dict__
        custom_fields = ["user_id", "endpoint", "method", "status_code", "duration_ms", "error_code"]
        for field in custom_fields:
            if hasattr(record, field):
                value = getattr(record, field, None)
                if value is not None:
                    log_obj[field] = value
        
        # Inclui exceção se houver
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_obj, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    """Retorna logger estruturado configurado.
    
    Args:
        name: Nome do logger (tipicamente __name__).
    
    Returns:
        Logger configurado com handler JSON.
    """
    logger = logging.getLogger(name)
    
    # Evita duplicação de handlers se chamado múltiplas vezes
    if logger.handlers:
        return logger
    
    # Define nível de log a partir de env (padrão: INFO)
    level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level_str, logging.INFO))
    
    # Handler para stdout (production-friendly)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    logger.addHandler(handler)
    
    # Evita propagação para root logger
    logger.propagate = False
    
    return logger


class LogContext:
    """Context manager para adicionar campos estruturados ao log."""
    
    def __init__(self, logger: logging.Logger, **fields):
        self.logger = logger
        self.fields = fields
    
    def __enter__(self):
        # Adiciona fields ao logger para próximo log
        self._original_factory = logging.getLogRecordFactory()
        
        def custom_factory(*args, **kwargs):
            record = self._original_factory(*args, **kwargs)
            for key, value in self.fields.items():
                setattr(record, key, value)
            return record
        
        logging.setLogRecordFactory(custom_factory)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restaura factory original
        logging.setLogRecordFactory(self._original_factory)


# Logger padrão para backend
logger = get_logger("gestor_financeiro.backend")
