"""Gestión de usuarios del sistema (solo para administradores)."""
from functools import wraps

from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, abort)
from flask_login import login_required, current_user

from .. import db
from ..models import Usuario

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")

ROLES = [("admin", "Administrador (gestiona usuarios y todo el sistema)"),
         ("operador", "Operador (usa el sistema)")]


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def _cant_admins_activos(excluir_id=None):
    q = Usuario.query.filter_by(rol="admin", activo=True)
    if excluir_id:
        q = q.filter(Usuario.id != excluir_id)
    return q.count()


@usuarios_bp.route("/")
@login_required
@admin_required
def listar():
    usuarios = Usuario.query.order_by(Usuario.nombre, Usuario.username).all()
    return render_template("usuarios/list.html", usuarios=usuarios)


@usuarios_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def nuevo():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        nombre = request.form.get("nombre", "").strip()
        rol = request.form.get("rol", "operador")
        password = request.form.get("password", "")
        error = None
        if not username:
            error = "El nombre de usuario es obligatorio."
        elif Usuario.query.filter_by(username=username).first():
            error = "Ya existe un usuario con ese nombre."
        elif len(password) < 4:
            error = "La contraseña debe tener al menos 4 caracteres."
        if error:
            flash(error, "error")
            return render_template("usuarios/form.html", u=None, roles=ROLES,
                                   datos={"username": username, "nombre": nombre, "rol": rol})
        u = Usuario(username=username, nombre=nombre, rol=rol, activo=True)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        flash(f"Usuario '{username}' creado.", "ok")
        return redirect(url_for("usuarios.listar"))
    return render_template("usuarios/form.html", u=None, roles=ROLES, datos={})


@usuarios_bp.route("/<int:uid>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def editar(uid):
    u = db.session.get(Usuario, uid) or abort(404)
    if request.method == "POST":
        nuevo_rol = request.form.get("rol", u.rol)
        activo = bool(request.form.get("activo"))
        # Proteger al último admin activo.
        quita_admin = (u.rol == "admin" and (nuevo_rol != "admin" or not activo))
        if quita_admin and _cant_admins_activos(excluir_id=u.id) == 0:
            flash("No podés dejar el sistema sin ningún administrador activo.", "error")
            return redirect(url_for("usuarios.editar", uid=u.id))
        u.nombre = request.form.get("nombre", "").strip()
        u.rol = nuevo_rol
        u.activo = activo
        nueva = request.form.get("password", "")
        if nueva:
            if len(nueva) < 4:
                flash("La nueva contraseña es muy corta.", "error")
                return redirect(url_for("usuarios.editar", uid=u.id))
            u.set_password(nueva)
        db.session.commit()
        flash("Usuario actualizado." + (" Contraseña cambiada." if nueva else ""), "ok")
        return redirect(url_for("usuarios.listar"))
    return render_template("usuarios/form.html", u=u, roles=ROLES, datos={})


@usuarios_bp.route("/<int:uid>/eliminar", methods=["POST"])
@login_required
@admin_required
def eliminar(uid):
    u = db.session.get(Usuario, uid) or abort(404)
    if u.id == current_user.id:
        flash("No podés eliminar tu propio usuario.", "error")
        return redirect(url_for("usuarios.listar"))
    if u.rol == "admin" and _cant_admins_activos(excluir_id=u.id) == 0:
        flash("No podés eliminar al último administrador.", "error")
        return redirect(url_for("usuarios.listar"))
    db.session.delete(u)
    db.session.commit()
    flash(f"Usuario '{u.username}' eliminado.", "ok")
    return redirect(url_for("usuarios.listar"))
