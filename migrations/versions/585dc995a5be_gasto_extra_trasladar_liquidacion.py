"""gasto_extra_trasladar_liquidacion: opción de no liquidar un gasto extra al propietario

Un "gasto extra" cargado al cobrar (ej.: seguro, agua, expensas) ahora puede
marcarse para NO trasladarse a la liquidación del propietario -- por ejemplo un
seguro que paga la inmobiliaria, no el propietario. Por defecto se traslada
(True), que es el criterio que ya regía de hecho para cosas como agua o
expensas.

Revision ID: 585dc995a5be
Revises: f7a8b9c0d1e2
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = '585dc995a5be'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('gastos_extra',
                  sa.Column('trasladar_liquidacion', sa.Boolean(), nullable=False,
                            server_default=sa.text('true')))


def downgrade():
    op.drop_column('gastos_extra', 'trasladar_liquidacion')
