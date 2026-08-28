"""contenido de mails (bienvenida/notificaciones) configurable por inmobiliaria

Agrega a Ajustes los campos email_bio / email_firma / email_pie, para que
cada inmobiliaria pueda cargar su propio texto en los mails automáticos en
vez de que el sistema use el de otra. Ver app/emailer_contenido.py.

Revision ID: a9b1c2d3e4f5
Revises: e7f8a9b0c1d2
Create Date: 2026-08-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'a9b1c2d3e4f5'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ajustes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email_bio', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('email_firma', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('email_pie', sa.String(length=200), nullable=True))

    # Backfill: conserva tal cual el texto que hoy está escrito a mano en el
    # código, para que el comportamiento de FINART no cambie. Toda fila de
    # `ajustes` que ya exista en esta base es, a la fecha de esta migración,
    # la de FINART (todavía no hay una segunda inmobiliaria en producción).
    # Una inmobiliaria que se dé de alta después arranca con estos campos
    # vacíos y usa el texto genérico por defecto (emailer_contenido.py) --
    # nunca el de FINART.
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE ajustes SET email_bio = :bio, email_firma = :firma, "
            "email_pie = :pie WHERE email_bio IS NULL"
        ),
        {
            "bio": (
                "Somos FINART, una inmobiliaria con más de 40 años en Arroyo Seco "
                "-- y también un Estudio Jurídico. Además de alquileres y ventas, "
                "asesoramos en derecho sucesorio, laboral, contractual y de familia."
            ),
            "firma": (
                "Dr. Alejandro R. Di Tullio — Abogado, Corredor Inmobiliario\n"
                "Dra. María M. Di Tullio — Abogado"
            ),
            "pie": "FINART Propiedades — Arroyo Seco",
        },
    )


def downgrade():
    with op.batch_alter_table('ajustes', schema=None) as batch_op:
        batch_op.drop_column('email_pie')
        batch_op.drop_column('email_firma')
        batch_op.drop_column('email_bio')
