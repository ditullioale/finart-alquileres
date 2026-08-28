"""personas.portal_password_hash (contraseña propia del portal)

Revision ID: d5e6f7a8b9c1
Revises: c4d5e6f7a8b9
Create Date: 2026-08-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'd5e6f7a8b9c1'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('personas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('portal_password_hash', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('personas', schema=None) as batch_op:
        batch_op.drop_column('portal_password_hash')
