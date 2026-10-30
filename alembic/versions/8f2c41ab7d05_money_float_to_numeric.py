"""Converte colunas monetárias de FLOAT para NUMERIC

Revision ID: 8f2c41ab7d05
Revises: 6a8a71d3da19
Create Date: 2026-10-30 11:40:00.000000

Fase 3: dinheiro deix de ser FLOAT.

Por que isto importa num app de finanças: FLOAT é binário, então 0.1 não tem
representação exata. Somar centavos acumula erro — `0.1 + 0.2 == 0.30000000000000004`.
O resumo do usuário é exatamente isso: uma soma longa de valores monetários. Com
NUMERIC(14,2) o valor é exato no banco e a soma é exata.

Duas decisões de projeto:

1. **Dinheiro e quantidade são tipos diferentes.** `transactions.amount` e
   `installments.monthly_value` viram NUMERIC(14,2) — centavos. Mas
   `investments.amount`/`purchase_price`/`current_price` viram NUMERIC(20,8):
   uma posição pode ser 0.00012345 BTC e um token pode custar 0.0000012.
   Aplicar 2 casas ali **zeraria a posição do usuário**.

2. **A revisão é idempotente e portátil.** Um banco criado do zero já recebe
   NUMERIC na revisão inicial, então aqui não há nada a fazer — por isso a
   checagem de tipo antes de alterar. E como o SQLite não tem `ALTER COLUMN`,
   usamos `batch_alter_table`, que o recria preservando dados e índices
   (`render_as_batch=True` já está no env.py).

O cast no PostgreSQL é explícito (`USING round(col::numeric, N)`) porque o
 PostgreSQL não converte float -> numeric implicitamente em ALTER TYPE.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f2c41ab7d05'
down_revision: Union[str, Sequence[str], None] = '6a8a71d3da19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (tabela, coluna, precisão, escala, nullable)
COLUNAS = [
    ("transactions", "amount", 14, 2, False),
    ("installments", "monthly_value", 14, 2, False),
    ("investments", "amount", 20, 8, False),
    ("investments", "purchase_price", 20, 8, False),
    ("investments", "current_price", 20, 8, True),
]


def _tipo_atual(tabela: str, coluna: str):
    """Devolve o tipo refletido da coluna, ou None se não der para inspecionar.

    None cobre três casos e os três levam a "não converter": coluna ausente,
    tabela ausente e modo offline (`--sql`, MockConnection sem inspeção). No
    offline isso é o correto — a revisão inicial do script já cria as colunas
    como NUMERIC, então emitir um ALTER redundante aqui só sujaria o dump.
    """
    try:
        inspetor = sa.inspect(op.get_bind())
    except sa.exc.NoInspectionAvailable:
        return None
    if not inspetor.has_table(tabela):
        return None
    for col in inspetor.get_columns(tabela):
        if col["name"] == coluna:
            return col["type"]
    return None


def _ja_e_numeric(tipo) -> bool:
    """True se a coluna já é NUMERIC/DECIMAL (e não FLOAT/REAL).

    `sa.Float` herda de `sa.Numeric` no SQLAlchemy, então `isinstance(t, Numeric)`
    seria True para FLOAT também — a comparação tem que ser pelo nome do tipo ou
    excluindo Float explicitamente.
    """
    if tipo is None:
        return True  # coluna/tabela ausente: nada a converter
    if isinstance(tipo, sa.Float):
        return False
    return isinstance(tipo, (sa.Numeric, sa.DECIMAL))


def upgrade() -> None:
    bind = op.get_bind()
    dialeto = bind.dialect.name

    for tabela, coluna, precisao, escala, nullable in COLUNAS:
        atual = _tipo_atual(tabela, coluna)
        if _ja_e_numeric(atual):
            continue

        novo_tipo = sa.Numeric(precisao, escala)

        # batch_alter_table com recreate="auto" (o padrão): no SQLite, que não tem
        # ALTER COLUMN TYPE, o Alembic recria a tabela preservando dados e índices;
        # no PostgreSQL emite um ALTER TYPE direto, sem copiar a tabela inteira.
        with op.batch_alter_table(tabela, recreate="auto") as batch:
            batch.alter_column(
                coluna,
                existing_type=atual if atual is not None else sa.Float(),
                type_=novo_tipo,
                existing_nullable=nullable,
                nullable=nullable,
                # PostgreSQL exige cast explícito de float para numeric.
                postgresql_using=f"round({coluna}::numeric, {escala})",
            )


def downgrade() -> None:
    """Volta para FLOAT.

    Perde exatidão decimal — é o motivo de esta migração existir. Em produção,
    prefira restaurar de backup a descer este degrau.
    """
    for tabela, coluna, _precisao, _escala, nullable in COLUNAS:
        atual = _tipo_atual(tabela, coluna)
        if atual is None or isinstance(atual, sa.Float):
            continue
        if not isinstance(atual, (sa.Numeric, sa.DECIMAL)):
            continue

        with op.batch_alter_table(tabela, recreate="auto") as batch:
            batch.alter_column(
                coluna,
                existing_type=atual,
                type_=sa.Float(),
                existing_nullable=nullable,
                nullable=nullable,
                postgresql_using=f"{coluna}::double precision",
            )
