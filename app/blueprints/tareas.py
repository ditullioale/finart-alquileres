"""Tareas pendientes: recordatorios de acciones a realizar por la inmobiliaria.

Se agregan desde el dashboard (menú emergente), figuran mientras están pendientes
y desaparecen al tildarlas como completadas. Aisladas por inmobiliaria como el
resto (llevan inmobiliaria_id y las consultas se filtran por el tenant activo).
"""
from datetime import datetime

from flask import (Blueprint, request, redirect, url_for, jsonify, abort, flash)
from flask_login import login_required, current_user

from .. import db
from ..models import TareaPendiente

tareas_bp = Blueprint("tareas", __name__, url_prefix="/tareas")


def _quiere_json():
    return (request.is_json
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in (request.headers.get("Accept") or ""))


def pendientes():
    """Tareas sin completar de la inmobiliaria activa, más nuevas primero."""
    return (TareaPendiente.query.filter_by(completada=False)
            .order_by(TareaPendiente.creado.desc()).all())


@tareas_bp.route("/nueva", methods=["POST"])
@login_required
def nueva():
    datos = request.get_json(silent=True) or request.form
    texto = (datos.get("texto") or "").strip()
    if not texto:
        if _quiere_json():
            return jsonify(ok=False, error="Escribí la tarea."), 400
        flash("Escribí la tarea pendiente.", "error")
        return redirect(request.referrer or url_for("main.index"))
    autor = getattr(current_user, "username", None) or "—"
    t = TareaPendiente(texto=texto[:300], autor=autor)
    db.session.add(t)
    db.session.commit()
    if _quiere_json():
        return jsonify(ok=True, id=t.id, texto=t.texto, autor=t.autor)
    flash("Tarea agregada.", "ok")
    return redirect(request.referrer or url_for("main.index"))


@tareas_bp.route("/<int:tid>/completar", methods=["POST"])
@login_required
def completar(tid):
    t = db.session.get(TareaPendiente, tid) or abort(404)
    t.completada = True
    t.completada_en = datetime.utcnow()
    t.completada_por = getattr(current_user, "username", None) or "—"
    db.session.commit()
    if _quiere_json():
        return jsonify(ok=True)
    flash("Tarea completada.", "ok")
    return redirect(request.referrer or url_for("main.index"))


@tareas_bp.route("/<int:tid>/eliminar", methods=["POST"])
@login_required
def eliminar(tid):
    t = db.session.get(TareaPendiente, tid) or abort(404)
    db.session.delete(t)
    db.session.commit()
    if _quiere_json():
        return jsonify(ok=True)
    flash("Tarea eliminada.", "ok")
    return redirect(request.referrer or url_for("main.index"))
