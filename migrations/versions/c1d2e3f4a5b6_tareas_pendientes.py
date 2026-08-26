"""Tareas pendientes (recordatorios de acciones de la inmobiliaria)

Revision ID: c1d2e3f4a5b6
Revises: a9b0c1d2e3f4
Create Date: 2026-08-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c1d2e3f4a5b6"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tareas_pendientes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inmobiliaria_id", sa.Integer(), nullable=False),
        sa.Column("texto", sa.String(length=300), nullable=False),
        sa.Column("autor", sa.String(length=80), nullable=True),
        sa.Column("creado", sa.DateTime(), nullable=True),
        sa.Column("completada", sa.Boolean(), server_default=sa.text("false"),
                  nullable=False),
        sa.Column("completada_en", sa.DateTime(), nullable=True),
        sa.Column("completada_por", sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(["inmobiliaria_id"], ["inmobiliarias.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tareas_pendientes_inmobiliaria_id",
                    "tareas_pendientes", ["inmobiliaria_id"])


def downgrade():
    op.drop_index("ix_tareas_pendientes_inmobiliaria_id",
                  table_name="tareas_pendientes")
    op.drop_table("tareas_pendientes")
