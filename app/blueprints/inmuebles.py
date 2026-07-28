"""ABM de Inmuebles."""
from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, abort)
from flask_login import login_required
from sqlalchemy.orm import aliased

from .. import db
from ..models import Inmueble, Persona

inmuebles_bp = Blueprint("inmuebles", __name__, url_prefix="/inmuebles")

ESTADOS = ["Disponible", "Alquilado", "Reservado"]
TIPOS = ["Casa", "Departamento", "Local", "Campo", "Cochera", "Oficina", "Terreno"]


@inmuebles_bp.route("/")
@login_required
def listar():
    q = request.args.get("q", "").strip()
    estado = request.args.get("estado", "")
    query = Inmueble.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Inmueble.codigo.ilike(like),
                                    Inmueble.direccion.ilike(like),
                                    Inmueble.localidad.ilike(like)))
    if estado:
        query = query.filter_by(estado=estado)

    sort = request.args.get("sort", "")
    direccion = request.args.get("dir", "asc")
    Prop = aliased(Persona)
    cols = {"direccion": db.func.lower(Inmueble.direccion), "tipo": db.func.lower(Inmueble.tipo),
            "localidad": db.func.lower(Inmueble.localidad), "estado": Inmueble.estado,
            "precio": Inmueble.precio_referencia, "propietario": db.func.lower(Prop.nombre)}
    col = cols.get(sort)
    if col is not None:
        if sort == "propietario":
            query = query.outerjoin(Prop, Inmueble.propietario_id == Prop.id)
        query = query.order_by(col.desc() if direccion == "desc" else col.asc())
    else:
        query = query.order_by(Inmueble.direccion)
    inmuebles = query.all()
    return render_template("inmuebles/list.html", inmuebles=inmuebles,
                           q=q, estado=estado, estados=ESTADOS)


@inmuebles_bp.route("/react")
@login_required
def react():
    return render_template("inmuebles/react.html")


def _leer_form(inmueble):
    inmueble.codigo = request.form.get("codigo", "").strip()
    inmueble.tipo = request.form.get("tipo", "").strip()
    inmueble.direccion = request.form.get("direccion", "").strip()
    inmueble.localidad = request.form.get("localidad", "").strip()
    inmueble.provincia = request.form.get("provincia", "").strip()
    inmueble.barrio = request.form.get("barrio", "").strip()
    inmueble.estado = request.form.get("estado", "Disponible")
    inmueble.moneda = request.form.get("moneda", "Pesos")
    inmueble.cuenta_gas = request.form.get("cuenta_gas", "").strip()
    inmueble.descripcion = request.form.get("descripcion", "").strip()
    inmueble.observaciones = request.form.get("observaciones", "").strip()

    def num(campo, entero=False):
        v = request.form.get(campo, "").strip().replace(".", "").replace(",", ".")
        if v == "":
            return None
        try:
            return int(float(v)) if entero else float(v)
        except ValueError:
            return None

    inmueble.dormitorios = num("dormitorios", entero=True)
    inmueble.banos = num("banos", entero=True)
    inmueble.precio_referencia = num("precio_referencia")
    inmueble.comision_pct = num("comision_pct")
    pid = request.form.get("propietario_id", "")
    inmueble.propietario_id = int(pid) if pid else None


@inmuebles_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    propietarios = Persona.query.filter_by(es_propietario=True).order_by(Persona.nombre).all()
    if request.method == "POST":
        inmueble = Inmueble()
        _leer_form(inmueble)
        if not inmueble.direccion:
            flash("La dirección es obligatoria.", "error")
            return render_template("inmuebles/form.html", inmueble=inmueble,
                                   propietarios=propietarios, estados=ESTADOS, tipos=TIPOS)
        db.session.add(inmueble)
        db.session.commit()
        flash("Inmueble creado correctamente.", "ok")
        return redirect(url_for("inmuebles.listar"))
    return render_template("inmuebles/form.html", inmueble=Inmueble(),
                           propietarios=propietarios, estados=ESTADOS, tipos=TIPOS)


@inmuebles_bp.route("/<int:iid>/editar", methods=["GET", "POST"])
@login_required
def editar(iid):
    inmueble = db.session.get(Inmueble, iid) or abort(404)
    propietarios = Persona.query.filter_by(es_propietario=True).order_by(Persona.nombre).all()
    if request.method == "POST":
        _leer_form(inmueble)
        if not inmueble.direccion:
            flash("La dirección es obligatoria.", "error")
            return render_template("inmuebles/form.html", inmueble=inmueble,
                                   propietarios=propietarios, estados=ESTADOS, tipos=TIPOS)
        db.session.commit()
        flash("Inmueble actualizado.", "ok")
        return redirect(url_for("inmuebles.listar"))
    return render_template("inmuebles/form.html", inmueble=inmueble,
                           propietarios=propietarios, estados=ESTADOS, tipos=TIPOS)


@inmuebles_bp.route("/<int:iid>/eliminar", methods=["POST"])
@login_required
def eliminar(iid):
    inmueble = db.session.get(Inmueble, iid) or abort(404)
    if inmueble.contratos:
        flash("No se puede eliminar: tiene contratos asociados.", "error")
        return redirect(url_for("inmuebles.listar"))
    db.session.delete(inmueble)
    db.session.commit()
    flash("Inmueble eliminado.", "ok")
    return redirect(url_for("inmuebles.listar"))
