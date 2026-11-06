"""Firma manuscrita digital del propietario sobre la liquidación + puente PC->celular

Revision ID: a1b2f1rmas01
Revises: f1a2b3c4d5e6
Create Date: 2026-11-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1b2f1rmas01"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "liquidaciones_firmas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inmobiliaria_id", sa.Integer(), nullable=False),
        sa.Column("liquidacion_id", sa.Integer(), nullable=False),
        sa.Column("firmante", sa.String(length=160), nullable=True),
        sa.Column("firmante_dni", sa.String(length=30), nullable=True),
        sa.Column("conforme", sa.Boolean(), nullable=True),
        sa.Column("consentimiento", sa.Text(), nullable=True),
        sa.Column("firma_png", sa.LargeBinary(), nullable=True),
        sa.Column("trazos", sa.Text(), nullable=True),
        sa.Column("snapshot", sa.Text(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("pdf_firmado", sa.LargeBinary(), nullable=True),
        sa.Column("pdf_sha256", sa.String(length=64), nullable=True),
        sa.Column("firmado", sa.DateTime(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("dispositivo", sa.String(length=300), nullable=True),
        sa.Column("meta", sa.Text(), nullable=True),
        sa.Column("registrado_por", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(["inmobiliaria_id"], ["inmobiliarias.id"]),
        sa.ForeignKeyConstraint(["liquidacion_id"], ["liquidaciones.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("liquidacion_id"),
    )
    op.create_index("ix_liquidaciones_firmas_inmobiliaria_id",
                    "liquidaciones_firmas", ["inmobiliaria_id"])
    op.create_index("ix_liquidaciones_firmas_liquidacion_id",
                    "liquidaciones_firmas", ["liquidacion_id"])

    op.create_table(
        "firma_sesiones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inmobiliaria_id", sa.Integer(), nullable=False),
        sa.Column("pendiente_liq_id", sa.Integer(), nullable=True),
        sa.Column("solicitado", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["inmobiliaria_id"], ["inmobiliarias.id"]),
        sa.ForeignKeyConstraint(["pendiente_liq_id"], ["liquidaciones.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inmobiliaria_id"),
    )
    op.create_index("ix_firma_sesiones_inmobiliaria_id",
                    "firma_sesiones", ["inmobiliaria_id"])


def downgrade():
    op.drop_index("ix_firma_sesiones_inmobiliaria_id", table_name="firma_sesiones")
    op.drop_table("firma_sesiones")
    op.drop_index("ix_liquidaciones_firmas_liquidacion_id", table_name="liquidaciones_firmas")
    op.drop_index("ix_liquidaciones_firmas_inmobiliaria_id", table_name="liquidaciones_firmas")
    op.drop_table("liquidaciones_firmas")
