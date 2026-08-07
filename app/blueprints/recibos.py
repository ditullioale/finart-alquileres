"""Recibos, liquidaciones y pagarés listos para imprimir (HTML → PDF navegador)."""
from datetime import date
from io import BytesIO

from flask import (Blueprint, render_template, redirect, url_for, request, flash,
                   abort, make_response, jsonify)
from flask_login import login_required
from sqlalchemy.exc import IntegrityError

from datetime import timedelta

from .. import db
from ..models import Pago, Contrato, Ajustes, ReciboManual, PagareManual
from ..utils import (pesos_letras, numero_letras, MESES_ES, parse_num,
                     parse_fecha, vencimiento)


def _venc_pago(pago):
    """Fecha de vencimiento del período del pago (o None)."""
    c = pago.contrato
    if not (c and pago.periodo_mes and pago.periodo_anio):
        return None
    return vencimiento(pago.periodo_anio, pago.periodo_mes, c.dia_vencimiento or 10)

recibos_bp = Blueprint("recibos", __name__, url_prefix="/recibos")


def _numerar(pago):
    """Le asigna el próximo número de recibo, sin repetir nunca uno.

    La base tiene un único (inmobiliaria, número de recibo): si dos pedidos
    simultáneos alcanzan a tomar el mismo número, el segundo commit falla y se
    reintenta con el siguiente, en vez de emitir dos recibos iguales."""
    a = Ajustes.get()
    for _ in range(5):
        try:
            pago.recibo_numero = a.siguiente_recibo()
            db.session.commit()
            return a
        except IntegrityError:
            db.session.rollback()
            a = Ajustes.get()
    raise RuntimeError("No pude asignar un número de recibo libre")


def _datos_recibo(pago):
    """Prepara el número de recibo y la lista de conceptos de un pago."""
    a = Ajustes.get() if pago.recibo_numero else _numerar(pago)
    conceptos = []
    if pago.mora and float(pago.mora) > 0:
        conceptos.append(("Mora", float(pago.mora)))
    for g in pago.gastos:
        conceptos.append((g.descripcion, float(g.monto)))
    return a, conceptos


@recibos_bp.route("/pago/<int:pid>")
@login_required
def recibo(pid):
    pago = db.session.get(Pago, pid) or abort(404)
    a, conceptos = _datos_recibo(pago)
    return render_template("recibos/recibo.html", pago=pago, c=pago.contrato, a=a,
                           conceptos=conceptos, meses=MESES_ES, venc=_venc_pago(pago),
                           total_letras=pesos_letras(pago.total or 0),
                           hoy=date.today())


def _recibo_pdf_bytes(pago):
    """Genera el recibo en PDF y devuelve (bytes, nombre_archivo)."""
    from xhtml2pdf import pisa
    a, conceptos = _datos_recibo(pago)
    html = render_template("recibos/recibo_pdf.html", pago=pago, c=pago.contrato, a=a,
                           conceptos=conceptos, meses=MESES_ES, venc=_venc_pago(pago),
                           total_letras=pesos_letras(pago.total or 0),
                           hoy=date.today())
    buf = BytesIO()
    pisa.CreatePDF(html, dest=buf, encoding="utf-8")
    buf.seek(0)
    inq = (pago.contrato.inquilino.nombre if pago.contrato and pago.contrato.inquilino
           else "inquilino")
    inq = "".join(ch if ch.isalnum() else "_" for ch in inq)
    nombre = f"Recibo_{(pago.recibo_numero or pago.id)}_{inq}.pdf".replace("__", "_")
    return buf.read(), nombre


@recibos_bp.route("/pago/<int:pid>/pdf")
@login_required
def recibo_pdf(pid):
    """Genera el recibo en PDF (para descargar y enviar por WhatsApp/mail)."""
    pago = db.session.get(Pago, pid) or abort(404)
    datos, nombre = _recibo_pdf_bytes(pago)
    resp = make_response(datos)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return resp


@recibos_bp.route("/pago/<int:pid>/email", methods=["POST"])
@login_required
def recibo_email(pid):
    """Envía el recibo (PDF adjunto) por email al inquilino. Si no tiene email cargado,
    devuelve need_email para que la UI lo pida; si viene un email nuevo, lo guarda."""
    from ..emailer import enviar_email
    pago = db.session.get(Pago, pid) or abort(404)
    contrato = pago.contrato
    inq = contrato.inquilino if contrato else None
    d = request.get_json(silent=True) or {}
    email = ((d.get("email") or "").strip()
             or ((inq.email or "").strip() if inq else ""))
    if not email:
        return jsonify(ok=False, need_email=True,
                       mensaje="El inquilino no tiene email cargado."), 200
    from ..blueprints.auth import _email_valido
    if not _email_valido(email):
        return jsonify(ok=False, error="El email no parece válido."), 200
    # Guardar el email en el inquilino si es nuevo o cambió.
    if inq and inq.email != email:
        inq.email = email
        db.session.commit()

    datos, nombre = _recibo_pdf_bytes(pago)
    a = Ajustes.get()
    inmo = (a.nombre if a and a.nombre else "la inmobiliaria")
    nombre_inq = (inq.nombre if inq else "")
    periodo = f"{MESES_ES[pago.periodo_mes]} {pago.periodo_anio}" if pago.periodo_mes else ""
    cuerpo = (f"Hola {nombre_inq}!\n\nTe adjuntamos el recibo del alquiler"
              + (f" correspondiente a {periodo}" if periodo else "")
              + (f" de {contrato.inmueble.direccion}" if contrato and contrato.inmueble else "")
              + f".\n\nSaludos,\n{inmo}")
    enviado = enviar_email(email, f"Recibo de alquiler{(' - ' + periodo) if periodo else ''}",
                           cuerpo, adjunto=(nombre, datos, "application/pdf"))
    if enviado:
        return jsonify(ok=True, email=email,
                       mensaje=f"Recibo enviado a {email}."), 200
    return jsonify(ok=False,
                   error="No se pudo enviar el email (revisá la configuración de correo "
                         "del servidor).", email=email), 200


