"""Panel de plataforma (superadmin del SaaS).

Solo para el dueño de la plataforma (rol 'superadmin', sin inmobiliaria propia).
Permite dar de alta nuevas inmobiliarias con su primer administrador (onboarding).
El superadmin no ve el filtro de tenant (inmobiliaria_id None), así que puede
administrar todas las inmobiliarias.
"""
from functools import wraps

from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, abort)
from flask_login import login_required, current_user

from datetime import datetime

from .. import db
from ..models import Inmobiliaria, Usuario, SolicitudAlta

plataforma_bp = Blueprint("plataforma", __name__, url_prefix="/plataforma")


def superadmin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol != "superadmin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper


@plataforma_bp.route("/test-sentry")
@login_required
@superadmin_required
def test_sentry():
    """Genera un error a propósito para confirmar que Sentry captura los errores.
    Solo el superadmin puede dispararlo. Si Sentry NO está configurado, igual verás
    la página de error del servidor (500); si SÍ está, el error aparece en Sentry."""
    raise RuntimeError("Prueba de Sentry desde /plataforma/test-sentry (ignorar).")


@plataforma_bp.route("/")
@login_required
@superadmin_required
def index():
    inmos = Inmobiliaria.query.order_by(Inmobiliaria.id).all()
    datos = []
    for i in inmos:
        usuarios = Usuario.query.filter_by(inmobiliaria_id=i.id).count()
        datos.append(dict(i=i, usuarios=usuarios))
    solicitudes = (SolicitudAlta.query.filter_by(estado="pendiente")
                   .order_by(SolicitudAlta.creada).all())
    return render_template("plataforma/index.html", datos=datos,
                           solicitudes=solicitudes)


@plataforma_bp.route("/solicitudes/<int:sid>/aprobar", methods=["POST"])
@login_required
@superadmin_required
def aprobar_solicitud(sid):
    s = db.session.get(SolicitudAlta, sid)
    if not s:
        abort(404)
    if s.estado != "pendiente":
        flash("Esa solicitud ya fue procesada.", "error")
        return redirect(url_for("plataforma.index"))
    if Usuario.query.filter_by(username=s.username).first():
        flash(f"El usuario «{s.username}» ya existe. Rechazá la solicitud o pedí "
              "que se registre con otro usuario.", "error")
        return redirect(url_for("plataforma.index"))

    inmo = Inmobiliaria(nombre=s.nombre_inmobiliaria, localidad=s.localidad,
                        plan="inicial")
    db.session.add(inmo)
    db.session.flush()   # obtener inmo.id
    u = Usuario(username=s.username, nombre=(s.nombre_contacto or s.username),
                email=(s.email or None), rol="admin", activo=True,
                must_change_password=False, inmobiliaria_id=inmo.id)
    u.password_hash = s.password_hash   # ya la eligió al registrarse
    db.session.add(u)
    s.estado = "aprobada"
    s.procesada = datetime.utcnow()
    db.session.commit()
    flash(f"Solicitud aprobada. «{s.nombre_inmobiliaria}» ya puede ingresar "
          f"con el usuario «{s.username}».", "ok")
    return redirect(url_for("plataforma.index"))


@plataforma_bp.route("/solicitudes/<int:sid>/rechazar", methods=["POST"])
@login_required
@superadmin_required
def rechazar_solicitud(sid):
    s = db.session.get(SolicitudAlta, sid)
    if not s:
        abort(404)
    if s.estado == "pendiente":
        s.estado = "rechazada"
        s.procesada = datetime.utcnow()
        db.session.commit()
    flash("Solicitud rechazada.", "ok")
    return redirect(url_for("plataforma.index"))


@plataforma_bp.route("/inmobiliarias/nueva", methods=["GET", "POST"])
@login_required
@superadmin_required
def nueva_inmobiliaria():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        cuit = request.form.get("cuit", "").strip()
        localidad = request.form.get("localidad", "").strip()
        admin_user = request.form.get("admin_user", "").strip().lower()
        admin_nombre = request.form.get("admin_nombre", "").strip()
        admin_pass = request.form.get("admin_pass", "")
        plan = request.form.get("plan", "inicial")

        error = None
        if not nombre:
            error = "El nombre de la inmobiliaria es obligatorio."
        elif not admin_user:
            error = "Indicá el usuario del administrador."
        elif Usuario.query.filter_by(username=admin_user).first():
            error = "Ya existe un usuario con ese nombre."
        elif len(admin_pass) < 6:
            error = "La contraseña del administrador debe tener al menos 6 caracteres."
        if error:
            flash(error, "error")
            return render_template("plataforma/form.html", datos=request.form)

        inmo = Inmobiliaria(nombre=nombre, cuit=cuit, localidad=localidad, plan=plan)
        db.session.add(inmo)
        db.session.flush()   # obtener inmo.id
        u = Usuario(username=admin_user, nombre=(admin_nombre or admin_user),
                    rol="admin", activo=True, must_change_password=True,
                    inmobiliaria_id=inmo.id)   # explícito: pertenece a la nueva inmobiliaria
        u.set_password(admin_pass)
        db.session.add(u)
        db.session.commit()
        flash(f"Inmobiliaria «{nombre}» creada. Su administrador ({admin_user}) "
              "deberá cambiar la contraseña en el primer ingreso.", "ok")
        return redirect(url_for("plataforma.index"))
    return render_template("plataforma/form.html", datos={})
