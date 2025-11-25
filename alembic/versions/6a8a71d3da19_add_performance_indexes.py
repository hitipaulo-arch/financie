"""Add performance indexes

Revision ID: 6a8a71d3da19
Revises: 46d24e28829d
Create Date: 2025-11-25 08:26:02.450329

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6a8a71d3da19'
down_revision: Union[str, Sequence[str], None] = '46d24e28829d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Add performance indexes to optimize queries."""
    # Transaction indexes - create only if they don't exist
    with op.get_context().autocommit_block():
        connection = op.get_bind()
        
        # Helper to check if index exists
        def index_exists(index_name):
            result = connection.execute(sa.text(
                f"SELECT name FROM sqlite_master WHERE type='index' AND name='{index_name}'"
            ))
            return result.fetchone() is not None
        
        # Transaction indexes
        if not index_exists('idx_transaction_date'):
            op.create_index('idx_transaction_date', 'transactions', ['date'], unique=False)
        if not index_exists('idx_transaction_type'):
            op.create_index('idx_transaction_type', 'transactions', ['type'], unique=False)
        if not index_exists('idx_transaction_deleted_at'):
            op.create_index('idx_transaction_deleted_at', 'transactions', ['deleted_at'], unique=False)
        if not index_exists('idx_transaction_user_date'):
            op.create_index('idx_transaction_user_date', 'transactions', ['user_id', 'date'], unique=False)
        
        # Installment indexes
        if not index_exists('idx_installment_date_added'):
            op.create_index('idx_installment_date_added', 'installments', ['date_added'], unique=False)
        if not index_exists('idx_installment_deleted_at'):
            op.create_index('idx_installment_deleted_at', 'installments', ['deleted_at'], unique=False)
        if not index_exists('idx_installment_user_date'):
            op.create_index('idx_installment_user_date', 'installments', ['user_id', 'date_added'], unique=False)
        
        # Consent indexes
        if not index_exists('idx_consent_status'):
            op.create_index('idx_consent_status', 'consents', ['status'], unique=False)
        if not index_exists('idx_consent_deleted_at'):
            op.create_index('idx_consent_deleted_at', 'consents', ['deleted_at'], unique=False)
        if not index_exists('idx_consent_user_status'):
            op.create_index('idx_consent_user_status', 'consents', ['user_id', 'status'], unique=False)


def downgrade() -> None:
    """Downgrade schema: Remove performance indexes."""
    # Remove consent indexes
    op.drop_index('idx_consent_user_status', table_name='consents')
    op.drop_index('idx_consent_deleted_at', table_name='consents')
    op.drop_index('idx_consent_status', table_name='consents')
    
    # Remove installment indexes
    op.drop_index('idx_installment_user_date', table_name='installments')
    op.drop_index('idx_installment_deleted_at', table_name='installments')
    op.drop_index('idx_installment_date_added', table_name='installments')
    
    # Remove transaction indexes
    op.drop_index('idx_transaction_user_date', table_name='transactions')
    op.drop_index('idx_transaction_deleted_at', table_name='transactions')
    op.drop_index('idx_transaction_type', table_name='transactions')
    op.drop_index('idx_transaction_date', table_name='transactions')
