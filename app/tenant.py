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

# Modelos con inmobiliaria_id sujetos al filtro central de lectura.
# Usuario NO se incluye acá: filtrarlo rompería la carga del propio usuario en
# el login. La separación de usuarios por inmobiliaria se hace explícitamente en
# las pantallas de Usuarios (listar/editar/eliminar).
_TENANT_MODEL_NAMES = ["Persona", "Inmueble", "Contrato", "Aumento", "Pago",
                       "GasEstado", "ReciboManual", "Liquidacion",
                       "RegistroAuditoria"]


def _tenant_modelos():
    from . import models
    return [getattr(models, n) for n in _TENANT_MODEL_NAMES]


def _tenant_para_filtro():
    """Inmobiliaria a usar para FILTRAR lecturas.

    - Anónimo (login, robot) o superadmin de plataforma: None = no filtrar.
    - Usuario normal: su inmobiliaria. Si por error no tuviera, -1 (no ve nada),
      nunca 'ver todo'.
    """
    try:
        if getattr(current_user, "is_authenticated", False):
            if getattr(current_user, "rol", None) == "superadmin":
                return None
            tid = getattr(current_user, "inmobiliaria_id", None)
            return tid if tid else -1
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
    # (Los Usuario NO se auto-asignan: superadmin=None, el resto se asignan
    # explícitamente al crearlos.)
    @event.listens_for(db.session, "before_flush")
    def _asignar_tenant(session, flush_ctx, instances):
        pendientes = [o for o in session.new
                      if hasattr(o, "inmobiliaria_id")
                      and getattr(o, "inmobiliaria_id", None) is None
                      and type(o).__name__ != "Usuario"]
        if not pendientes:
            return
        # Inmobiliaria del usuario logueado (no superadmin); si no hay, principal.
        tid = None
        try:
            if (getattr(current_user, "is_authenticated", False)
                    and getattr(current_user, "rol", None) != "superadmin"):
                tid = getattr(current_user, "inmobiliaria_id", None)
        except Exception:
            tid = None
        if not tid:
            from .models import Inmobiliaria
            with session.no_autoflush:
                inmo = Inmobiliaria.query.order_by(Inmobiliaria.id).first()
            tid = inmo.id if inmo else None
        if not tid:
            return
        for obj in pendientes:
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
