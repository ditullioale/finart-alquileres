"""contrato.aumento_base: fecha base para contar el próximo aumento

Revision ID: c2d3e4f5a6b7
Revises: a1b2c3fac701
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = 'c2d3e4f5a6b7'
down_revision = 'a1b2c3fac701'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('contratos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('aumento_base', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('contratos', schema=None) as batch_op:
        batch_op.drop_column('aumento_base')
