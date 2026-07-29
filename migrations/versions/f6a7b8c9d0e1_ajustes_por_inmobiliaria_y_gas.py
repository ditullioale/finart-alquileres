"""ajustes por inmobiliaria + credenciales de Litoral Gas

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ajustes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('inmobiliaria_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('gas_usuario', sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column('gas_clave_enc', sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f('ix_ajustes_inmobiliaria_id'),
                              ['inmobiliaria_id'], unique=False)


def downgrade():
    with op.batch_alter_table('ajustes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ajustes_inmobiliaria_id'))
        batch_op.drop_column('gas_clave_enc')
        batch_op.drop_column('gas_usuario')
        batch_op.drop_column('inmobiliaria_id')
