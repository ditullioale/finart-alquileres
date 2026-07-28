"""Registro de cobros: pagos, mora, gastos extras, historial y deuda."""
from datetime import date

from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, abort, jsonify, make_response)
from flask_login import login_required
from sqlalchemy.orm import joinedload, selectinload

from .. import db
from ..models import Contrato, Pago, GastoExtra
from ..utils import (parse_fecha, parse_num, vencimiento, calcular_mora,
                     periodo_siguiente, MESES_ES, link_whatsapp, whatsapp_valido, q2)

cobros_bp = Blueprint("cobros", __name__, url_prefix="/cobros")

FORMAS_PAGO = ["Efectivo", "Transferencia", "Transferencia prop / inmo", "Cheque", "Otro"]


# --------------------------------------------------------------------------- #
#  Helpers de resumen
# --------------------------------------------------------------------------- #
def _resumen(contrato):
    pagos = sorted(contrato.pagos, key=lambda p: (p.periodo_anio or 0, p.periodo_mes or 0))
    deuda = sum(float(p.saldo or 0) for p in contrato.pagos)
    if pagos:
        ult = pagos[-1]
        mes, anio = periodo_siguiente(ult.periodo_mes or 1, ult.periodo_anio or date.today().year)
        nro = (max((p.numero or 0) for p in contrato.pagos)) + 1
    else:
        fi = contrato.fecha_inicio or date.today()
        mes, anio, nro = fi.month, fi.year, 1
    prox_vto = vencimiento(anio, mes, contrato.dia_vencimiento or 10)
    return dict(deuda=deuda, prox_mes=mes, prox_anio=anio, prox_nro=nro,
                prox_vto=prox_vto, monto_prox=float(contrato.precio_actual or contrato.precio_inicial or 0))


def _leer_gastos(pago):
    pago.gastos.clear()
    descs = request.form.getlist("gasto_desc")
    montos = request.form.getlist("gasto_monto")
    total = 0.0
    for i, desc in enumerate(descs):
        monto = parse_num(montos[i]) if i < len(montos) else None
        if desc.strip() and monto is not None:
            pago.gastos.append(GastoExtra(descripcion=desc.strip(), monto=monto))
            total += monto
    return total


def _estado_saldo(pago):
    """Recalcula saldo y estado a partir del total y lo pagado (decimal exacto)."""
    total = q2(pago.total)
    pagado = q2(pago.pagado)
    pago.saldo = total - pagado
    if pagado <= 0:
        pago.estado = "Pendiente"
    elif pago.saldo > 0:
        pago.estado = "Parcial"
    else:
        pago.estado = "Pagado"


def _recalcular(pago, gastos_total):
    pago.total = q2(pago.precio_alquiler) + q2(pago.mora) + q2(gastos_total)
    _estado_saldo(pago)


def _deuda_previa(contrato, excluir_id=None):
    """Suma de saldos pendientes de otros pagos del contrato."""
    return sum(float(p.saldo or 0) for p in contrato.pagos
               if (p.saldo or 0) > 0 and p.id != excluir_id)


