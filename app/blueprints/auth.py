"""Autenticación: login y logout."""
import time

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user

from ..models import Usuario

auth_bp = Blueprint("auth", __name__)

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
            return redirect(request.args.get("next") or url_for("main.index"))
        _registrar_fallo(clave)
        flash("Usuario o contraseña incorrectos.", "error")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
