"""Multiempresa: aislamiento por 'tenant' (inmobiliaria).

Tres capas de defensa (roadmap FINART 2.0 §3.3):
  - Capa 1: filtro central de LECTURA. Toda consulta sobre entidades con tenant
    se limita a la inmobiliaria del usuario logueado (cubre listados, búsquedas
    y accesos por ID vía db.session.get, porque cada request usa sesión limpia).
  - Capa 2: asignación automática de inmobiliaria al CREAR registros.
  - Capa 3: helper get_or_404_tenant para accesos por ID (defensa extra).

Cuando no hay usuario logueado (login, robot, seeds) NO se filtra: el tenant es
None y las consultas ven todo (necesario para autenticar y para procesos de
sistema). Los datos sin inmobiliaria se curan en el backfill del arranque.
"""
from flask import abort
from flask_login import current_user

from . import db

# Nombres de los modelos con inmobiliaria_id (se resuelven en runtime).
_TENANT_MODEL_NAMES = ["Persona", "Inmueble", "Contrato", "Aumento", "Pago",
                       "GasEstado", "ReciboManual", "Liquidacion", "Usuario"]


def _tenant_modelos():
    from . import models
    return [getattr(models, n) for n in _TENANT_MODEL_NAMES]


def _tenant_para_filtro():
    """Inmobiliaria a usar para FILTRAR. None = no filtrar (anónimo o superadmin)."""
    try:
        if getattr(current_user, "is_authenticated", False):
            return getattr(current_user, "inmobiliaria_id", None)
    except Exception:
        pass
    return None


def tenant_actual():
    """Inmobiliaria del usuario logueado. Durante la transición (una sola
    inmobiliaria) cae a la principal si no hay usuario. Se usa para ASIGNAR."""
    tid = _tenant_para_filtro()
    if tid:
        return tid
    from .models import Inmobiliaria
    inmo = Inmobiliaria.principal()
    return inmo.id if inmo else None


def get_or_404_tenant(model, ident):
    """Trae un registro por ID verificando que sea de la inmobiliaria actual.
    (El filtro de Capa 1 ya lo cubre; esto es defensa explícita adicional.)"""
    obj = db.session.get(model, ident)
    if obj is None:
        abort(404)
    tid = _tenant_para_filtro()
    if tid is not None and getattr(obj, "inmobiliaria_id", None) not in (None, tid):
        abort(404)
    return obj


def registrar_eventos():
    """Instala las Capas 1 y 2 sobre la sesión de SQLAlchemy."""
    from sqlalchemy import event
    from sqlalchemy.orm import with_loader_criteria

    # --- Capa 2: asignar inmobiliaria al crear ---
    @event.listens_for(db.session, "before_flush")
    def _asignar_tenant(session, flush_ctx, instances):
        tid = _tenant_para_filtro()
        if not tid:
            return
        for obj in session.new:
            if hasattr(obj, "inmobiliaria_id") and getattr(obj, "inmobiliaria_id", None) is None:
                obj.inmobiliaria_id = tid

    # --- Capa 1: filtro central de lectura ---
    def _crit(model, tid):
        return with_loader_criteria(
            model, lambda cls: cls.inmobiliaria_id == tid, include_aliases=True)

    @event.listens_for(db.session, "do_orm_execute")
    def _filtrar_por_tenant(state):
        if not state.is_select or state.is_column_load:
            return
        tid = _tenant_para_filtro()
        if tid is None:
            return
        opciones = [_crit(m, tid) for m in _tenant_modelos()]
        state.statement = state.statement.options(*opciones)
