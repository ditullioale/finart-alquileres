"""Multiempresa: helpers de 'tenant' (inmobiliaria actual).

PASO 1 (fundamento): toda entidad pertenece a una inmobiliaria y los registros
nuevos se asignan automáticamente a la inmobiliaria del usuario logueado. El
FILTRADO de aislamiento (que un usuario no vea datos de otra inmobiliaria) se
agrega en el paso 2; por eso acá todavía no se filtran las consultas.
"""
from flask_login import current_user

from . import db


def tenant_actual():
    """Inmobiliaria del usuario logueado. Durante la transición (una sola
    inmobiliaria) cae a la principal si no hay usuario."""
    try:
        if getattr(current_user, "is_authenticated", False):
            tid = getattr(current_user, "inmobiliaria_id", None)
            if tid:
                return tid
    except Exception:
        pass
    from .models import Inmobiliaria
    inmo = Inmobiliaria.principal()
    return inmo.id if inmo else None


def registrar_eventos():
    """Asigna inmobiliaria_id automáticamente al crear registros (Capa 2).

    Usa solo el usuario logueado (sin consultar la base durante el flush, para
    evitar reentrancias). Los registros sin usuario (robot, seeds) se completan
    en el backfill del arranque."""
    from sqlalchemy import event

    @event.listens_for(db.session, "before_flush")
    def _asignar_tenant(session, flush_ctx, instances):
        tid = None
        try:
            if getattr(current_user, "is_authenticated", False):
                tid = getattr(current_user, "inmobiliaria_id", None)
        except Exception:
            tid = None
        if not tid:
            return
        for obj in session.new:
            if hasattr(obj, "inmobiliaria_id") and getattr(obj, "inmobiliaria_id", None) is None:
                obj.inmobiliaria_id = tid
