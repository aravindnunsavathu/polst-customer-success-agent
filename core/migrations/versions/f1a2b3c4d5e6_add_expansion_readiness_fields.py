"""add expansion readiness fields to account_plans

Revision ID: f1a2b3c4d5e6
Revises: dad9568f048c
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'dad9568f048c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('account_plans', sa.Column('expansion_target_department', sa.String(), nullable=True))
    op.add_column('account_plans', sa.Column('expansion_target_owner', sa.String(), nullable=True))
    # server_default required so existing rows backfill instead of
    # violating NOT NULL — same reasoning as reference_willing's migration.
    op.add_column(
        'account_plans',
        sa.Column('expansion_champion_introduction', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.add_column('account_plans', sa.Column('expansion_new_budget_holder', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('account_plans', 'expansion_new_budget_holder')
    op.drop_column('account_plans', 'expansion_champion_introduction')
    op.drop_column('account_plans', 'expansion_target_owner')
    op.drop_column('account_plans', 'expansion_target_department')
