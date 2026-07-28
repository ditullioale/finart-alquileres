"""inmobiliaria_id NOT NULL en las entidades comerciales

Cierra el hueco de registros "sin dueño": primero asegura que exista una
inmobiliaria, asigna a ella cualquier registro con inmobiliaria_id NULL y recién
después pone la columna como obligatoria (NOT NULL). El usuario NO se toca (puede
ser superadmin de plataforma, sin inmobiliaria).

Revision ID: a1b2c3d4e5f6
Revises: 05e854d42a59
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '05e854d42a59'
branch_labels = None
depends_on = None

# Entidades comerciales (sin 'usuarios', que puede quedar sin inmobiliaria).
TABLAS = ['personas', 'inmuebles', 'contratos', 'aumentos', 'pagos',
          'gas_estado', 'recibos_manuales', 'liquidaciones']


def upgrade():
    conn = op.get_bind()
    # 1) Asegurar que exista al menos una inmobiliaria.
    fila = conn.execute(sa.text(
        "SELECT id FROM inmobiliarias ORDER BY id LIMIT 1")).first()
    if fila is None:
        conn.execute(sa.text(
            "INSERT INTO inmobiliarias (nombre, slug) VALUES "
            "('Mi Inmobiliaria', 'principal')"))
        fila = conn.execute(sa.text(
            "SELECT id FROM inmobiliarias ORDER BY id LIMIT 1")).first()
    tid = fila[0]
    # 2) Backfill: asignar los NULL a esa inmobiliaria.
    for t in TABLAS:
        conn.execute(sa.text(
            f"UPDATE {t} SET inmobiliaria_id = :tid WHERE inmobiliaria_id IS NULL"),
            {"tid": tid})
    # 3) Volver la columna obligatoria.
    for t in TABLAS:
        with op.batch_alter_table(t, schema=None) as batch_op:
            batch_op.alter_column('inmobiliaria_id',
                                  existing_type=sa.Integer(), nullable=False)


def downgrade():
    for t in TABLAS:
        with op.batch_alter_table(t, schema=None) as batch_op:
            batch_op.alter_column('inmobiliaria_id',
                                  existing_type=sa.Integer(), nullable=True)
