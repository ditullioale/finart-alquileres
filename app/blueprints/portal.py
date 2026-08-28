"""Portal de autoservicio para inquilinos y propietarios (sin usuario de staff).

Acceso sin contraseña: la persona ingresa su email, le llega un enlace de un
solo uso (magic link) válido por 20 minutos, y al abrirlo queda "adentro" de
este portal -- una sesión propia (``session['portal_email']``), completamente
aparte del login de personal (Usuario / flask_login) que usa el resto del
sistema. Nunca se cruzan: quien entra por acá nunca ve el panel de gestión, y
un operador nunca entra por este camino.

Todo lo que se muestra sale de buscar, por email, las Personas (inquilino y/o
propietario) que coincidan -- en cualquier inmobiliaria del sistema, porque
una misma persona puede alquilar con más de una agencia -- y armar, para cada
contrato donde participa, un resumen de solo lectura: rol, próximo aumento,
deuda, últimos pagos y estado de la cuenta de gas del inmueble. No hay ninguna
acción de escritura acá: es consulta pura.
"""
from datetime import date
from functools import wraps

from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, current_app, session, abort, make_response)
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.orm import joinedload

from .. import db
from ..models import Persona, Contrato, Pago, GasEstado
from ..calculos import proximo_aumento, deuda_real
from ..utils import MESES_ES

portal_bp = Blueprint("portal", __name__, url_prefix="/portal")

_SALT = "portal-login"
_MAX_AGE = 20 * 60  # 20 minutos: bastante para abrir el mail, poco para que un
                    # enlace viejo dando vueltas en una bandeja siga sirviendo.


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def _email_valido(email):
    """Chequeo básico de formato (no confirma que exista; eso lo hace el enlace)."""
    if not email or email.count("@") != 1:
        return False
    local, dominio = email.split("@")
    return bool(local) and "." in dominio and not dominio.startswith(".")


def _personas_del_email(email):
    """Personas (inquilino y/o propietario, en cualquier inmobiliaria) con ese
    email. Vacía la lista si no hay ninguna -- nunca revela por sí sola si el
    email existe (eso lo decide quien llama, con el mensaje que muestra)."""
    email = (email or "").strip().lower()
    if not email:
        return []
    return (Persona.query
            .filter(db.func.lower(Persona.email) == email)
            .filter(db.or_(Persona.es_inquilino.is_(True),
                           Persona.es_propietario.is_(True)))
            .all())


def _contratos_de(personas):
    """Contratos donde alguna de estas personas es inquilino o propietario
    titular, sin duplicar, vigentes primero y luego por fecha de inicio."""
    ids = [p.id for p in personas]
    if not ids:
        return []
    return (Contrato.query
            .filter(db.or_(Contrato.inquilino_id.in_(ids),
                           Contrato.propietario_id.in_(ids)))
            .options(joinedload(Contrato.inmueble),
                     joinedload(Contrato.pagos),
                     joinedload(Contrato.aumentos))
            .order_by((Contrato.estado != "Vigente"), Contrato.fecha_inicio.desc())
            .all())


def _sesion_activa():
    """(email, personas) de la sesión de portal actual, o (None, []) si no hay
    ninguna vigente. Si la persona fue borrada o cambió de email desde que
    entró, se cierra la sesión en vez de mostrar un portal vacío sin
    explicación."""
    email = session.get("portal_email")
    if not email:
        return None, []
    personas = _personas_del_email(email)
    if not personas:
        session.pop("portal_email", None)
        return None, []
    return email, personas


def portal_login_required(f):
    @wraps(f)
    def envoltorio(*args, **kwargs):
        email, personas = _sesion_activa()
        if not email:
            flash("Tu sesión venció o no iniciaste sesión. Pedí un nuevo enlace.", "error")
            return redirect(url_for("portal.acceder"))
        return f(email, personas, *args, **kwargs)
    return envoltorio


