"""número de recibo irrepetible + claves de idempotencia

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa

revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


DUPLICADOS_RECIBO = sa.text("""
    SELECT inmobiliaria_id, recibo_numero, COUNT(*) AS n
      FROM pagos
     WHERE recibo_numero IS NOT NULL AND recibo_numero <> ''
     GROUP BY inmobiliaria_id, recibo_numero
    HAVING COUNT(*) > 1
""")


def upgrade():
    conn = op.get_bind()

    op.create_table(
        'operaciones_idem',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clave', sa.String(length=120), nullable=False),
        sa.Column('creado', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('operaciones_idem', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_operaciones_idem_clave'),
                              ['clave'], unique=True)

    # "Sin número" tiene que ser NULL y no cadena vacía: dos vacías chocarían
    # contra el único, mientras que los NULL no compiten entre sí.
    conn.execute(sa.text("UPDATE pagos SET recibo_numero = NULL "
                         "WHERE recibo_numero = ''"))

    repetidos = conn.execute(DUPLICADOS_RECIBO).fetchall()
    if repetidos:
        detalle = "; ".join(f"inmobiliaria {r[0]}, recibo {r[1]}: {r[2]} pagos"
                            for r in repetidos)
        print("[migración] no activo el único de número de recibo porque ya hay "
              f"números repetidos ({detalle}). Renumeralos y volvé a aplicar.")
        return

    with op.batch_alter_table('pagos', schema=None) as batch_op:
        batch_op.create_unique_constraint(
            'uq_pago_recibo_numero', ['inmobiliaria_id', 'recibo_numero'])


def downgrade():
    with op.batch_alter_table('pagos', schema=None) as batch_op:
        batch_op.drop_constraint('uq_pago_recibo_numero', type_='unique')
    op.drop_table('operaciones_idem')
