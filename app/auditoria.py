"""Auditoría automática: registra altas, cambios y eliminaciones.

Escucha los flush de SQLAlchemy y anota en la tabla `auditoria` cada creación,
edición o borrado de las entidades importantes, junto con el usuario, la fecha y
la IP. Se escribe con un INSERT de bajo nivel dentro de la misma transacción, así
no interfiere con la sesión ORM ni se audita a sí misma.
"""
from datetime import datetime

from . import db

# Entidades que se auditan (por nombre de clase).
AUDITADAS = {"Persona", "Inmueble", "Contrato", "Pago", "Aumento",
             "Liquidacion", "ReciboManual", "Usuario", "GasEstado"}


def _descripcion(obj):
    """Texto legible para el registro (nombre del inquilino, dirección, etc.)."""
    cls = type(obj).__name__
    try:
        if cls == "Persona":
            return obj.nombre or ""
        if cls == "Inmueble":
            return obj.direccion or ""
        if cls == "Contrato":
            inq = obj.inquilino.nombre if getattr(obj, "inquilino", None) else "?"
            dir_ = obj.inmueble.direccion if getattr(obj, "inmueble", None) else "?"
            return f"{inq} — {dir_}"
        if cls == "Pago":
            return f"Período {obj.periodo_mes}/{obj.periodo_anio} — {obj.moneda} {obj.total or 0}"
        if cls == "Aumento":
            return f"{obj.precio_anterior or 0} → {obj.precio_nuevo or 0}"
        if cls == "Usuario":
            return obj.username or ""
        if cls == "ReciboManual":
            return obj.cliente or ""
        if cls == "GasEstado":
            return obj.cuenta or ""
    except Exception:
        pass
    return ""


def registrar_auditoria():
    """Instala el listener de auditoría sobre la sesión."""
    from sqlalchemy import event

    @event.listens_for(db.session, "after_flush")
    def _auditar(session, flush_ctx):
        from flask import request, has_request_context
        from flask_login import current_user
        from .models import RegistroAuditoria

        cambios = []

        def add(obj, accion):
            if type(obj).__name__ in AUDITADAS:
                cambios.append((accion, type(obj).__name__,
                                getattr(obj, "id", None), _descripcion(obj)))

        for o in session.new:
            add(o, "crear")
        for o in session.deleted:
            add(o, "eliminar")
        for o in session.dirty:
            if session.is_modified(o, include_collections=False):
                add(o, "editar")
        if not cambios:
            return

        autenticado = getattr(current_user, "is_authenticated", False)
        uid = getattr(current_user, "id", None) if autenticado else None
        uname = ((getattr(current_user, "nombre", None)
                  or getattr(current_user, "username", None)) if autenticado else "sistema")
        tid = getattr(current_user, "inmobiliaria_id", None) if autenticado else None
        ip = request.remote_addr if has_request_context() else None

        conn = session.connection()
        tabla = RegistroAuditoria.__table__
        for accion, ent, pk, desc in cambios:
            conn.execute(tabla.insert().values(
                inmobiliaria_id=tid, usuario_id=uid, usuario_nombre=uname,
                accion=accion, entidad=ent,
                entidad_id=(str(pk) if pk is not None else None),
                descripcion=(desc or "")[:300], ip=ip, fecha=datetime.utcnow()))
