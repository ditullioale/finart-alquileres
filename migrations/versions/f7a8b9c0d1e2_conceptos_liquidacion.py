"""conceptos_liquidacion: líneas extra (+/-) en una liquidación al propietario

Permite agregar conceptos libres (descripción + importe, + suma / − resta) a una
liquidación, para sumar o descontar gastos al propietario antes de pagarle el neto.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa

revision = 'f7a8b9c0d1e2'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'conceptos_liquidacion',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('inmobiliaria_id', sa.Integer(), nullable=False),
        sa.Column('liquidacion_id', sa.Integer(), nullable=False),
        sa.Column('descripcion', sa.String(length=200), nullable=False),
        sa.Column('monto', sa.Numeric(14, 2), nullable=False),
        sa.ForeignKeyConstraint(['inmobiliaria_id'], ['inmobiliarias.id']),
        sa.ForeignKeyConstraint(['liquidacion_id'], ['liquidaciones.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_conceptos_liquidacion_inmobiliaria_id',
                    'conceptos_liquidacion', ['inmobiliaria_id'])
    op.create_index('ix_conceptos_liquidacion_liquidacion_id',
                    'conceptos_liquidacion', ['liquidacion_id'])


def downgrade():
    op.drop_index('ix_conceptos_liquidacion_liquidacion_id', table_name='conceptos_liquidacion')
    op.drop_index('ix_conceptos_liquidacion_inmobiliaria_id', table_name='conceptos_liquidacion')
    op.drop_table('conceptos_liquidacion')