# --------------------------------------------------------------------------- #
#  Panel de cobranzas del mes
# --------------------------------------------------------------------------- #
@cobros_bp.route("/")
@login_required
def index():
    hoy = date.today()
    mes = parse_num(request.args.get("mes"), entero=True) or hoy.month
    anio = parse_num(request.args.get("anio"), entero=True) or hoy.year
    filtro = request.args.get("f", "")  # "", "pendiente", "cobrado"
    q = request.args.get("q", "").strip().lower()

    filas = []
    tot_esperado = tot_cobrado = tot_pendiente = 0.0
    contratos = (Contrato.query.filter_by(estado="Vigente")
                 .options(joinedload(Contrato.inquilino),
                          joinedload(Contrato.propietario),
                          joinedload(Contrato.inmueble),
                          selectinload(Contrato.pagos))
                 .all())
    for c in contratos:
        if q:
            campos = " ".join(filter(None, [
                c.inmueble.codigo if c.inmueble else "",
                c.inmueble.direccion if c.inmueble else "",
                c.inquilino.nombre if c.inquilino else "",
                c.propietario.nombre if c.propietario else "",
            ])).lower()
            if q not in campos:
                continue
        # ¿el contrato ya arrancó y no terminó en ese período?
        pago = next((p for p in c.pagos
                     if p.periodo_mes == mes and p.periodo_anio == anio), None)
        esperado = float(c.precio_actual or c.precio_inicial or 0)
        if pago:
            estado = pago.estado
            cobrado = float(pago.pagado or 0)
            saldo = float(pago.saldo or 0)
        else:
            estado = "Sin registrar"
            cobrado = 0.0
            saldo = esperado
        tot_esperado += esperado
        tot_cobrado += cobrado
        if estado != "Pagado":
            tot_pendiente += saldo
        prox_nro = (max((p.numero or 0) for p in c.pagos) + 1) if c.pagos else 1
        venc = vencimiento(anio, mes, c.dia_vencimiento or 10)
        filas.append(dict(c=c, pago=pago, esperado=esperado, estado=estado,
                          cobrado=cobrado, saldo=saldo, prox_nro=prox_nro,
                          venc=venc))

    if filtro == "pendiente":
        filas = [f for f in filas if f["estado"] not in ("Pagado",)]
    elif filtro == "cobrado":
        filas = [f for f in filas if f["estado"] == "Pagado"]

    sort = request.args.get("sort", "")
    rev = request.args.get("dir", "asc") == "desc"
    claves = {
        "inquilino": lambda f: (f["c"].inquilino.nombre if f["c"].inquilino else "").lower(),
        "inmueble": lambda f: (f["c"].inmueble.direccion or "").lower(),
        "esperado": lambda f: f["esperado"],
        "cobrado": lambda f: f["cobrado"],
        "estado": lambda f: f["estado"],
    }
    if sort in claves:
        filas.sort(key=claves[sort], reverse=rev)
    else:
        filas.sort(key=lambda f: (f["estado"] == "Pagado",
                                  (f["c"].inquilino.nombre if f["c"].inquilino else "")))

    return render_template("cobros/index.html", filas=filas, mes=mes, anio=anio,
                           filtro=filtro, meses=MESES_ES, formas=FORMAS_PAGO, hoy=hoy,
                           totales=dict(esperado=tot_esperado, cobrado=tot_cobrado,
                                        pendiente=tot_pendiente),
                           anios=list(range(hoy.year - 4, hoy.year + 2)))


@cobros_bp.route("/react")
@login_required
def react():
    """Versión nueva del panel de cobranzas, renderizada con React (Sprint 1).
    Convive con la versión clásica en '/' para poder validarla sin riesgo."""
    hoy = date.today()
    mes = parse_num(request.args.get("mes"), entero=True) or hoy.month
    anio = parse_num(request.args.get("anio"), entero=True) or hoy.year
    return render_template("cobros/react.html", mes=mes, anio=anio)


