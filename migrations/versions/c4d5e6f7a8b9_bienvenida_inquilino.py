"""personas.bienvenida_enviada_at (mail de bienvenida al portal)

Revision ID: c4d5e6f7a8b9
Revises: d2e3f4a5b6c7
Create Date: 2026-08-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'c4d5e6f7a8b9'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('personas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bienvenida_enviada_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('personas', schema=None) as batch_op:
        batch_op.drop_column('bienvenida_enviada_at')
