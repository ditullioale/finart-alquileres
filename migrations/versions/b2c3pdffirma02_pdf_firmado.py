"""PDF congelado de la liquidación firmada (columnas pdf_firmado + pdf_sha256)

Se agregan en una migración APARTE porque la tabla liquidaciones_firmas ya se
había creado y aplicado en producción sin estas columnas; editar aquella migración
no las vuelve a aplicar.

Revision ID: b2c3pdffirma02
Revises: a1b2f1rmas01
Create Date: 2026-11-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b2c3pdffirma02"
down_revision = "a1b2f1rmas01"
branch_labels = None
depends_on = None


def _tiene_columna(tabla, columna):
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return columna in [c["name"] for c in insp.get_columns(tabla)]


def upgrade():
    # Idempotente: si por algún camino la columna ya existe, no falla.
    if not _tiene_columna("liquidaciones_firmas", "pdf_firmado"):
        op.add_column("liquidaciones_firmas",
                      sa.Column("pdf_firmado", sa.LargeBinary(), nullable=True))
    if not _tiene_columna("liquidaciones_firmas", "pdf_sha256"):
        op.add_column("liquidaciones_firmas",
                      sa.Column("pdf_sha256", sa.String(length=64), nullable=True))


def downgrade():
    op.drop_column("liquidaciones_firmas", "pdf_sha256")
    op.drop_column("liquidaciones_firmas", "pdf_firmado")
