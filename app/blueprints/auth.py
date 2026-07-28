"""Autenticación: login, logout y recuperación de contraseña."""
import time

from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, current_app)
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from .. import db
from ..models import Usuario

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
# segundos, se bloquea ese usuario+IP por BLOQUEO segundos. Es en memoria
# (suficiente para una instancia chica); se reinicia al reiniciar la app.
MAX_INTENTOS = 5
VENTANA = 300        # 5 minutos
BLOQUEO = 300        # 5 minutos de espera
_intentos = {}       # clave -> [timestamps de fallos recientes]


def _clave_intento(username):
    return f"{request.remote_addr or '?'}|{(username or '').lower()}"


def _bloqueado(clave):
    ahora = time.time()
    fallos = [t for t in _intentos.get(clave, []) if ahora - t < VENTANA]
    _intentos[clave] = fallos
    if len(fallos) >= MAX_INTENTOS:
        espera = int((BLOQUEO - (ahora - fallos[-1])) / 60) + 1
        return max(espera, 1)
    return 0


def _registrar_fallo(clave):
    _intentos.setdefault(clave, []).append(time.time())


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
            _intentos.pop(clave, None)   # login exitoso: limpiar contador
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
