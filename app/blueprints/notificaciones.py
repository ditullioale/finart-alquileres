"""Notificaciones al portal: avisos que la inmobiliaria carga desde la app
(mora, aumento, arreglo, u otro tema libre) para uno o más inquilinos/
propietarios. Al cargarla se manda un mail con el contenido del aviso y un
link directo al portal; ni bien la persona entra al portal, la ve como un
pop-up que tiene que aceptar, y de ahí en más le queda en su historial de
notificaciones (ver app/blueprints/portal.py).
"""
from datetime import date, datetime

from flask import (Blueprint, render_template, redirect, url_for, request, flash, jsonify)
from flask_login import login_required

from .. import db
from ..models import Persona, Contrato, GasEstado, Notificacion, NotificacionDestinatario, TIPOS_NOTIFICACION
from ..calculos import deuda_real, periodos_impagos, proximo_aumento
from ..utils import MESES_ES

notificaciones_bp = Blueprint("notificaciones", __name__, url_prefix="/notificaciones")

# Ícono y color por tipo -- "chip" para las pantallas Aurora (portal), "badge"
# para las pantallas clásicas de la app (reutiliza clases .badge existentes).
_ESTILO_TIPO = {
    "Mora":    {"icono": "alert-triangle", "chip": "err",  "badge": "pendiente"},
    "Aumento": {"icono": "trending-up",    "chip": "info", "badge": "alquilado"},
    "Arreglo": {"icono": "settings",       "chip": "warn", "badge": "reservado"},
    "Otro":    {"icono": "message-circle", "chip": "acc",  "badge": "finalizado"},
}


def estilo_tipo(tipo):
    return _ESTILO_TIPO.get(tipo, _ESTILO_TIPO["Otro"])


def _money(n):
    try:
        n = float(n or 0)
    except (TypeError, ValueError):
        return str(n)
    return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _texto_datos(persona, tipo):
    """Arma, a partir de la base, un texto sugerido para el aviso -- solo con
    datos que realmente están cargados (deuda real, próximo aumento, deuda de
    gas). Para tipos sin dato asociado (Arreglo, Otro) devuelve None."""
    if tipo not in ("Mora", "Aumento"):
        return None

    contratos = (Contrato.query
                .filter_by(inquilino_id=persona.id)
                .filter(Contrato.estado == "Vigente")
                .all())
    if not contratos:
        return None

    hoy = date.today()
    partes = []

    for c in contratos:
        direccion = c.inmueble.direccion if c.inmueble else f"contrato #{c.id}"
        sim = "US$" if (c.moneda or "").lower().startswith("dol") else "$"

        if tipo == "Mora":
            deuda = deuda_real(c, hoy)
            if deuda <= 0:
                continue
            impagos = periodos_impagos(c, hoy)
            periodos_txt = ", ".join(f"{MESES_ES[p['mes']]} {p['anio']}"
                                     for p in impagos if 1 <= p['mes'] <= 12)
            linea = (f"{direccion}: alquiler actual {sim} {_money(c.precio_actual)}. "
                     f"Deuda de {sim} {_money(deuda)}"
                     + (f" ({periodos_txt})." if periodos_txt else "."))
            gas = GasEstado.query.filter_by(cuenta=c.inmueble.cuenta_gas).first() \
                if c.inmueble and c.inmueble.cuenta_gas else None
            if gas and gas.tiene_deuda and gas.deuda_total:
                linea += f" La cuenta de gas tiene una deuda de $ {_money(gas.deuda_total)}."
            partes.append(linea)

        elif tipo == "Aumento":
            prox = proximo_aumento(c, hoy)
            if not prox:
                continue
            linea = (f"{direccion}: alquiler actual {sim} {_money(c.precio_actual)}. "
                     f"Próximo aumento el {prox.strftime('%d/%m/%Y')}")
            if c.metodo_ajuste == "porcentaje" and c.porcentaje_ajuste:
                nuevo = float(c.precio_actual or 0) * (1 + float(c.porcentaje_ajuste) / 100)
                linea += f", pasaría a {sim} {_money(nuevo)} ({c.porcentaje_ajuste}%)."
            else:
                linea += "."
            partes.append(linea)

    if not partes:
        return None
    return " ".join(partes)


@notificaciones_bp.route("/datos")
@login_required
def datos():
    """JSON con un texto sugerido (armado con datos reales de la base) para
    completar el mensaje, según la persona y el tipo elegidos. Se usa desde el
    botón 'Traer datos' del formulario de nueva notificación."""
    from ..tenant import get_or_404_tenant
    pid = request.args.get("persona_id", type=int)
    tipo = request.args.get("tipo", "")
    if not pid:
        return jsonify(ok=False, motivo="Elegí un destinatario primero."), 400
    persona = get_or_404_tenant(Persona, pid)
    texto = _texto_datos(persona, tipo)
    if not texto:
        return jsonify(ok=False, motivo="No hay datos automáticos disponibles para "
                                        f"{persona.nombre} en este tipo de aviso.")
    return jsonify(ok=True, texto=texto)


