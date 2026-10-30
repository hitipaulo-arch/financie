"""Initial schema with indexes and soft delete

Revision ID: 46d24e28829d
Revises:
Create Date: 2025-11-25 08:24:51.111961

ESTA REVISÃO NASCEU VAZIA. O `upgrade()` original era só `pass`, o que a tornava
inofensiva num banco que já existia — mas inútil num banco novo: ela marcava o
Alembic como "esquema inicial aplicado" sem criar tabela alguma, e a revisão
seguinte morria com `no such table: main.transactions`.

O esquema era criado de verdade pelo `Base.metadata.create_all()` no boot do app,
ou seja: as migrações não descreviam o banco, só fingiam descrever.

Agora ela cria as quatro tabelas. Cada criação é protegida por `has_table()` para
que um banco existente (criado pelo `create_all` de um deploy anterior, ou já
carregado de dados) atravesse a revisão sem erro — o `alembic upgrade head` do
`startup.txt` roda em todo boot.

Os tipos monetários espelham o modelo: NUMERIC(14,2) para dinheiro e
NUMERIC(20,8) para quantidade/cotação, nos dois dialetos. Se aqui divergir do
modelo, o `alembic revision --autogenerate` passa a gerar diff fantasma.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '46d24e28829d'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def dinheiro():
    """NUMERIC(14,2) — exato, como money_type() no modelo."""
    return sa.Numeric(14, 2)


def quantidade():
    """NUMERIC(20,8) — fração de ativo, como quantity_type() no modelo."""
    return sa.Numeric(20, 8)


def _inspetor():
    """Inspector do banco, ou None em modo offline (`alembic upgrade head --sql`).

    Offline o Alembic entrega um MockConnection, que não tem sistema de inspeção:
    `sa.inspect()` lança NoInspectionAvailable. Tratar None como "banco vazio" é o
    comportamento certo para o modo --sql, cujo papel é gerar o DDL de uma
    instalação nova para um DBA revisar.
    """
    try:
        return sa.inspect(op.get_bind())
    except sa.exc.NoInspectionAvailable:
        return None


def _existe(tabela: str) -> bool:
    inspetor = _inspetor()
    return False if inspetor is None else inspetor.has_table(tabela)


def _garantir_indice(tabela: str, nome: str, colunas: list) -> None:
    """Cria o índice só se ele não existir.

    A guarda de índice é SEPARADA da guarda de tabela de propósito. Um banco que
    já existia (criado pelo `create_all()` de um deploy anterior) passa reto pelo
    `has_table`, mas pode não ter este índice — se a criação ficasse dentro do
    bloco da tabela, ele nunca seria criado num banco existente.
    """
    inspetor = _inspetor()
    if inspetor is None:          # modo offline: emite o CREATE INDEX no script
        op.create_index(nome, tabela, colunas, unique=False)
        return
    if not inspetor.has_table(tabela):
        return
    existentes = {ix["name"] for ix in inspetor.get_indexes(tabela)}
    if nome not in existentes:
        op.create_index(nome, tabela, colunas, unique=False)


def upgrade() -> None:
    if not _existe("transactions"):
        op.create_table(
            "transactions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=False),
            sa.Column("amount", dinheiro(), nullable=False),
            sa.Column("type", sa.String(length=16), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )
    _garantir_indice("transactions", "ix_transactions_user_id", ["user_id"])

    if not _existe("installments"):
        op.create_table(
            "installments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=False),
            sa.Column("monthly_value", dinheiro(), nullable=False),
            sa.Column("total_months", sa.Integer(), nullable=False),
            sa.Column("date_added", sa.Date(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )
    _garantir_indice("installments", "ix_installments_user_id", ["user_id"])

    if not _existe("consents"):
        op.create_table(
            "consents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("consent_id", sa.String(length=128), nullable=False, unique=True),
            sa.Column("provider", sa.String(length=64), nullable=False),
            sa.Column("scopes", sa.String(length=512), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )
    _garantir_indice("consents", "ix_consents_user_id", ["user_id"])

    if not _existe("investments"):
        op.create_table(
            "investments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=256), nullable=False),
            sa.Column("asset_type", sa.String(length=64), nullable=False),
            sa.Column("amount", quantidade(), nullable=False),
            sa.Column("purchase_price", quantidade(), nullable=False),
            sa.Column("current_price", quantidade(), nullable=True),
            sa.Column("purchase_date", sa.Date(), nullable=False),
            sa.Column("target_return", sa.Float(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("notes", sa.String(length=1024), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )
    _garantir_indice("investments", "ix_investments_user_id", ["user_id"])


def downgrade() -> None:
    # Ordem inversa da criação. Também protegido: derrubar o banco de alguém não
    # é efeito colateral aceitável de um downgrade parcial.
    for tabela in ("investments", "consents", "installments", "transactions"):
        if _existe(tabela):
            op.drop_table(tabela)
