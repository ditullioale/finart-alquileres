"""solicitudes_alta (auto-registro de inmobiliarias con aprobación del superadmin)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'solicitudes_alta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre_inmobiliaria', sa.String(length=160), nullable=False),
        sa.Column('nombre_contacto', sa.String(length=160), nullable=True),
        sa.Column('email', sa.String(length=120), nullable=True),
        sa.Column('telefono', sa.String(length=60), nullable=True),
        sa.Column('localidad', sa.String(length=120), nullable=True),
        sa.Column('username', sa.String(length=60), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=True),
        sa.Column('creada', sa.DateTime(), nullable=True),
        sa.Column('procesada', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('solicitudes_alta')
