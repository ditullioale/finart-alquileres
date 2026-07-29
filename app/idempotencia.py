"""Anti doble cobro: claves de idempotencia para las operaciones de plata.

Cada pantalla que registra plata (cobro rápido, alta de pago, pago a cuenta)
manda una clave única generada al abrir el formulario. Antes de guardar se
reserva esa clave en la misma transacción: si el pedido llega dos veces —doble
clic, F5 sobre el POST, dos pestañas, un reintento del navegador— la segunda vez
la clave ya está tomada y no se cobra de nuevo.
"""
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from . import db
from .models import OperacionIdem

# Cuánto se guardan las claves. Alcanza de sobra para reintentos del navegador y
# evita que la tabla crezca sin límite.
DIAS_RETENCION = 7


def nueva_clave():
    """Clave para poner en un formulario (hidden 'idem')."""
    return uuid4().hex


def reservar(alcance, clave):
    """Reserva la clave para esa operación. False = ya se había ejecutado.

    Se llama antes de guardar y deja la reserva pendiente en la sesión: se
    confirma con el mismo commit que la operación, así nunca queda una clave
    quemada por una operación que al final falló."""
    if not clave:
        return True
    completa = f"{alcance}:{str(clave)[:80]}"
    db.session.add(OperacionIdem(clave=completa))
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return False
    return True


def purgar(probabilidad=20):
    """Borra claves viejas de a poco (1 de cada `probabilidad` llamadas)."""
    if uuid4().int % probabilidad:
        return
    limite = datetime.utcnow() - timedelta(days=DIAS_RETENCION)
    try:
        OperacionIdem.query.filter(OperacionIdem.creado < limite).delete()
        db.session.commit()
    except Exception:
        db.session.rollback()
