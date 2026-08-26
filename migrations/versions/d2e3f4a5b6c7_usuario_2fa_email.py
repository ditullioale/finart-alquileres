"""Usuario.dosfa_email: segundo factor por email (opt-in)

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-08-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "usuarios",
        sa.Column("dosfa_email", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )


def downgrade():
    op.drop_column("usuarios", "dosfa_email")
