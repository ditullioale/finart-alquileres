"""gas_credenciales: varias cuentas de Litoral Gas por inmobiliaria

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'gas_credenciales',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('inmobiliaria_id', sa.Integer(), nullable=False),
        sa.Column('alias', sa.String(length=80), nullable=True),
        sa.Column('usuario', sa.String(length=160), nullable=False),
        sa.Column('clave_enc', sa.Text(), nullable=False),
        sa.Column('creada', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('gas_credenciales', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gas_credenciales_inmobiliaria_id'),
                              ['inmobiliaria_id'], unique=False)


def downgrade():
    op.drop_table('gas_credenciales')
