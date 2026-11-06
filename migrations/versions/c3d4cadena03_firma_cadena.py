"""Cadena de hashes entre firmas (ledger anti-borrado): hash_prev + hash_cadena

Revision ID: c3d4cadena03
Revises: b2c3pdffirma02
Create Date: 2026-11-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c3d4cadena03"
down_revision = "b2c3pdffirma02"
branch_labels = None
depends_on = None


def _tiene_columna(tabla, columna):
    insp = sa.inspect(op.get_bind())
    return columna in [c["name"] for c in insp.get_columns(tabla)]


def upgrade():
    if not _tiene_columna("liquidaciones_firmas", "hash_prev"):
        op.add_column("liquidaciones_firmas",
                      sa.Column("hash_prev", sa.String(length=64), nullable=True))
    if not _tiene_columna("liquidaciones_firmas", "hash_cadena"):
        op.add_column("liquidaciones_firmas",
                      sa.Column("hash_cadena", sa.String(length=64), nullable=True))


def downgrade():
    op.drop_column("liquidaciones_firmas", "hash_cadena")
    op.drop_column("liquidaciones_firmas", "hash_prev")
