"""Configuração do Alembic.

Duas diferenças importantes em relação ao arquivo gerado pelo `alembic init`:

1. **A URL vem do ambiente**, pela MESMA resolução que o backend usa
   (`DATABASE_URL` → `GF_DB_URL` → `sqlite:///data.db`). Antes ficava fixa em
   `alembic.ini`, então rodar as migrações contra o banco de produção exigia
   editar o .ini na mão — e esquecer disso aplicava a migração no `data.db`
   local sem avisar.

2. **`render_as_batch=True` e `compare_type=True`**: batch mode é o que permite
   alterar colunas no SQLite (que não tem `ALTER COLUMN`), e `compare_type` faz o
   `autogenerate` perceber mudanças de tipo — sem ele, a conversão
   Float → Numeric nunca seria detectada. É o que mantém as migrações portáveis
   entre SQLite e PostgreSQL.
"""
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importar Base dá o metadata para o autogenerate. `resolve_db_url()` garante que
# a migração e o aplicativo resolvam o banco exatamente da mesma forma — e é uma
# FUNÇÃO de propósito: importar a constante DB_URL congelaria o valor do primeiro
# import do módulo, o que mandaria a migração para o banco errado quando o ambiente
# muda depois (caso dos testes, que apontam GF_DB_URL por teste).
# O import não abre conexão: a engine é criada sob demanda em get_engine().
from backend import Base, resolve_db_url

DB_URL = resolve_db_url()

config = context.config

# O `%` precisa ser escapado: set_main_option passa por interpolação do
# configparser, e senhas de banco costumam ter caracteres escapados com %.
config.set_main_option("sqlalchemy.url", DB_URL.replace("%", "%%"))

if config.config_file_name is not None:
    # disable_existing_loggers=False: o padrão True desligaria o logger do
    # aplicativo ao rodar migração dentro de um processo já iniciado (testes).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        render_as_batch=True,   # SQLite: recria a tabela para alterar coluna
        compare_type=True,      # autogenerate percebe Float -> Numeric
        **kwargs,
    )


def run_migrations_offline() -> None:
    """Modo offline: emite o SQL sem conectar (`alembic upgrade head --sql`)."""
    _configure(
        url=DB_URL,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Modo online: conecta e aplica."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _configure(connection=connection)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
