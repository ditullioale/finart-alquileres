"""Anulación de liquidaciones firmadas (no borrado): anulada + metadatos

Revision ID: d4e5anula04
Revises: c3d4cadena03
Create Date: 2026-11-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d4e5anula04"
down_revision = "c3d4cadena03"
branch_labels = None
depends_on = None


def _tiene_columna(tabla, columna):
    insp = sa.inspect(op.get_bind())
    return columna in [c["name"] for c in insp.get_columns(tabla)]


def upgrade():
    if not _tiene_columna("liquidaciones", "anulada"):
        op.add_column("liquidaciones",
                      sa.Column("anulada", sa.Boolean(), nullable=False,
                                server_default=sa.text("false")))
    if not _tiene_columna("liquidaciones", "anulada_en"):
        op.add_column("liquidaciones", sa.Column("anulada_en", sa.DateTime(), nullable=True))
    if not _tiene_columna("liquidaciones", "anulada_por"):
        op.add_column("liquidaciones", sa.Column("anulada_por", sa.String(length=120), nullable=True))
    if not _tiene_columna("liquidaciones", "anulacion_motivo"):
        op.add_column("liquidaciones", sa.Column("anulacion_motivo", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("liquidaciones", "anulacion_motivo")
    op.drop_column("liquidaciones", "anulada_por")
    op.drop_column("liquidaciones", "anulada_en")
    op.drop_column("liquidaciones", "anulada")