@portal_bp.route("/acceder", methods=["GET", "POST"])
def acceder():
    email, _ = _sesion_activa()
    if email:
        return redirect(url_for("portal.panel"))

    if request.method == "POST":
        from .auth import _throttle_publico
        ingresado = request.form.get("email", "").strip()
        espera = _throttle_publico("portal_acceder", maximo=6)
        if espera:
            flash(f"Demasiados pedidos desde tu conexión. Probá de nuevo en unos "
                  f"{espera} minuto(s).", "error")
            return render_template("aurora/portal/acceder.html")
        if not _email_valido(ingresado):
            flash("Ingresá un email válido.", "error")
            return render_template("aurora/portal/acceder.html", email=ingresado)

        if _personas_del_email(ingresado):
            from ..emailer import enviar_email
            token = _serializer().dumps(ingresado.lower(), salt=_SALT)
            link = url_for("portal.verificar", token=token, _external=True)
            enviar_email(
                ingresado, "Tu acceso al portal — FINART",
                f"Hola!\n\nEntrá a este enlace para ver tus recibos, tu contrato y "
                f"tus próximos vencimientos (vence en 20 minutos):\n{link}\n\n"
                f"Si no lo pediste vos, ignorá este mensaje.")
        # Mismo mensaje exista o no el email: no revela si alguien figura como
        # inquilino o propietario en el sistema.
        flash("Si ese email está registrado como inquilino o propietario, te "
              "enviamos un enlace de acceso. Revisá tu casilla (y spam).", "ok")
        return redirect(url_for("portal.acceder"))

    return render_template("aurora/portal/acceder.html")


@portal_bp.route("/verificar/<token>")
def verificar(token):
    try:
        email = _serializer().loads(token, salt=_SALT, max_age=_MAX_AGE)
    except SignatureExpired:
        flash("Ese enlace venció. Pedí uno nuevo.", "error")
        return redirect(url_for("portal.acceder"))
    except (BadSignature, Exception):
        flash("Ese enlace no es válido.", "error")
        return redirect(url_for("portal.acceder"))

    if not _personas_del_email(email):
        flash("No encontramos una cuenta activa con ese email.", "error")
        return redirect(url_for("portal.acceder"))

    session.clear()
    session["portal_email"] = email
    return redirect(url_for("portal.panel"))


@portal_bp.route("/salir", methods=["POST"])
def salir():
    session.pop("portal_email", None)
    return redirect(url_for("portal.acceder"))


@portal_bp.route("/")
@portal_login_required
def panel(email, personas):
    hoy = date.today()
    ids = {p.id for p in personas}
    contratos = _contratos_de(personas)

    items = []
    for c in contratos:
        rol = []
        if c.inquilino_id in ids:
            rol.append("Inquilino")
        if c.propietario_id in ids:
            rol.append("Propietario")

        ultimos_pagos = sorted(
            c.pagos, key=lambda p: (p.periodo_anio or 0, p.periodo_mes or 0),
            reverse=True)[:6]

        gas = None
        if c.inmueble and c.inmueble.cuenta_gas:
            gas = GasEstado.query.filter_by(cuenta=c.inmueble.cuenta_gas).first()

        items.append({
            "contrato": c,
            "rol": " / ".join(rol) or "—",
            "direccion": c.inmueble.direccion if c.inmueble else "—",
            "proximo_aumento": proximo_aumento(c, hoy),
            "deuda": round(deuda_real(c, hoy), 2),
            "pagos": ultimos_pagos,
            "gas": gas,
        })

    nombre = personas[0].nombre if personas else email
    return render_template("aurora/portal/panel.html", nombre=nombre, email=email,
                           items=items, meses=MESES_ES, hoy=hoy)


@portal_bp.route("/recibo/<int:pid>/pdf")
@portal_login_required
def recibo_pdf(email, personas, pid):
    """PDF del recibo -- solo si el pago pertenece a un contrato donde esta
    persona (por email) es inquilino o propietario. Cualquier otro caso, 404
    (no 403: no hace falta confirmarle a nadie que el recibo existe)."""
    pago = db.session.get(Pago, pid)
    if not pago:
        abort(404)
    ids = {p.id for p in personas}
    c = pago.contrato
    if not c or (c.inquilino_id not in ids and c.propietario_id not in ids):
        abort(404)

    from .recibos import _recibo_pdf_bytes
    datos, nombre_archivo = _recibo_pdf_bytes(pago)
    resp = make_response(datos)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'attachment; filename="{nombre_archivo}"'
    return resp
