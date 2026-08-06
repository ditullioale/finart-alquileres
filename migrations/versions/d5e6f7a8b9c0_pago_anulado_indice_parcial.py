"""pago anulado: índice único parcial (permite recobrar un período anulado)

Convierte la restricción única (contrato, período) en un índice único PARCIAL que
excluye los pagos anulados. Así se puede anular un pago (queda como rastro) y volver
a cobrar ese mismo período, sin poder tener dos pagos activos a la vez.

Revision ID: d5e6f7a8b9c0
Revises: c2d3e4f5a6b7
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = 'd5e6f7a8b9c0'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name
    # 1) Sacar la restricción única total, si está.
    try:
        with op.batch_alter_table('pagos', schema=None) as batch_op:
            batch_op.drop_constraint('uq_pago_contrato_periodo', type_='unique')
    except Exception as e:  # base sin la constraint o motor que no la nombra
        print(f"[migración] no se pudo quitar la constraint única (sigo): {e}")
    # 2) Crear el índice único parcial (excluye anulados).
    if dialect == 'postgresql':
        op.create_index('uq_pago_contrato_periodo', 'pagos',
                        ['contrato_id', 'periodo_mes', 'periodo_anio'], unique=True,
                        postgresql_where=sa.text("estado <> 'Anulado'"))
    else:
        op.create_index('uq_pago_contrato_periodo', 'pagos',
                        ['contrato_id', 'periodo_mes', 'periodo_anio'], unique=True,
                        sqlite_where=sa.text("estado <> 'Anulado'"))


def downgrade():
    op.drop_index('uq_pago_contrato_periodo', table_name='pagos')
    with op.batch_alter_table('pagos', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_pago_contrato_periodo',
                                          ['contrato_id', 'periodo_mes', 'periodo_anio'])