@recibos_bp.route("/liquidacion/pago/<int:pid>")
@login_required
def liquidacion(pid):
    pago = db.session.get(Pago, pid) or abort(404)
    a = Ajustes.get()
    from ..utils import q2
    from decimal import Decimal
    inm = pago.contrato.inmueble
    alquiler = q2(pago.precio_alquiler)
    if pago.contrato.comision_pct is not None:
        pct = float(pago.contrato.comision_pct)
    else:
        pct = float(inm.comision_pct or 0) if inm else 0
    comision = q2(alquiler * q2(pct) / Decimal(100))
    neto = alquiler - comision
    alquiler = float(alquiler); comision = float(comision); neto = float(neto)
    return render_template("recibos/liquidacion.html", pago=pago, c=pago.contrato, a=a,
                           alquiler=alquiler, pct=pct, comision=comision, neto=neto,
                           neto_letras=pesos_letras(neto), meses=MESES_ES, hoy=date.today())


# --------------------------------------------------------------------------- #
#  Recibos manuales (cobros fuera del circuito de alquileres)
# --------------------------------------------------------------------------- #
FORMAS_PAGO = ["Efectivo", "Transferencia", "Cheque", "Otro"]


def _parse_conceptos(texto):
    """Convierte líneas 'descripcion | monto' en lista [(desc, monto)]."""
    items = []
    for linea in (texto or "").splitlines():
        if "|" in linea:
            desc, monto = linea.rsplit("|", 1)
            m = parse_num(monto)
            if desc.strip() and m is not None:
                items.append((desc.strip(), m))
    return items


@recibos_bp.route("/manuales")
@login_required
def manuales():
    q = request.args.get("q", "").strip()
    query = ReciboManual.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(ReciboManual.cliente.ilike(like),
                                    ReciboManual.numero.ilike(like),
                                    ReciboManual.concepto_general.ilike(like)))
    recibos = query.order_by(ReciboManual.id.desc()).limit(200).all()
    return render_template("recibos/manuales_list.html", recibos=recibos, q=q)


@recibos_bp.route("/manuales/nuevo", methods=["GET", "POST"])
@login_required
def manual_nuevo():
    if request.method == "POST":
        descs = request.form.getlist("concepto_desc")
        montos = request.form.getlist("concepto_monto")
        lineas, total = [], 0.0
        conceptos = []   # para redibujar el formulario si hay un error
        for i, desc in enumerate(descs):
            monto_txt = montos[i] if i < len(montos) else ""
            if desc.strip() or (monto_txt or "").strip():
                conceptos.append({"desc": desc.strip(), "monto": monto_txt})
            m = parse_num(monto_txt)
            if desc.strip() and m is not None:
                lineas.append(f"{desc.strip()} | {m}")
                total += m
        cliente = request.form.get("cliente", "").strip()

        def _volver_con_error(msg):
            flash(msg, "error")
            return render_template("recibos/manual_form.html", formas=FORMAS_PAGO,
                                   hoy=date.today(), datos=request.form,
                                   conceptos=conceptos)
        if not cliente:
            return _volver_con_error("Indicá el nombre del cliente.")
        if not lineas:
            return _volver_con_error("Agregá al menos un concepto con su monto "
                                     "(la descripción y el importe).")
        a = Ajustes.get()
        r = ReciboManual(
            numero=a.siguiente_recibo(),
            fecha=parse_fecha(request.form.get("fecha")) or date.today(),
            cliente=cliente,
            cliente_dni=request.form.get("cliente_dni", "").strip(),
            cliente_domicilio=request.form.get("cliente_domicilio", "").strip(),
            concepto_general=request.form.get("concepto_general", "").strip(),
            detalle="\n".join(lineas),
            total=round(total, 2),
            moneda=request.form.get("moneda", "Pesos"),
            forma_pago=request.form.get("forma_pago", ""),
            observaciones=request.form.get("observaciones", "").strip(),
        )
        db.session.add(r)
        db.session.commit()
        flash(f"Recibo {r.numero} creado.", "ok")
        return redirect(url_for("recibos.manual_ver", rid=r.id))
    return render_template("recibos/manual_form.html", formas=FORMAS_PAGO, hoy=date.today())


