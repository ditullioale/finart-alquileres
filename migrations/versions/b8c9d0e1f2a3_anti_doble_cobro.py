"""Anti doble cobro: un pago por contrato/período, recibos irrepetibles y
claves de idempotencia.

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


DUPLICADOS_PERIODO = sa.text("""
    SELECT contrato_id, periodo_mes, periodo_anio, COUNT(*) AS n
      FROM pagos
     WHERE periodo_mes IS NOT NULL AND periodo_anio IS NOT NULL
     GROUP BY contrato_id, periodo_mes, periodo_anio
    HAVING COUNT(*) > 1
""")

DUPLICADOS_RECIBO = sa.text("""
    SELECT inmobiliaria_id, recibo_numero, COUNT(*) AS n
      FROM pagos
     WHERE recibo_numero IS NOT NULL AND recibo_numero <> ''
     GROUP BY inmobiliaria_id, recibo_numero
    HAVING COUNT(*) > 1
""")


def _cortar_si_hay_duplicados(conn):
    """No se puede crear el índice único si los datos ya tienen duplicados.

    En vez de fallar con un error de base incomprensible, se corta acá diciendo
    exactamente qué pagos hay que unificar a mano (borrar el repetido o pasarlo
    al período correcto): son decisiones de plata, no las toma la migración."""
    periodos = conn.execute(DUPLICADOS_PERIODO).fetchall()
    recibos = conn.execute(DUPLICADOS_RECIBO).fetchall()
    if not periodos and not recibos:
        return
    partes = []
    for r in periodos:
        partes.append(f"contrato {r[0]}, período {r[1]}/{r[2]}: {r[3]} pagos")
    for r in recibos:
        partes.append(f"inmobiliaria {r[0]}, recibo {r[1]}: {r[2]} pagos")
    raise RuntimeError(
        "No puedo activar el control de doble cobro porque ya hay pagos "
        "repetidos en la base. Unificalos (dejando uno por período y por "
        "número de recibo) y volvé a correr la migración:\n  - "
        + "\n  - ".join(partes))


def upgrade():
    conn = op.get_bind()
    # "Sin número" tiene que ser NULL y no cadena vacía: dos vacías chocarían
    # contra el único, mientras que los NULL no compiten entre sí.
    conn.execute(sa.text("UPDATE pagos SET recibo_numero = NULL "
                         "WHERE recibo_numero = ''"))
    _cortar_si_hay_duplicados(conn)

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

    with op.batch_alter_table('pagos', schema=None) as batch_op:
        batch_op.create_unique_constraint(
            'uq_pago_contrato_periodo', ['contrato_id', 'periodo_mes', 'periodo_anio'])
        batch_op.create_unique_constraint(
            'uq_pago_recibo_numero', ['inmobiliaria_id', 'recibo_numero'])


def downgrade():
    with op.batch_alter_table('pagos', schema=None) as batch_op:
        batch_op.drop_constraint('uq_pago_recibo_numero', type_='unique')
        batch_op.drop_constraint('uq_pago_contrato_periodo', type_='unique')
    op.drop_table('operaciones_idem')
