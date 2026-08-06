"""Autenticación: login, logout y recuperación de contraseña."""
import math
from datetime import datetime, timedelta

from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, current_app)
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from .. import db
from ..models import IntentoLogin, Usuario
from ..seguridad import validar_password

auth_bp = Blueprint("auth", __name__)

_RESET_SALT = "reset-password"
_RESET_MAX_AGE = 3600   # 1 hora
_ALTA_SALT = "verif-alta"
_ALTA_MAX_AGE = 3 * 24 * 3600   # 3 días para confirmar el email


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


def generar_token_alta(solicitud_id):
    return _serializer().dumps(solicitud_id, salt=_ALTA_SALT)


def verificar_token_alta(token):
    from ..models import SolicitudAlta
    try:
        sid = _serializer().loads(token, salt=_ALTA_SALT, max_age=_ALTA_MAX_AGE)
    except (BadSignature, SignatureExpired, Exception):
        return None
    return db.session.get(SolicitudAlta, sid)


def _email_valido(email):
    """Chequeo básico de formato (no verifica que exista; eso lo hace el enlace)."""
    if not email or email.count("@") != 1:
        return False
    local, dominio = email.split("@")
    return bool(local) and "." in dominio and not dominio.startswith(".")

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


# Freno genérico por IP para endpoints públicos (registro, recuperación), para
# frenar el abuso automatizado. Reusa la tabla IntentoLogin.
def _throttle(clave, maximo, ventana, bloqueo):
    """Minutos de espera (0 si se puede seguir). Cuenta intentos por 'clave'."""
    reg = IntentoLogin.query.filter_by(clave=clave).first()
    ahora = datetime.utcnow()
    if reg and (ahora - reg.ultimo).total_seconds() >= ventana:
        db.session.delete(reg)
        db.session.commit()
        return 0
    if reg and (reg.fallos or 0) >= maximo:
        transcurrido = (ahora - reg.ultimo).total_seconds()
        if transcurrido < bloqueo:
            return max(math.ceil((bloqueo - transcurrido) / 60), 1)
    return 0


def _throttle_contar(clave):
    reg = IntentoLogin.query.filter_by(clave=clave).first()
    if reg is None:
        reg = IntentoLogin(clave=clave, fallos=0)
        db.session.add(reg)
    reg.fallos = (reg.fallos or 0) + 1
    reg.ultimo = datetime.utcnow()
    db.session.commit()


def _throttle_publico(accion, maximo=10, ventana=3600, bloqueo=3600):
    """Aplica el freno a la acción pública actual. Devuelve minutos de espera (0 = ok).
    Desactivado en pruebas para no interferir con la batería automática."""
    import os
    if os.environ.get("TESTING"):
        return 0
    clave = f"{accion}|{request.remote_addr or '?'}"[:160]
    espera = _throttle(clave, maximo, ventana, bloqueo)
    if not espera:
        _throttle_contar(clave)
    return espera


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


@auth_bp.route("/logout", methods=["POST"])
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
        espera = _throttle_publico("registro")
        if espera:
            flash("Demasiadas solicitudes desde tu conexión. Probá de nuevo en un "
                  f"rato (unos {espera} minuto/s).", "error")
            return render_template("auth/registro.html", datos=request.form)
        nombre_inmo = request.form.get("nombre_inmobiliaria", "").strip()
        contacto = request.form.get("nombre_contacto", "").strip()
        email = request.form.get("email", "").strip()
        telefono = request.form.get("telefono", "").strip()
        localidad = request.form.get("localidad", "").strip()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        _abiertas = ("pendiente", "sin_verificar")
        error = None
        if not nombre_inmo:
            error = "El nombre de la inmobiliaria es obligatorio."
        elif not username or len(username) < 3:
            error = "Elegí un usuario de al menos 3 caracteres."
        elif not _email_valido(email):
            error = "Ingresá un email válido: te vamos a enviar un enlace para confirmarlo."
        elif Usuario.query.filter_by(username=username).first():
            error = "Ese usuario ya está en uso. Probá con otro."
        elif SolicitudAlta.query.filter(SolicitudAlta.username == username,
                                        SolicitudAlta.estado.in_(_abiertas)).first():
            error = "Ya hay una solicitud con ese usuario. Revisá tu email para confirmarla."
        elif validar_password(password):
            error = validar_password(password)
        elif password != password2:
            error = "Las contraseñas no coinciden."

        if error:
            flash(error, "error")
            return render_template("auth/registro.html", datos=request.form)

        # La solicitud nace SIN verificar; solo llega al superadmin cuando el
        # interesado confirma su email con el enlace que le enviamos.
        sol = SolicitudAlta(
            nombre_inmobiliaria=nombre_inmo, nombre_contacto=contacto,
            email=email, telefono=telefono, localidad=localidad,
            username=username, estado="sin_verificar")
        sol.set_password(password)
        db.session.add(sol)
        db.session.commit()

        from ..emailer import enviar_email
        link = url_for("auth.confirmar_registro",
                       token=generar_token_alta(sol.id), _external=True)
        enviado = enviar_email(
            email, "Confirmá tu email — FINART",
            f"Hola {contacto or nombre_inmo}:\n\n"
            f"Recibimos tu pedido de acceso a FINART. Para confirmar tu email y que "
            f"tu solicitud pase a revisión, entrá a este enlace (vence en 3 días):\n"
            f"{link}\n\nSi no pediste esto, ignorá el mensaje.")

        if enviado:
            flash("¡Casi listo! Te enviamos un email para confirmar tu dirección. "
                  "Hacé clic en el enlace y tu solicitud pasará a revisión.", "ok")
        else:
            # Sin correo saliente configurado no podríamos verificar nunca: para no
            # bloquear el alta, la solicitud pasa directo a revisión del superadmin.
            sol.estado = "pendiente"
            db.session.commit()
            flash("¡Solicitud enviada! Te vamos a habilitar el acceso a la brevedad.", "ok")
        return redirect(url_for("auth.login"))

    return render_template("auth/registro.html", datos={})


@auth_bp.route("/registro/confirmar/<token>")
def confirmar_registro(token):
    """El interesado confirma su email: la solicitud pasa de 'sin_verificar' a
    'pendiente' y recién ahí aparece en el panel del superadmin."""
    sol = verificar_token_alta(token)
    if not sol:
        flash("El enlace de confirmación no es válido o venció. Volvé a registrarte.", "error")
        return redirect(url_for("auth.registro"))
    if sol.estado == "sin_verificar":
        sol.estado = "pendiente"
        db.session.commit()
        flash("¡Email confirmado! Tu solicitud ya está en revisión. Te avisaremos "
              "cuando esté habilitada.", "ok")
    elif sol.estado == "pendiente":
        flash("Tu email ya estaba confirmado. Tu solicitud está en revisión.", "ok")
    else:
        flash("Esta solicitud ya fue procesada.", "ok")
    return redirect(url_for("auth.login"))


@auth_bp.route("/recuperar", methods=["GET", "POST"])
def recuperar():
    """Pide un enlace de recuperación. Nunca revela si el usuario existe."""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "POST":
        espera = _throttle_publico("recuperar")
        if espera:
            flash("Demasiados pedidos desde tu conexión. Probá de nuevo en un rato "
                  f"(unos {espera} minuto/s).", "error")
            return render_template("auth/recuperar.html")
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
        err = validar_password(nueva)
        if err:
            flash(err, "error")
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
