"""Acuse por POST: user-agent de la confirmación + contador de intentos

Revision ID: g7b8acuse07
Revises: f6a7acuse06
Create Date: 2026-11-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "g7b8acuse07"
down_revision = "f6a7acuse06"
branch_labels = None
depends_on = None


def _tiene_columna(tabla, columna):
    insp = sa.inspect(op.get_bind())
    return columna in [c["name"] for c in insp.get_columns(tabla)]


def upgrade():
    if not _tiene_columna("liquidaciones_firmas", "email_confirmado_ua"):
        op.add_column("liquidaciones_firmas",
                      sa.Column("email_confirmado_ua", sa.String(length=300), nullable=True))
    if not _tiene_columna("liquidaciones_firmas", "acuse_intentos"):
        op.add_column("liquidaciones_firmas",
                      sa.Column("acuse_intentos", sa.Integer(), nullable=True,
                                server_default="0"))


def downgrade():
    op.drop_column("liquidaciones_firmas", "acuse_intentos")
    op.drop_column("liquidaciones_firmas", "email_confirmado_ua")
