"""ajustes: token del emisor del facturador (ARCA multiempresa)

Revision ID: a1b2c3fac701
Revises: c9d0e1f2a3b4
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3fac701'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ajustes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('facturador_token_enc', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('facturador_modo', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('facturador_pv', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('ajustes', schema=None) as batch_op:
        batch_op.drop_column('facturador_pv')
        batch_op.drop_column('facturador_modo')
        batch_op.drop_column('facturador_token_enc')