@recibos_bp.route("/manuales/<int:rid>")
@login_required
def manual_ver(rid):
    r = db.session.get(ReciboManual, rid) or abort(404)
    a = Ajustes.get()
    conceptos = _parse_conceptos(r.detalle)
    return render_template("recibos/manual_ver.html", r=r, a=a, conceptos=conceptos,
                           total_letras=pesos_letras(r.total or 0))


@recibos_bp.route("/manuales/<int:rid>/eliminar", methods=["POST"])
@login_required
def manual_eliminar(rid):
    r = db.session.get(ReciboManual, rid) or abort(404)
    db.session.delete(r)
    db.session.commit()
    flash("Recibo manual eliminado.", "ok")
    return redirect(url_for("recibos.manuales"))


# --------------------------------------------------------------------------- #
#  Pagarés manuales (sueltos, sin contrato)
# --------------------------------------------------------------------------- #
@recibos_bp.route("/pagares-manuales")
@login_required
def pagares_manuales():
    q = request.args.get("q", "").strip()
    query = PagareManual.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(PagareManual.deudor.ilike(like),
                                    PagareManual.beneficiario.ilike(like),
                                    PagareManual.concepto.ilike(like)))
    pagares = query.order_by(PagareManual.id.desc()).limit(200).all()
    return render_template("recibos/pagares_manuales_list.html", pagares=pagares, q=q)


@recibos_bp.route("/pagares-manuales/nuevo", methods=["GET", "POST"])
@login_required
def pagare_manual_nuevo():
    a = Ajustes.get()
    if request.method == "POST":
        deudor = request.form.get("deudor", "").strip()
        monto = parse_num(request.form.get("monto"))
        if not deudor or not monto:
            flash("Completá el deudor y el monto.", "error")
            return render_template("recibos/pagare_manual_form.html", a=a, hoy=date.today())
        pm = PagareManual(
            fecha=parse_fecha(request.form.get("fecha")) or date.today(),
            lugar=request.form.get("lugar", "").strip() or (a.pagare_lugar or a.localidad or ""),
            beneficiario=request.form.get("beneficiario", "").strip() or a.nombre,
            deudor=deudor,
            deudor_dni=request.form.get("deudor_dni", "").strip(),
            deudor_domicilio=request.form.get("deudor_domicilio", "").strip(),
            monto=monto,
            moneda=request.form.get("moneda", "Pesos"),
            cantidad=parse_num(request.form.get("cantidad"), entero=True) or 1,
            primer_venc=parse_fecha(request.form.get("primer_venc")),
            cada_dias=parse_num(request.form.get("cada_dias"), entero=True) or 30,
            concepto=request.form.get("concepto", "").strip(),
        )
        db.session.add(pm)
        db.session.commit()
        flash("Pagaré(s) generado(s).", "ok")
        return redirect(url_for("recibos.pagare_manual_ver", pmid=pm.id))
    return render_template("recibos/pagare_manual_form.html", a=a, hoy=date.today())


@recibos_bp.route("/pagares-manuales/<int:pmid>")
@login_required
def pagare_manual_ver(pmid):
    pm = db.session.get(PagareManual, pmid) or abort(404)
    # Construir la lista de pagarés con su vencimiento.
    pagares = []
    for i in range(pm.cantidad or 1):
        if pm.primer_venc:
            venc = pm.primer_venc + timedelta(days=(pm.cada_dias or 30) * i)
            venc_txt = venc.strftime("%d/%m/%Y")
        else:
            venc_txt = "a la vista"
        pagares.append({"n": i + 1, "venc": venc_txt})
    return render_template("recibos/pagare_manual_ver.html", pm=pm, pagares=pagares,
                           monto_letras=pesos_letras(pm.monto or 0))


@recibos_bp.route("/pagares-manuales/<int:pmid>/eliminar", methods=["POST"])
@login_required
def pagare_manual_eliminar(pmid):
    pm = db.session.get(PagareManual, pmid) or abort(404)
    db.session.delete(pm)
    db.session.commit()
    flash("Pagaré manual eliminado.", "ok")
    return redirect(url_for("recibos.pagares_manuales"))


@recibos_bp.route("/pagares/contrato/<int:cid>")
@login_required
def pagares(cid):
    c = db.session.get(Contrato, cid) or abort(404)
    a = Ajustes.get()
    meses = request.args.get("meses", type=int) or a.pagare_meses or 10
    lugar = a.pagare_lugar or a.localidad or c.inmueble.localidad or ""
    monto = float(c.precio_actual or c.precio_inicial or 0) * meses
    return render_template("recibos/pagares.html", c=c, a=a, fiadores=c.fiadores,
                           meses_pagare=meses, lugar=lugar, monto=monto,
                           monto_letras=pesos_letras(monto), meses_num=numero_letras(meses),
                           hoy=date.today())
