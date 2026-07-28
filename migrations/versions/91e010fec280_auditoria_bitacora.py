"""auditoria: bitácora de altas, cambios y eliminaciones

Crea solo la tabla `auditoria`. (No se tocan las claves foráneas de
inmobiliaria_id, que se agregarán con convención de nombres en un paso aparte.)

Revision ID: 91e010fec280
Revises: a1b2c3d4e5f6
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = '91e010fec280'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'auditoria',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('inmobiliaria_id', sa.Integer(), nullable=True),
        sa.Column('fecha', sa.DateTime(), nullable=True),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('usuario_nombre', sa.String(length=120), nullable=True),
        sa.Column('accion', sa.String(length=20), nullable=True),
        sa.Column('entidad', sa.String(length=40), nullable=True),
        sa.Column('entidad_id', sa.String(length=20), nullable=True),
        sa.Column('descripcion', sa.String(length=300), nullable=True),
        sa.Column('ip', sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('auditoria', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_auditoria_fecha'), ['fecha'], unique=False)
        batch_op.create_index(batch_op.f('ix_auditoria_inmobiliaria_id'),
                              ['inmobiliaria_id'], unique=False)


def downgrade():
    op.drop_table('auditoria')
