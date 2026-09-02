"""Conceptos fijos por contrato (ej.: seguro) que se cobran en cada recibo

Revision ID: f1a2b3c4d5e6
Revises: a9b1c2d3e4f5
Create Date: 2026-09-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = "a9b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "contrato_conceptos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inmobiliaria_id", sa.Integer(), nullable=False),
        sa.Column("contrato_id", sa.Integer(), nullable=False),
        sa.Column("descripcion", sa.String(length=120), nullable=False),
        sa.Column("monto", sa.Numeric(14, 2), nullable=False),
        sa.Column("trasladar_liquidacion", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("activo", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["inmobiliaria_id"], ["inmobiliarias.id"]),
        sa.ForeignKeyConstraint(["contrato_id"], ["contratos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contrato_conceptos_inmobiliaria_id",
                    "contrato_conceptos", ["inmobiliaria_id"])
    op.create_index("ix_contrato_conceptos_contrato_id",
                    "contrato_conceptos", ["contrato_id"])


def downgrade():
    op.drop_index("ix_contrato_conceptos_contrato_id", table_name="contrato_conceptos")
    op.drop_index("ix_contrato_conceptos_inmobiliaria_id", table_name="contrato_conceptos")
    op.drop_table("contrato_conceptos")
