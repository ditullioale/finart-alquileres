"""ABM de Personas (propietarios e inquilinos)."""
from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, abort)
from flask_login import login_required

from .. import db
from ..models import Persona
from ..utils import normalizar_whatsapp

personas_bp = Blueprint("personas", __name__, url_prefix="/personas")


@personas_bp.route("/")
@login_required
def listar():
    q = request.args.get("q", "").strip()
    rol = request.args.get("rol", "")
    query = Persona.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Persona.nombre.ilike(like),
                                    Persona.dni.ilike(like),
                                    Persona.cuit.ilike(like)))
    if rol == "propietario":
        query = query.filter_by(es_propietario=True)
    elif rol == "inquilino":
        query = query.filter_by(es_inquilino=True)

    sort = request.args.get("sort", "")
    direccion = request.args.get("dir", "asc")
    cols = {"nombre": db.func.lower(Persona.nombre), "dni": Persona.dni, "cuit": Persona.cuit,
            "telefono": Persona.telefono, "email": db.func.lower(Persona.email)}
    col = cols.get(sort)
    if col is not None:
        query = query.order_by(col.desc() if direccion == "desc" else col.asc())
    else:
        query = query.order_by(Persona.nombre)
    personas = query.all()
    return render_template("personas/list.html", personas=personas, q=q, rol=rol)


def _leer_form(persona):
    persona.nombre = request.form.get("nombre", "").strip()
    persona.dni = request.form.get("dni", "").strip()
    persona.cuit = request.form.get("cuit", "").strip()
    persona.domicilio = request.form.get("domicilio", "").strip()
    persona.localidad = request.form.get("localidad", "").strip()
    persona.telefono = request.form.get("telefono", "").strip()
    persona.email = request.form.get("email", "").strip()
    persona.cond_iva = request.form.get("cond_iva", "").strip()
    persona.es_propietario = bool(request.form.get("es_propietario"))
    persona.es_inquilino = bool(request.form.get("es_inquilino"))
    persona.observaciones = request.form.get("observaciones", "").strip()


def _validar(persona):
    if not persona.nombre:
        return "El nombre es obligatorio."
    if persona.telefono and normalizar_whatsapp(persona.telefono) is None:
        return ("El teléfono no parece válido para WhatsApp. Cargalo con código de área, "
                "ej: 11 2345-6789 o 0221 15-456-7890 (sin dejarlo tan corto).")
    return None


@personas_bp.route("/nueva", methods=["GET", "POST"])
@login_required
def nueva():
    if request.method == "POST":
        persona = Persona()
        _leer_form(persona)
        error = _validar(persona)
        if error:
            flash(error, "error")
            return render_template("personas/form.html", persona=persona)
        db.session.add(persona)
        db.session.commit()
        flash("Persona creada correctamente.", "ok")
        return redirect(url_for("personas.listar"))
    return render_template("personas/form.html", persona=Persona())


@personas_bp.route("/<int:pid>/editar", methods=["GET", "POST"])
@login_required
def editar(pid):
    persona = db.session.get(Persona, pid) or abort(404)
    if request.method == "POST":
        _leer_form(persona)
        error = _validar(persona)
        if error:
            flash(error, "error")
            return render_template("personas/form.html", persona=persona)
        db.session.commit()
        flash("Persona actualizada.", "ok")
        return redirect(url_for("personas.listar"))
    return render_template("personas/form.html", persona=persona)


@personas_bp.route("/<int:pid>/eliminar", methods=["POST"])
@login_required
def eliminar(pid):
    persona = db.session.get(Persona, pid) or abort(404)
    if persona.inmuebles:
        flash("No se puede eliminar: tiene inmuebles asociados.", "error")
        return redirect(url_for("personas.listar"))
    db.session.delete(persona)
    db.session.commit()
    flash("Persona eliminada.", "ok")
    return redirect(url_for("personas.listar"))