# --------------------------------------------------------------------------- #
#  Detalle de pagos por contrato
# --------------------------------------------------------------------------- #
@cobros_bp.route("/exportar")
@login_required
def exportar():
    """Exporta el panel de cobranzas del mes a Excel."""
    import pandas as pd
    from io import BytesIO
    hoy = date.today()
    mes = parse_num(request.args.get("mes"), entero=True) or hoy.month
    anio = parse_num(request.args.get("anio"), entero=True) or hoy.year
    filas = []
    tot_esp = tot_cob = tot_saldo = 0.0
    for c in Contrato.query.filter_by(estado="Vigente").all():
        pago = next((p for p in c.pagos
                     if p.periodo_mes == mes and p.periodo_anio == anio), None)
        esperado = float(c.precio_actual or c.precio_inicial or 0)
        estado = pago.estado if pago else "Sin cobrar"
        cobrado = float(pago.pagado or 0) if pago else 0.0
        saldo = float(pago.saldo or 0) if pago else esperado
        tot_esp += esperado; tot_cob += cobrado
        if estado != "Pagado":
            tot_saldo += saldo
        filas.append({
            "Inquilino": c.inquilino.nombre if c.inquilino else "",
            "Inmueble": c.inmueble.direccion if c.inmueble else "",
            "Localidad": (c.inmueble.localidad if c.inmueble else "") or "",
            "Propietario": c.propietario.nombre if c.propietario else "",
            "A cobrar": esperado, "Cobrado": cobrado, "Saldo": saldo,
            "Estado": estado, "Forma de pago": (pago.forma_pago if pago else ""),
            "Fecha de pago": (pago.fecha_pago.strftime("%d/%m/%Y")
                              if pago and pago.fecha_pago else ""),
        })
    filas.append({"Inquilino": "TOTALES", "A cobrar": tot_esp,
                  "Cobrado": tot_cob, "Saldo": tot_saldo})
    df = pd.DataFrame(filas)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        df.to_excel(xl, sheet_name="Cobranzas", index=False)
    buf.seek(0)
    nombre = f"Cobranzas_{MESES_ES[mes]}_{anio}.xlsx"
    resp = make_response(buf.read())
    resp.headers["Content-Type"] = ("application/vnd.openxmlformats-officedocument."
                                    "spreadsheetml.sheet")
    resp.headers["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return resp


@cobros_bp.route("/recordatorios")
@login_required
def recordatorios():
    """Lista de inquilinos que deben el mes elegido, con recordatorio de pago
    por WhatsApp listo para enviar de a uno."""
    hoy = date.today()
    mes = parse_num(request.args.get("mes"), entero=True) or hoy.month
    anio = parse_num(request.args.get("anio"), entero=True) or hoy.year

    items = []
    for c in Contrato.query.filter_by(estado="Vigente").all():
        if not c.inquilino:
            continue
        pago = next((p for p in c.pagos
                     if p.periodo_mes == mes and p.periodo_anio == anio), None)
        esperado = float(c.precio_actual or c.precio_inicial or 0)
        if pago and pago.estado == "Pagado":
            continue
        deuda = float(pago.saldo) if pago else esperado
        estado = pago.estado if pago else "Sin cobrar"
        msj = (f"Hola {c.inquilino.nombre}! Te escribo por el alquiler de "
               f"{c.inmueble.direccion}. El período {MESES_ES[mes]} {anio} figura "
               f"{estado.lower()}" + (f" (falta ${deuda:,.2f})" if estado == "Parcial" else "") +
               ". ¿Podés confirmarme cuándo lo abonás? ¡Gracias!")
        wa = link_whatsapp(c.inquilino.telefono, msj)
        items.append(dict(c=c, deuda=deuda, estado=estado, wa=wa,
                          tel_ok=whatsapp_valido(c.inquilino.telefono),
                          email=c.inquilino.email, msj=msj))
    items.sort(key=lambda it: (it["c"].inquilino.nombre or "").lower())
    con_wa = sum(1 for it in items if it["wa"])
    return render_template("cobros/recordatorios.html", items=items, mes=mes, anio=anio,
                           meses=MESES_ES, con_wa=con_wa,
                           anios=list(range(hoy.year - 4, hoy.year + 2)))


@cobros_bp.route("/contrato/<int:cid>")
@login_required
def detalle(cid):
    contrato = db.session.get(Contrato, cid) or abort(404)
    pagos = sorted(contrato.pagos,
                   key=lambda p: (p.periodo_anio or 0, p.periodo_mes or 0), reverse=True)
    return render_template("cobros/detalle.html", c=contrato, pagos=pagos,
                           resumen=_resumen(contrato), meses=MESES_ES)


# --------------------------------------------------------------------------- #
#  Alta / edición de pago
# --------------------------------------------------------------------------- #
def _leer_pago(pago, contrato):
    pago.numero = parse_num(request.form.get("numero"), entero=True)
    pago.periodo_mes = parse_num(request.form.get("periodo_mes"), entero=True)
    pago.periodo_anio = parse_num(request.form.get("periodo_anio"), entero=True)
    pago.fecha_pago = parse_fecha(request.form.get("fecha_pago"))
    pago.precio_alquiler = parse_num(request.form.get("precio_alquiler")) or 0
    pago.moneda = contrato.moneda or "Pesos"
    pago.forma_pago = request.form.get("forma_pago", "")
    pago.observaciones = request.form.get("observaciones", "").strip()
    pago.recibo_numero = request.form.get("recibo_numero", "").strip()

    # Mora: usa la ingresada, o si se pide, la calcula automáticamente.
    if request.form.get("mora_auto"):
        venc = vencimiento(pago.periodo_anio, pago.periodo_mes, contrato.dia_vencimiento or 10)
        pago.mora = calcular_mora(pago.precio_alquiler, contrato.mora_diaria_pct,
                                  venc, pago.fecha_pago)
    else:
        pago.mora = parse_num(request.form.get("mora")) or 0

    pago.pagado = parse_num(request.form.get("pagado"))
    if request.form.get("pagado_al_propietario"):
        pago.pagado_al_propietario = parse_fecha(request.form.get("fecha_prop")) or date.today()
    else:
        pago.pagado_al_propietario = None


@cobros_bp.route("/rapido", methods=["POST"])
@login_required
def rapido():
    """Registrar un pago desde el panel de Cobranzas, sin recargar la página.
    Acepta precio, mora, gastos extras, observaciones, forma de pago y monto pagado
    (permite pago parcial). Devuelve JSON para actualizar la fila al instante."""
    d = request.get_json(silent=True) or {}
    contrato = db.session.get(Contrato, parse_num(d.get("cid"), entero=True) or 0)
    if not contrato:
        return jsonify(ok=False, error="No se encontró el contrato."), 404

    mes = parse_num(d.get("mes"), entero=True)
    anio = parse_num(d.get("anio"), entero=True)
    precio = parse_num(d.get("precio")) or parse_num(d.get("monto"))
    if not mes or not anio:
        return jsonify(ok=False, error="Falta el período."), 400
    if not precio or precio <= 0:
        return jsonify(ok=False, error="El precio del alquiler debe ser mayor a 0."), 400

    # Evitar duplicar: si ya hay un pago de ese período, no crear otro.
    ya = next((p for p in contrato.pagos
               if p.periodo_mes == mes and p.periodo_anio == anio), None)
    if ya:
        return jsonify(ok=False, error="Ya existe un pago para ese período."), 409

    mora = parse_num(d.get("mora")) or 0
    # Gastos extras: lista de {desc, monto} (suma con decimales exactos)
    gastos = []
    gastos_total = q2(0)
    for g in (d.get("gastos") or []):
        desc = (g.get("desc") or "").strip()
        monto = parse_num(g.get("monto"))
        if desc and monto is not None:
            gastos.append((desc, monto))
            gastos_total += q2(monto)

    total = q2(precio) + q2(mora) + gastos_total
    pagado = parse_num(d.get("pagado"))
    if pagado is None:
        pagado = total
    pagado = q2(pagado)
    saldo = total - pagado
    if pagado <= 0:
        estado = "Pendiente"
    elif saldo > 0:
        estado = "Parcial"
    else:
        estado = "Pagado"
        saldo = q2(0)

    fecha = parse_fecha(d.get("fecha")) or date.today()
    nro = (max((p.numero or 0) for p in contrato.pagos) + 1) if contrato.pagos else 1
    pago = Pago(
        contrato_id=contrato.id, numero=nro, periodo_mes=mes, periodo_anio=anio,
        fecha_pago=fecha, precio_alquiler=precio, moneda=contrato.moneda or "Pesos",
        forma_pago=(d.get("forma_pago") or "").strip(),
        observaciones=(d.get("observaciones") or "").strip(),
        mora=mora, total=total, pagado=pagado, saldo=saldo, estado=estado,
    )
    for desc, monto in gastos:
        pago.gastos.append(GastoExtra(descripcion=desc, monto=monto))
    db.session.add(pago)
    db.session.commit()
    return jsonify(ok=True, pago_id=pago.id, estado=estado,
                   pagado=float(pagado), saldo=float(saldo), total=float(total),
                   moneda=pago.moneda,
                   recibo_url=url_for("recibos.recibo", pid=pago.id),
                   pdf_url=url_for("recibos.recibo_pdf", pid=pago.id),
                   abonar_url=url_for("cobros.abonar", pid=pago.id),
                   detalle_url=url_for("cobros.detalle", cid=contrato.id))


@cobros_bp.route("/contrato/<int:cid>/nuevo", methods=["GET", "POST"])
@login_required
def nuevo(cid):
    contrato = db.session.get(Contrato, cid) or abort(404)
    if request.method == "POST":
        pago = Pago(contrato_id=contrato.id)
        _leer_pago(pago, contrato)
        error = _validar(pago)
        if error:
            flash(error, "error")
            return render_template("cobros/form_pago.html", c=contrato, pago=pago,
                                   formas=FORMAS_PAGO, meses=MESES_ES, nuevo=True)
        gastos_total = _leer_gastos(pago)

        # Arrastrar saldo pendiente de meses anteriores a este pago.
        arrastrado = 0.0
        if request.form.get("arrastrar_saldo"):
            previos = [p for p in contrato.pagos if (p.saldo or 0) > 0]
            arrastrado = sum(float(p.saldo) for p in previos)
            if arrastrado > 0:
                pago.gastos.append(GastoExtra(descripcion="Saldo período(s) anterior(es)",
                                              monto=round(arrastrado, 2)))
                gastos_total += arrastrado
                destino = f"{MESES_ES[pago.periodo_mes]} {pago.periodo_anio}"
                for p in previos:
                    nota = f"Saldo {float(p.saldo):.2f} arrastrado a {destino}."
                    p.observaciones = ((p.observaciones or "") + " " + nota).strip()
                    p.saldo = 0
                    p.estado = "Arrastrado"

        if pago.pagado is None:
            pago.pagado = round(float(pago.precio_alquiler or 0) + float(pago.mora or 0)
                                + gastos_total - arrastrado, 2)
        _recalcular(pago, gastos_total)
        db.session.add(pago)
        db.session.commit()
        msg = f"Pago del período {MESES_ES[pago.periodo_mes]} {pago.periodo_anio} registrado."
        if arrastrado > 0:
            msg += f" Se arrastró {contrato.moneda} {arrastrado:,.2f} de saldo anterior."
        flash(msg, "ok")
        if request.form.get("guardar_seguir"):
            return redirect(url_for("cobros.nuevo", cid=contrato.id))
        # Al volver al detalle, ofrecer imprimir/enviar el recibo de este pago.
        return redirect(url_for("cobros.detalle", cid=contrato.id, recibo=pago.id))

    r = _resumen(contrato)
    # Permite prefijar el período desde el panel de cobranzas (?mes=&anio=).
    mes = parse_num(request.args.get("mes"), entero=True) or r["prox_mes"]
    anio = parse_num(request.args.get("anio"), entero=True) or r["prox_anio"]
    pago = Pago(numero=r["prox_nro"], periodo_mes=mes, periodo_anio=anio,
                fecha_pago=date.today(),
                precio_alquiler=contrato.precio_actual or contrato.precio_inicial)
    return render_template("cobros/form_pago.html", c=contrato, pago=pago,
                           formas=FORMAS_PAGO, meses=MESES_ES, nuevo=True,
                           deuda_previa=_deuda_previa(contrato))


@cobros_bp.route("/pago/<int:pid>/editar", methods=["GET", "POST"])
@login_required
def editar(pid):
    pago = db.session.get(Pago, pid) or abort(404)
    contrato = pago.contrato
    if request.method == "POST":
        _leer_pago(pago, contrato)
        error = _validar(pago)
        if error:
            flash(error, "error")
            return render_template("cobros/form_pago.html", c=contrato, pago=pago,
                                   formas=FORMAS_PAGO, meses=MESES_ES, nuevo=False)
        gastos_total = _leer_gastos(pago)
        if pago.pagado is None:
            pago.pagado = 0
        _recalcular(pago, gastos_total)
        db.session.commit()
        flash("Pago actualizado.", "ok")
        return redirect(url_for("cobros.detalle", cid=contrato.id))
    return render_template("cobros/form_pago.html", c=contrato, pago=pago,
                           formas=FORMAS_PAGO, meses=MESES_ES, nuevo=False)


@cobros_bp.route("/pago/<int:pid>/eliminar", methods=["POST"])
@login_required
def eliminar(pid):
    pago = db.session.get(Pago, pid) or abort(404)
    cid = pago.contrato_id
    db.session.delete(pago)
    db.session.commit()
    flash("Pago eliminado.", "ok")
    return redirect(url_for("cobros.detalle", cid=cid))


@cobros_bp.route("/pago/<int:pid>/abonar", methods=["GET", "POST"])
@login_required
def abonar(pid):
    """Registra un pago a cuenta sobre un saldo pendiente (se acumula)."""
    pago = db.session.get(Pago, pid) or abort(404)
    saldo = float(pago.saldo or 0)
    if request.method == "POST":
        monto = parse_num(request.form.get("monto"))
        if not monto or monto <= 0:
            flash("Ingresá un monto mayor a 0.", "error")
            return render_template("cobros/abonar.html", pago=pago, saldo=saldo,
                                   formas=FORMAS_PAGO, meses=MESES_ES)
        pago.pagado = q2(pago.pagado) + q2(monto)
        if request.form.get("fecha_pago"):
            pago.fecha_pago = parse_fecha(request.form.get("fecha_pago")) or pago.fecha_pago
        if request.form.get("forma_pago"):
            pago.forma_pago = request.form.get("forma_pago")
        nota = request.form.get("observaciones", "").strip()
        if nota:
            pago.observaciones = ((pago.observaciones or "") + " " + nota).strip()
        _estado_saldo(pago)
        db.session.commit()
        flash(f"Cobro a cuenta registrado. Saldo restante: {pago.moneda} {float(pago.saldo):,.2f}.", "ok")
        return redirect(url_for("cobros.detalle", cid=pago.contrato_id))
    return render_template("cobros/abonar.html", pago=pago, saldo=saldo,
                           formas=FORMAS_PAGO, meses=MESES_ES)


def _validar(pago):
    if not pago.periodo_mes or not pago.periodo_anio:
        return "Indicá el mes y el año del pago."
    if not pago.precio_alquiler or pago.precio_alquiler <= 0:
        return "El precio del alquiler debe ser mayor a 0."
    if not pago.fecha_pago:
        return "Indicá la fecha de pago."
    return None
