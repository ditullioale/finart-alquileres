"""Acuse de recepción del mail firmado: píxel de apertura + botón de confirmación

Revision ID: f6a7acuse06
Revises: e5f6email05
Create Date: 2026-11-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f6a7acuse06"
down_revision = "e5f6email05"
branch_labels = None
depends_on = None


_COLS = [
    ("acuse_token", sa.String(length=64)),
    ("email_enviado_at", sa.DateTime()),
    ("email_abierto_at", sa.DateTime()),
    ("email_abierto_ip", sa.String(length=64)),
    ("email_confirmado_at", sa.DateTime()),
    ("email_confirmado_ip", sa.String(length=64)),
]


def _tiene_columna(tabla, columna):
    insp = sa.inspect(op.get_bind())
    return columna in [c["name"] for c in insp.get_columns(tabla)]


def upgrade():
    for nombre, tipo in _COLS:
        if not _tiene_columna("liquidaciones_firmas", nombre):
            op.add_column("liquidaciones_firmas", sa.Column(nombre, tipo, nullable=True))
    # Índice para buscar por token (acuse público, sin login).
    insp = sa.inspect(op.get_bind())
    idx = [i["name"] for i in insp.get_indexes("liquidaciones_firmas")]
    if "ix_liquidaciones_firmas_acuse_token" not in idx:
        op.create_index("ix_liquidaciones_firmas_acuse_token",
                        "liquidaciones_firmas", ["acuse_token"])


def downgrade():
    op.drop_index("ix_liquidaciones_firmas_acuse_token",
                  table_name="liquidaciones_firmas")
    for nombre, _tipo in reversed(_COLS):
        op.drop_column("liquidaciones_firmas", nombre)
