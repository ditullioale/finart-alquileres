"""liquidación: datos del comprobante de honorarios emitido

Guarda dentro de la liquidación el CAE, número, tipo, fecha, vencimiento, id (para
el PDF) y estado de la factura de honorarios, para poder verla después sin salir del
gestor y para la bandeja de "liquidaciones sin facturar / con error".

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = 'e6f7a8b9c0d1'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None

_COLS = [
    ('factura_estado', sa.String(24)),
    ('factura_id', sa.Integer()),
    ('factura_numero', sa.String(30)),
    ('factura_tipo', sa.String(10)),
    ('factura_cae', sa.String(20)),
    ('factura_cae_vto', sa.Date()),
    ('factura_fecha', sa.Date()),
    ('factura_detalle', sa.Text()),
]


def upgrade():
    with op.batch_alter_table('liquidaciones', schema=None) as batch_op:
        for nombre, tipo in _COLS:
            batch_op.add_column(sa.Column(nombre, tipo, nullable=True))


def downgrade():
    with op.batch_alter_table('liquidaciones', schema=None) as batch_op:
        for nombre, _ in reversed(_COLS):
            batch_op.drop_column(nombre)
