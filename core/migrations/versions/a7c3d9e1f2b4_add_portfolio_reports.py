"""add portfolio_reports

Revision ID: a7c3d9e1f2b4
Revises: f1a2b3c4d5e6
Create Date: 2026-09-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a7c3d9e1f2b4'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Plain sa.Enum inline on the column, same convention as health_band
    # in the initial migration — Alembic emits the CREATE TYPE itself as
    # part of create_table, so it must not be pre-created separately.
    op.create_table(
        'portfolio_reports',
        sa.Column('report_type', sa.Enum(
            'at_risk_critical_review', 'watch_review', 'monthly_ceo_snapshot', 'calibration_input', 'voc_ranked_list',
            name='report_type',
        ), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('data', postgresql.JSONB(), nullable=False),
        sa.Column('narrative', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_portfolio_reports')),
    )
    op.create_index(op.f('ix_portfolio_reports_report_type'), 'portfolio_reports', ['report_type'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_portfolio_reports_report_type'), table_name='portfolio_reports')
    op.drop_table('portfolio_reports')
    sa.Enum(name='report_type').drop(op.get_bind())
