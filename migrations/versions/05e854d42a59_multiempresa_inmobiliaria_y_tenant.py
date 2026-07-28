"""multiempresa: tabla inmobiliarias + columna inmobiliaria_id (indexada)

Paso 1 del núcleo multiempresa. Agrega el 'tenant' (inmobiliaria) y la columna
inmobiliaria_id en las entidades comerciales, con índice para filtrar rápido.
Las columnas quedan nullable; el backfill (asignar todo a la inmobiliaria #1) y
la asignación automática se hacen desde la app. La constraint de clave foránea a
nivel base se agrega en un paso posterior (con convención de nombres), junto con
el paso a NOT NULL y el filtrado de aislamiento.

Revision ID: 05e854d42a59
Revises: ba72a5e5c3ea
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = '05e854d42a59'
down_revision = 'ba72a5e5c3ea'
branch_labels = None
depends_on = None

# Tablas comerciales que reciben inmobiliaria_id.
TABLAS = ['personas', 'inmuebles', 'contratos', 'aumentos', 'pagos',
          'gas_estado', 'recibos_manuales', 'liquidaciones', 'usuarios']


def upgrade():
    op.create_table(
        'inmobiliarias',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=160), nullable=False),
        sa.Column('slug', sa.String(length=60), nullable=True),
        sa.Column('cuit', sa.String(length=20), nullable=True),
        sa.Column('direccion', sa.String(length=200), nullable=True),
        sa.Column('localidad', sa.String(length=120), nullable=True),
        sa.Column('telefono', sa.String(length=60), nullable=True),
        sa.Column('email', sa.String(length=120), nullable=True),
        sa.Column('logo_path', sa.String(length=300), nullable=True),
        sa.Column('plan', sa.String(length=20), nullable=True),
        sa.Column('activa', sa.Boolean(), nullable=True),
        sa.Column('creada', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )
    for t in TABLAS:
        with op.batch_alter_table(t, schema=None) as batch_op:
            batch_op.add_column(sa.Column('inmobiliaria_id', sa.Integer(), nullable=True))
            batch_op.create_index(batch_op.f(f'ix_{t}_inmobiliaria_id'),
                                  ['inmobiliaria_id'], unique=False)


def downgrade():
    for t in reversed(TABLAS):
        with op.batch_alter_table(t, schema=None) as batch_op:
            batch_op.drop_index(batch_op.f(f'ix_{t}_inmobiliaria_id'))
            batch_op.drop_column('inmobiliaria_id')
    op.drop_table('inmobiliarias')
