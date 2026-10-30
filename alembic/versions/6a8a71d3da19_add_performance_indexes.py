"""Add performance indexes

Revision ID: 6a8a71d3da19
Revises: 46d24e28829d
Create Date: 2025-11-25 08:26:02.450329

Versão portátil desta revisão. A original consultava `sqlite_master` para
descobrir se o índice já existia:

    SELECT name FROM sqlite_master WHERE type='index' AND name='...'

Isso é específico do SQLite — num PostgreSQL a tabela de catálogo é
`pg_indexes`, então a consulta estourava e o `alembic upgrade head` do boot
derrubava o deploy. Como o banco de produção ainda não está decidido, a migração
precisa valer nos dois.

A checagem agora usa `sa.inspect(bind).get_indexes(tabela)`, que o SQLAlchemy
traduz para o catálogo de cada dialeto.

Cada `create_index` continua protegido por existência: um banco criado antes por
`Base.metadata.create_all()` já tem esses índices (eles vêm do `__table_args__`
do modelo), e recriá-los daria erro de nome duplicado.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6a8a71d3da19'
down_revision: Union[str, Sequence[str], None] = '46d24e28829d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (tabela, nome do índice, colunas)
INDICES = [
    ("transactions", "idx_transaction_date", ["date"]),
    ("transactions", "idx_transaction_type", ["type"]),
    ("transactions", "idx_transaction_deleted_at", ["deleted_at"]),
    ("transactions", "idx_transaction_user_date", ["user_id", "date"]),
    ("installments", "idx_installment_date_added", ["date_added"]),
    ("installments", "idx_installment_deleted_at", ["deleted_at"]),
    ("installments", "idx_installment_user_date", ["user_id", "date_added"]),
    ("consents", "idx_consent_status", ["status"]),
    ("consents", "idx_consent_deleted_at", ["deleted_at"]),
    ("consents", "idx_consent_user_status", ["user_id", "status"]),
    ("investments", "idx_investment_user_date", ["user_id", "purchase_date"]),
    ("investments", "idx_investment_type", ["asset_type"]),
    ("investments", "idx_investment_deleted_at", ["deleted_at"]),
]


def _indices_existentes(tabela: str) -> set:
    """Nomes dos índices já presentes. Conjunto vazio em modo offline.

    Offline (`--sql`) o Alembic usa um MockConnection, sem inspeção possível:
    devolver vazio faz o script emitir todos os CREATE INDEX, que é o esperado de
    um dump base -> head.
    """
    try:
        inspetor = sa.inspect(op.get_bind())
    except sa.exc.NoInspectionAvailable:
        return set()
    if not inspetor.has_table(tabela):
        return set()
    return {ix["name"] for ix in inspetor.get_indexes(tabela)}


def upgrade() -> None:
    """Cria os índices que ainda não existem.

    Num banco grande em PostgreSQL vale considerar `postgresql_concurrently=True`
    dentro de `autocommit_block()` para não travar escrita durante a criação.
    """
    por_tabela = {}
    for tabela, nome, colunas in INDICES:
        existentes = por_tabela.get(tabela)
        if existentes is None:
            existentes = por_tabela[tabela] = _indices_existentes(tabela)
        if nome in existentes:
            continue
        op.create_index(nome, tabela, colunas, unique=False)
        existentes.add(nome)


def downgrade() -> None:
    """Remove os índices, na ordem inversa e só os que existem."""
    por_tabela = {}
    for tabela, nome, _colunas in reversed(INDICES):
        existentes = por_tabela.get(tabela)
        if existentes is None:
            existentes = por_tabela[tabela] = _indices_existentes(tabela)
        if nome not in existentes:
            continue
        op.drop_index(nome, table_name=tabela)
        existentes.discard(nome)
