"""documentos_contrato (adjuntar DNI, recibos, etc. a un contrato)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'documentos_contrato',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('inmobiliaria_id', sa.Integer(), nullable=True),
        sa.Column('contrato_id', sa.Integer(), nullable=False),
        sa.Column('categoria', sa.String(length=40), nullable=True),
        sa.Column('persona', sa.String(length=160), nullable=True),
        sa.Column('nombre_archivo', sa.String(length=255), nullable=True),
        sa.Column('tipo_mime', sa.String(length=100), nullable=True),
        sa.Column('tamano', sa.Integer(), nullable=True),
        sa.Column('datos', sa.LargeBinary(), nullable=True),
        sa.Column('subido_por', sa.String(length=120), nullable=True),
        sa.Column('subido', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('documentos_contrato', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documentos_contrato_inmobiliaria_id'),
                              ['inmobiliaria_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documentos_contrato_contrato_id'),
                              ['contrato_id'], unique=False)


def downgrade():
    op.drop_table('documentos_contrato')
