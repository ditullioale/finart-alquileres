"""notificaciones + notificacion_destinatarios (avisos al portal)

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c1
Create Date: 2026-08-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'e7f8a9b0c1d2'
down_revision = 'd5e6f7a8b9c1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'notificaciones',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('inmobiliaria_id', sa.Integer(), nullable=False),
        sa.Column('tipo', sa.String(length=20), nullable=False),
        sa.Column('mensaje', sa.Text(), nullable=False),
        sa.Column('creada_por', sa.String(length=80), nullable=True),
        sa.Column('creada_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['inmobiliaria_id'], ['inmobiliarias.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('notificaciones', schema=None) as batch_op:
        batch_op.create_index('ix_notificaciones_inmobiliaria_id', ['inmobiliaria_id'], unique=False)

    op.create_table(
        'notificacion_destinatarios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('notificacion_id', sa.Integer(), nullable=False),
        sa.Column('persona_id', sa.Integer(), nullable=False),
        sa.Column('mail_enviado_at', sa.DateTime(), nullable=True),
        sa.Column('vista_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['notificacion_id'], ['notificaciones.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['persona_id'], ['personas.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('notificacion_destinatarios', schema=None) as batch_op:
        batch_op.create_index('ix_notificacion_destinatarios_notificacion_id', ['notificacion_id'], unique=False)
        batch_op.create_index('ix_notificacion_destinatarios_persona_id', ['persona_id'], unique=False)


def downgrade():
    op.drop_table('notificacion_destinatarios')
    op.drop_table('notificaciones')