@notificaciones_bp.route("/")
@login_required
def listar():
    notifs = (Notificacion.query
              .order_by(Notificacion.creada_at.desc())
              .all())
    filas = []
    for n in notifs:
        total = len(n.destinatarios)
        vistas = sum(1 for d in n.destinatarios if d.vista_at)
        filas.append({"n": n, "total": total, "vistas": vistas,
                      "estilo": estilo_tipo(n.tipo)})
    return render_template("notificaciones/list.html", filas=filas)


@notificaciones_bp.route("/nueva", methods=["GET", "POST"])
@login_required
def nueva():
    personas = (Persona.query
                .filter(db.or_(Persona.es_inquilino.is_(True), Persona.es_propietario.is_(True)))
                .order_by(Persona.nombre)
                .all())

    if request.method == "POST":
        tipo = request.form.get("tipo", "Otro")
        if tipo not in TIPOS_NOTIFICACION:
            tipo = "Otro"
        mensaje = (request.form.get("mensaje") or "").strip()
        ids = [int(x) for x in request.form.getlist("persona_id") if x.isdigit()]

        if not mensaje:
            flash("Escribí el contenido del aviso.", "error")
            return render_template("notificaciones/nueva.html", personas=personas,
                                   tipos=TIPOS_NOTIFICACION, sel=set(ids), tipo_sel=tipo,
                                   mensaje=mensaje)
        if not ids:
            flash("Elegí al menos un destinatario.", "error")
            return render_template("notificaciones/nueva.html", personas=personas,
                                   tipos=TIPOS_NOTIFICACION, sel=set(ids), tipo_sel=tipo,
                                   mensaje=mensaje)

        destinatarios = [p for p in personas if p.id in set(ids)]
        if not destinatarios:
            flash("Elegí al menos un destinatario.", "error")
            return render_template("notificaciones/nueva.html", personas=personas,
                                   tipos=TIPOS_NOTIFICACION, sel=set(ids), tipo_sel=tipo,
                                   mensaje=mensaje)

        from flask_login import current_user
        n = Notificacion(tipo=tipo, mensaje=mensaje,
                         creada_por=getattr(current_user, "username", None))
        db.session.add(n)
        db.session.flush()  # necesita n.id para los destinatarios

        sin_email = 0
        for p in destinatarios:
            d = NotificacionDestinatario(notificacion_id=n.id, persona_id=p.id)
            db.session.add(d)
            if p.email:
                enviado = _mandar_mail(p, n)
                if enviado:
                    d.mail_enviado_at = datetime.utcnow()
            else:
                sin_email += 1
        db.session.commit()

        msg = f"Notificación cargada para {len(destinatarios)} persona(s)."
        if sin_email:
            msg += (f" {sin_email} no tiene(n) email cargado: no se les pudo avisar por "
                    f"mail, pero la van a ver la próxima vez que entren al portal.")
        flash(msg, "ok")
        return redirect(url_for("notificaciones.listar"))

    persona_id = request.args.get("persona_id", type=int)
    sel = {persona_id} if persona_id else set()
    return render_template("notificaciones/nueva.html", personas=personas,
                           tipos=TIPOS_NOTIFICACION, sel=sel, tipo_sel="Otro", mensaje="")


@notificaciones_bp.route("/<int:nid>")
@login_required
def ver(nid):
    from ..tenant import get_or_404_tenant
    n = get_or_404_tenant(Notificacion, nid)
    return render_template("notificaciones/ver.html", n=n, estilo=estilo_tipo(n.tipo))


def _mandar_mail(persona, notificacion):
    """Manda el mail de aviso a `persona` con el contenido de `notificacion`.
    Devuelve True si se pudo mandar."""
    from flask import url_for as _url_for, render_template as _render_template
    from ..models import Ajustes
    from ..emailer import enviar_email  # import diferido -- monkeypatch-friendly en tests

    a = Ajustes.get()
    portal_link = _url_for("portal.acceder", _external=True)
    estilo = estilo_tipo(notificacion.tipo)

    texto = (f"Hola {persona.nombre},\n\n"
             f"Tenés una novedad en tu portal de FINART ({notificacion.tipo}):\n\n"
             f"{notificacion.mensaje}\n\n"
             f"Entrá para verla: {portal_link}\n")
    html = _render_template("email/notificacion_portal.html", nombre=persona.nombre,
                            tipo=notificacion.tipo, mensaje=notificacion.mensaje,
                            portal_link=portal_link, logo_url=(a.logo_url or None))
    return enviar_email(persona.email, f"Tenés novedades en tu portal — FINART ({notificacion.tipo})",
                        texto, html=html)
