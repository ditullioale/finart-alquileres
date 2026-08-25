"""Notas de seguimiento por contrato

Revision ID: a9b0c1d2e3f4
Revises: 585dc995a5be
Create Date: 2026-08-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a9b0c1d2e3f4"
down_revision = "585dc995a5be"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "seguimiento_notas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inmobiliaria_id", sa.Integer(), nullable=False),
        sa.Column("contrato_id", sa.Integer(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("autor", sa.String(length=80), nullable=True),
        sa.Column("creado", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["inmobiliaria_id"], ["inmobiliarias.id"]),
        sa.ForeignKeyConstraint(["contrato_id"], ["contratos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_seguimiento_notas_inmobiliaria_id",
                    "seguimiento_notas", ["inmobiliaria_id"])
    op.create_index("ix_seguimiento_notas_contrato_id",
                    "seguimiento_notas", ["contrato_id"])


def downgrade():
    op.drop_index("ix_seguimiento_notas_contrato_id", table_name="seguimiento_notas")
    op.drop_index("ix_seguimiento_notas_inmobiliaria_id", table_name="seguimiento_notas")
    op.drop_table("seguimiento_notas")
