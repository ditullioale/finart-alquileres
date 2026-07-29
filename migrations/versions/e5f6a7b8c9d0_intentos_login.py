"""intentos_login (límite de login compartido entre workers)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'intentos_login',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clave', sa.String(length=160), nullable=False),
        sa.Column('fallos', sa.Integer(), nullable=False),
        sa.Column('ultimo', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('clave'),
    )
    with op.batch_alter_table('intentos_login') as batch:
        batch.create_index('ix_intentos_login_clave', ['clave'])


def downgrade():
    with op.batch_alter_table('intentos_login') as batch:
        batch.drop_index('ix_intentos_login_clave')
    op.drop_table('intentos_login')
