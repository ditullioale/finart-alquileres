"""pago único por contrato+período (anti doble cobro)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa

revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    # Defensivo: si ya hubiera períodos duplicados en una base existente, NO
    # rompemos el deploy; se omite la restricción y queda la validación de la app.
    conn = op.get_bind()
    dups = conn.execute(sa.text(
        "SELECT COUNT(*) FROM (SELECT contrato_id, periodo_mes, periodo_anio "
        "FROM pagos WHERE periodo_mes IS NOT NULL AND periodo_anio IS NOT NULL "
        "GROUP BY contrato_id, periodo_mes, periodo_anio HAVING COUNT(*) > 1) t"
    )).scalar()
    if dups and int(dups) > 0:
        print(f"[migración] {dups} período(s) con pagos duplicados: se omite la "
              "restricción única de pago. Resolvé los duplicados y volvé a aplicar.")
        return
    with op.batch_alter_table('pagos', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_pago_contrato_periodo',
                                          ['contrato_id', 'periodo_mes', 'periodo_anio'])


def downgrade():
    with op.batch_alter_table('pagos', schema=None) as batch_op:
        batch_op.drop_constraint('uq_pago_contrato_periodo', type_='unique')
