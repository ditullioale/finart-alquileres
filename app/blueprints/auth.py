"""Autenticación: login, logout y recuperación de contraseña."""
import math
from datetime import datetime, timedelta

from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, current_app)
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from .. import db
from ..models import IntentoLogin, Usuario

auth_bp = Blueprint("auth", __name__)

_RESET_SALT = "reset-password"
_RESET_MAX_AGE = 3600   # 1 hora


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def generar_token_reset(user_id):
    return _serializer().dumps(user_id, salt=_RESET_SALT)


def verificar_token_reset(token):
    try:
        uid = _serializer().loads(token, salt=_RESET_SALT, max_age=_RESET_MAX_AGE)
    except (BadSignature, SignatureExpired, Exception):
        return None
    return db.session.get(Usuario, uid)

# Límite de intentos de login. Tras MAX_INTENTOS fallidos dentro de VENTANA
# segundos, se bloquea ese usuario+IP por BLOQUEO segundos. El contador se
# guarda en la base para que valga en todos los workers del servidor y no se
# borre al reiniciar (en memoria, cada worker tenía su propio contador).
MAX_INTENTOS = 5
VENTANA = 300        # 5 minutos
BLOQUEO = 300        # 5 minutos de espera


def _clave_intento(username):
    return f"{request.remote_addr or '?'}|{(username or '').lower()}"[:160]


def _bloqueado(clave):
    """Minutos que faltan para poder reintentar (0 si no está bloqueado)."""
    reg = IntentoLogin.query.filter_by(clave=clave).first()
    if reg is None:
        return 0
    transcurrido = (datetime.utcnow() - reg.ultimo).total_seconds()
    if transcurrido >= VENTANA:
        db.session.delete(reg)      # los fallos viejos caducan
        db.session.commit()
        return 0
    if reg.fallos < MAX_INTENTOS:
        return 0
    return max(math.ceil((BLOQUEO - transcurrido) / 60), 1)


def _registrar_fallo(clave):
    reg = IntentoLogin.query.filter_by(clave=clave).first()
    if reg is None:
        reg = IntentoLogin(clave=clave, fallos=0)
        db.session.add(reg)
    reg.fallos = (reg.fallos or 0) + 1
    reg.ultimo = datetime.utcnow()
    _purgar_intentos_viejos()
    db.session.commit()


def _olvidar_fallos(clave):
    IntentoLogin.query.filter_by(clave=clave).delete()
    db.session.commit()


def _purgar_intentos_viejos():
    limite = datetime.utcnow() - timedelta(seconds=VENTANA)
    IntentoLogin.query.filter(IntentoLogin.ultimo < limite).delete()


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        clave = _clave_intento(username)
        espera = _bloqueado(clave)
        if espera:
            flash(f"Demasiados intentos fallidos. Esperá unos {espera} minuto(s) "
                  "e intentá de nuevo.", "error")
            return render_template("auth/login.html")
        usuario = Usuario.query.filter_by(username=username).first()
        if usuario and usuario.activo and usuario.check_password(password):
            _olvidar_fallos(clave)
            login_user(usuario)
            destino = request.args.get("next")
            if not destino and usuario.rol == "superadmin":
                destino = url_for("plataforma.index")
            return redirect(destino or url_for("main.index"))
        _registrar_fallo(clave)
        flash("Usuario o contraseña incorrectos.", "error")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/registro", methods=["GET", "POST"])
def registro():
    """Alta autogestionada: una inmobiliaria pide acceso. Queda pendiente hasta
    que el superadmin la aprueba. No crea nada activo por sí sola."""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    from ..models import SolicitudAlta

    if request.method == "POST":
        nombre_inmo = request.form.get("nombre_inmobiliaria", "").strip()
        contacto = request.form.get("nombre_contacto", "").strip()
        email = request.form.get("email", "").strip()
        telefono = request.form.get("telefono", "").strip()
        localidad = request.form.get("localidad", "").strip()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        error = None
        if not nombre_inmo:
            error = "El nombre de la inmobiliaria es obligatorio."
        elif not username or len(username) < 3:
            error = "Elegí un usuario de al menos 3 caracteres."
        elif Usuario.query.filter_by(username=username).first():
            error = "Ese usuario ya está en uso. Probá con otro."
        elif SolicitudAlta.query.filter_by(username=username, estado="pendiente").first():
            error = "Ya hay una solicitud pendiente con ese usuario."
        elif len(password) < 6:
            error = "La contraseña debe tener al menos 6 caracteres."
        elif password != password2:
            error = "Las contraseñas no coinciden."

        if error:
            flash(error, "error")
            return render_template("auth/registro.html", datos=request.form)

        sol = SolicitudAlta(
            nombre_inmobiliaria=nombre_inmo, nombre_contacto=contacto,
            email=email, telefono=telefono, localidad=localidad,
            username=username, estado="pendiente")
        sol.set_password(password)
        db.session.add(sol)
        db.session.commit()
        flash("¡Solicitud enviada! Te vamos a habilitar el acceso a la brevedad. "
              "Después vas a poder ingresar con el usuario y contraseña que elegiste.", "ok")
        return redirect(url_for("auth.login"))

    return render_template("auth/registro.html", datos={})


@auth_bp.route("/recuperar", methods=["GET", "POST"])
def recuperar():
    """Pide un enlace de recuperación. Nunca revela si el usuario existe."""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "POST":
        ident = request.form.get("ident", "").strip()
        usuario = (Usuario.query.filter(db.or_(Usuario.username == ident.lower(),
                                               Usuario.email == ident)).first()
                   if ident else None)
        if usuario and usuario.activo and getattr(usuario, "email", None):
            from ..emailer import enviar_email
            link = url_for("auth.restablecer",
                           token=generar_token_reset(usuario.id), _external=True)
            enviar_email(usuario.email, "Recuperar contraseña — Gestión de Alquileres",
                         f"Hola {usuario.nombre or usuario.username}:\n\n"
                         f"Para elegir una nueva contraseña, entrá a este enlace "
                         f"(vence en 1 hora):\n{link}\n\n"
                         f"Si no pediste esto, ignorá el mensaje.")
        flash("Si el usuario existe y tiene email cargado, te enviamos un enlace "
              "para restablecer la contraseña.", "ok")
        return redirect(url_for("auth.login"))
    return render_template("auth/recuperar.html")


@auth_bp.route("/restablecer/<token>", methods=["GET", "POST"])
def restablecer(token):
    usuario = verificar_token_reset(token)
    if not usuario:
        flash("El enlace no es válido o venció. Pedí uno nuevo.", "error")
        return redirect(url_for("auth.recuperar"))
    if request.method == "POST":
        nueva = request.form.get("nueva", "")
        repetir = request.form.get("repetir", "")
        if len(nueva) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "error")
            return render_template("auth/restablecer.html", token=token)
        if nueva != repetir:
            flash("Las contraseñas no coinciden.", "error")
            return render_template("auth/restablecer.html", token=token)
        usuario.set_password(nueva)
        usuario.must_change_password = False
        db.session.commit()
        flash("Contraseña actualizada. Ya podés iniciar sesión.", "ok")
        return redirect(url_for("auth.login"))
    return render_template("auth/restablecer.html", token=token)
