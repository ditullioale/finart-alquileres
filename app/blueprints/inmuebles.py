"""ABM de Inmuebles."""
from flask import (Blueprint, redirect, url_for, request,
                   flash, abort, jsonify)
from flask_login import login_required
from sqlalchemy.orm import aliased
from sqlalchemy.exc import IntegrityError

from .. import db
from ..models import Inmueble, Persona
from ..ui import render_ui
from ..utils import parse_num


def _guardar_o_avisar(inmueble, propietarios):
    """Commit; si el código choca (único), avisa en vez de romper. Devuelve la respuesta
    a renderizar en caso de error, o None si guardó bien."""
    try:
        db.session.commit()
        return None
    except IntegrityError:
        db.session.rollback()
        flash("Ya existe un inmueble con ese código. Usá otro (o dejalo vacío).", "error")
        return render_ui("inmuebles/form.html", inmueble=inmueble,
                               propietarios=propietarios, estados=ESTADOS, tipos=TIPOS)

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
    from sqlalchemy.orm import joinedload
    inmuebles = query.options(joinedload(Inmueble.propietario)).all()
    return render_ui("inmuebles/list.html", inmuebles=inmuebles,
                           q=q, estado=estado, estados=ESTADOS)


# Islas React desactivadas: se conserva el código y las plantillas por si se
# retoman. Las rutas redirigen a la versión clásica.
@inmuebles_bp.route("/react")
@login_required
def react():
    return redirect(url_for("inmuebles.listar"))


@inmuebles_bp.route("/react/nuevo")
@login_required
def react_nuevo():
    return redirect(url_for("inmuebles.nuevo"))


@inmuebles_bp.route("/react/<int:iid>/editar")
@login_required
def react_editar(iid):
    return redirect(url_for("inmuebles.editar", iid=iid))


def _leer_form(inmueble):
    # Vacío -> None (no ""), porque 'codigo' es único: dos inmuebles con "" chocarían.
    inmueble.codigo = request.form.get("codigo", "").strip() or None
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
        return parse_num(request.form.get(campo, ""), entero=entero)

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
            return render_ui("inmuebles/form.html", inmueble=inmueble,
                                   propietarios=propietarios, estados=ESTADOS, tipos=TIPOS)
        db.session.add(inmueble)
        err = _guardar_o_avisar(inmueble, propietarios)
        if err:
            return err
        flash("Inmueble creado correctamente.", "ok")
        return redirect(url_for("inmuebles.listar"))
    return render_ui("inmuebles/form.html", inmueble=Inmueble(),
                           propietarios=propietarios, estados=ESTADOS, tipos=TIPOS)


@inmuebles_bp.route("/nuevo-rapido", methods=["POST"])
@login_required
def nuevo_rapido():
    """Alta rápida (JSON) desde el formulario de contrato: crea el inmueble con lo mínimo
    y lo devuelve para agregarlo al selector sin recargar la página."""
    d = request.get_json(silent=True) or {}
    direccion = (d.get("direccion") or "").strip()
    if not direccion:
        return jsonify(ok=False, error="La dirección es obligatoria."), 200
    inm = Inmueble(direccion=direccion, estado="Disponible", moneda="Pesos",
                   codigo=((d.get("codigo") or "").strip() or None))
    pid = d.get("propietario_id")
    if pid:
        try:
            inm.propietario_id = int(pid)
        except (TypeError, ValueError):
            pass
    db.session.add(inm)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(ok=False, error="Ya existe un inmueble con ese código."), 200
    texto = (f"{inm.codigo} · " if inm.codigo else "") + inm.direccion
    return jsonify(ok=True, id=inm.id, texto=texto, propietario_id=inm.propietario_id or "")


@inmuebles_bp.route("/<int:iid>/editar", methods=["GET", "POST"])
@login_required
def editar(iid):
    inmueble = db.session.get(Inmueble, iid) or abort(404)
    propietarios = Persona.query.filter_by(es_propietario=True).order_by(Persona.nombre).all()
    if request.method == "POST":
        _leer_form(inmueble)
        if not inmueble.direccion:
            flash("La dirección es obligatoria.", "error")
            return render_ui("inmuebles/form.html", inmueble=inmueble,
                                   propietarios=propietarios, estados=ESTADOS, tipos=TIPOS)
        err = _guardar_o_avisar(inmueble, propietarios)
        if err:
            return err
        flash("Inmueble actualizado.", "ok")
        return redirect(url_for("inmuebles.listar"))
    return render_ui("inmuebles/form.html", inmueble=inmueble,
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
