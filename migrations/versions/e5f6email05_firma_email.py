"""Email del firmante en la firma de liquidación (opcional)

Revision ID: e5f6email05
Revises: d4e5anula04
Create Date: 2026-11-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e5f6email05"
down_revision = "d4e5anula04"
branch_labels = None
depends_on = None


def _tiene_columna(tabla, columna):
    insp = sa.inspect(op.get_bind())
    return columna in [c["name"] for c in insp.get_columns(tabla)]


def upgrade():
    if not _tiene_columna("liquidaciones_firmas", "firmante_email"):
        op.add_column("liquidaciones_firmas",
                      sa.Column("firmante_email", sa.String(length=160), nullable=True))


def downgrade():
    op.drop_column("liquidaciones_firmas", "firmante_email")
