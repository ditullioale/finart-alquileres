"""Gestión de usuarios del sistema (solo para administradores)."""
from functools import wraps

from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, abort)
from flask_login import login_required, current_user

from .. import db
from ..models import Usuario

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")

ROLES = [("admin", "Administrador (gestiona usuarios y todo el sistema)"),
         ("operador", "Operador (usa el sistema y carga datos)"),
         ("contador", "Contador (ve y exporta, sin modificar)"),
         ("lectura", "Solo lectura (ve todo, no modifica)")]


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol not in ("admin", "superadmin"):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def _cant_admins_activos(excluir_id=None):
    q = Usuario.query.filter_by(rol="admin", activo=True)
    # Contar solo dentro de la inmobiliaria del usuario actual.
    tid = getattr(current_user, "inmobiliaria_id", None)
    if getattr(current_user, "rol", None) != "superadmin" and tid is not None:
        q = q.filter(Usuario.inmobiliaria_id == tid)
    if excluir_id:
        q = q.filter(Usuario.id != excluir_id)
    return q.count()


def _usuarios_de_mi_inmobiliaria():
    """Query de usuarios de la inmobiliaria del usuario actual (superadmin: todos)."""
    q = Usuario.query
    if current_user.rol != "superadmin":
        q = q.filter(Usuario.inmobiliaria_id == current_user.inmobiliaria_id)
    return q


def _usuario_de_mi_inmobiliaria(uid):
    """Trae un usuario verificando que sea de mi inmobiliaria (o 404)."""
    u = db.session.get(Usuario, uid) or abort(404)
    if current_user.rol != "superadmin" and u.inmobiliaria_id != current_user.inmobiliaria_id:
        abort(404)
    return u


@usuarios_bp.route("/")
@login_required
@admin_required
def listar():
    usuarios = _usuarios_de_mi_inmobiliaria().order_by(
        Usuario.nombre, Usuario.username).all()
    return render_template("usuarios/list.html", usuarios=usuarios)


@usuarios_bp.route("/auditoria")
@login_required
@admin_required
def auditoria():
    """Bitácora de altas, cambios y eliminaciones (solo de tu inmobiliaria)."""
    from ..models import RegistroAuditoria
    q = request.args.get("q", "").strip()
    query = RegistroAuditoria.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(RegistroAuditoria.entidad.ilike(like),
                                    RegistroAuditoria.usuario_nombre.ilike(like),
                                    RegistroAuditoria.accion.ilike(like),
                                    RegistroAuditoria.descripcion.ilike(like)))
    registros = query.order_by(RegistroAuditoria.fecha.desc()).limit(300).all()
    return render_template("usuarios/auditoria.html", registros=registros, q=q)


@usuarios_bp.route("/cambiar-clave", methods=["GET", "POST"])
@login_required
def cambiar_clave():
    """Cada usuario cambia su propia contraseña. También se usa para forzar el
    cambio de la clave por defecto en el primer ingreso."""
    forzado = bool(getattr(current_user, "must_change_password", False))
    if request.method == "POST":
        actual = request.form.get("actual", "")
        nueva = request.form.get("nueva", "")
        repetir = request.form.get("repetir", "")
        error = None
        if not current_user.check_password(actual):
            error = "La contraseña actual no es correcta."
        elif len(nueva) < 6:
            error = "La nueva contraseña debe tener al menos 6 caracteres."
        elif nueva != repetir:
            error = "Las contraseñas nuevas no coinciden."
        elif nueva == actual:
            error = "La nueva contraseña debe ser distinta de la actual."
        if error:
            flash(error, "error")
            return render_template("usuarios/cambiar_clave.html", forzado=forzado)
        current_user.set_password(nueva)
        current_user.must_change_password = False
        db.session.commit()
        flash("Contraseña actualizada correctamente.", "ok")
        return redirect(url_for("main.index"))
    return render_template("usuarios/cambiar_clave.html", forzado=forzado)


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
        u = Usuario(username=username, nombre=nombre, rol=rol, activo=True,
                    email=request.form.get("email", "").strip(),
                    inmobiliaria_id=getattr(current_user, "inmobiliaria_id", None))
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
    u = _usuario_de_mi_inmobiliaria(uid)
    if request.method == "POST":
        nuevo_rol = request.form.get("rol", u.rol)
        activo = bool(request.form.get("activo"))
        # Proteger al último admin activo.
        quita_admin = (u.rol == "admin" and (nuevo_rol != "admin" or not activo))
        if quita_admin and _cant_admins_activos(excluir_id=u.id) == 0:
            flash("No podés dejar el sistema sin ningún administrador activo.", "error")
            return redirect(url_for("usuarios.editar", uid=u.id))
        u.nombre = request.form.get("nombre", "").strip()
        u.email = request.form.get("email", "").strip()
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
    u = _usuario_de_mi_inmobiliaria(uid)
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
