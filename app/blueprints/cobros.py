"""Registro de cobros: pagos, mora, gastos extras, historial y deuda."""
from datetime import date

from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, abort, jsonify, make_response)
from flask_login import login_required
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import IntegrityError

from .. import db
from ..idempotencia import nueva_clave, reservar
from ..models import Contrato, Pago, GastoExtra
from ..ui import render_ui
from ..utils import (parse_fecha, parse_num, vencimiento, calcular_mora,
                     periodo_siguiente, MESES_ES, link_whatsapp, whatsapp_valido, q2)
from ..calculos import (estado_periodo, canon_vigente, deuda_real,
                        aumento_en_mes, aumento_registrado_en_mes)

cobros_bp = Blueprint("cobros", __name__, url_prefix="/cobros")

FORMAS_PAGO = ["Efectivo", "Transferencia", "Transferencia prop / inmo", "Cheque", "Otro"]


# --------------------------------------------------------------------------- #
#  Helpers de resumen
# --------------------------------------------------------------------------- #
def _resumen(contrato):
    pagos = sorted(contrato.pagos, key=lambda p: (p.periodo_anio or 0, p.periodo_mes or 0))
    # Deuda real: incluye los meses vencidos que ni siquiera se llegaron a
    # registrar como pago (no solo los saldos de pagos parciales ya cargados).
    # Antes esto sumaba nomás p.saldo de los pagos existentes, así que un
    # contrato con meses sin cargar mostraba "Deuda registrada $0" acá aunque
    # la ficha del contrato (que sí usa deuda_real) mostrara la deuda real.
    deuda = deuda_real(contrato, date.today())
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
    # Un valor por fila (0/1), sincronizado por JS con el checkbox "Trasladar al
    # propietario" -- así, aunque el checkbox esté destildado, sigue habiendo un
    # valor alineado por índice con gasto_desc/gasto_monto.
    traslada = request.form.getlist("gasto_trasladar")
    total = 0.0
    for i, desc in enumerate(descs):
        monto = parse_num(montos[i]) if i < len(montos) else None
        if desc.strip() and monto is not None:
            tr = traslada[i] != "0" if i < len(traslada) else True
            pago.gastos.append(GastoExtra(descripcion=desc.strip(), monto=monto,
                                          trasladar_liquidacion=tr))
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
        # Estado del período según la regla central (única fuente de verdad).
        info = estado_periodo(c, mes, anio, hoy=hoy)
        pago, esperado, estado = info["pago"], info["esperado"], info["estado"]
        cobrado, saldo, venc = info["cobrado"], info["saldo"], info["venc"]
        tot_esperado += esperado
        tot_cobrado += cobrado
        if estado != "Pagado":
            tot_pendiente += saldo
        prox_nro = (max((p.numero or 0) for p in c.pagos) + 1) if c.pagos else 1
        # ¿A este contrato le corresponde un aumento en el mes que se está cobrando
        # y todavía no se registró? Sirve para avisar antes de cobrar al precio viejo.
        f_aum = aumento_en_mes(c, anio, mes)
        aum_pendiente = bool(f_aum) and not aumento_registrado_en_mes(c, anio, mes)
        # Contrato vencido: pasó su fecha de fin pero sigue Vigente (no se renovó).
        contrato_vencido = bool(c.fecha_fin and c.fecha_fin < hoy)
        filas.append(dict(c=c, pago=pago, esperado=esperado, estado=estado,
                          cobrado=cobrado, saldo=saldo, prox_nro=prox_nro,
                          venc=venc, aum_pendiente=aum_pendiente,
                          contrato_vencido=contrato_vencido,
                          mora=float(calcular_mora(esperado, c.mora_diaria_pct,
                                                   venc, hoy) or 0),
                          registrable=pago is None))

    cuenta = dict(todos=len(filas),
                  pendiente=sum(1 for f in filas if f["estado"] != "Pagado"))
    cuenta["cobrado"] = cuenta["todos"] - cuenta["pendiente"]

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

    return render_ui("cobros/index.html", filas=filas, mes=mes, anio=anio,
                     filtro=filtro, meses=MESES_ES, formas=FORMAS_PAGO, hoy=hoy,
                     cuenta=cuenta,
                     totales=dict(esperado=tot_esperado, cobrado=tot_cobrado,
                                  pendiente=tot_pendiente),
                     anios=list(range(hoy.year - 4, hoy.year + 2)))


@cobros_bp.route("/react")
@login_required
def react():
    """Isla React desactivada: se usa la versión clásica. Se conserva el código
    y la plantilla (cobros/react.html) por si se retoma más adelante."""
    return redirect(url_for("cobros.index", mes=request.args.get("mes"),
                            anio=request.args.get("anio")))


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
        info = estado_periodo(c, mes, anio)
        pago, esperado = info["pago"], info["esperado"]
        estado = "Sin cobrar" if info["estado"] == "Sin registrar" else info["estado"]
        cobrado, saldo = info["cobrado"], info["saldo"]
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
        info = estado_periodo(c, mes, anio)
        if info["estado"] == "Pagado":
            continue
        deuda = info["saldo"]
        estado = "Sin cobrar" if info["estado"] == "Sin registrar" else info["estado"]
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


@cobros_bp.route("/pagos")
@login_required
def pagos():
    """Historial global de pagos: todos los pagos registrados (incluidos los
    importados), buscables y filtrables, sin entrar contrato por contrato."""
    hoy = date.today()
    q = request.args.get("q", "").strip().lower()
    anio = parse_num(request.args.get("anio"), entero=True)
    mes = parse_num(request.args.get("mes"), entero=True)
    estado = request.args.get("estado", "")

    query = Pago.query.options(
        joinedload(Pago.contrato).joinedload(Contrato.inquilino),
        joinedload(Pago.contrato).joinedload(Contrato.inmueble))
    if anio:
        query = query.filter(Pago.periodo_anio == anio)
    if mes:
        query = query.filter(Pago.periodo_mes == mes)
    if estado:
        query = query.filter(Pago.estado == estado)
    query = query.order_by(Pago.periodo_anio.desc(), Pago.periodo_mes.desc(),
                           Pago.id.desc())
    filas = query.limit(800).all()

    if q:
        def _match(p):
            c = p.contrato
            campos = " ".join(filter(None, [
                (c.inquilino.nombre if c and c.inquilino else ""),
                (c.inmueble.direccion if c and c.inmueble else ""),
                (c.inmueble.codigo if c and c.inmueble else ""),
                (p.recibo_numero or "")])).lower()
            return q in campos
        filas = [p for p in filas if _match(p)]

    anios = [a for (a,) in db.session.query(Pago.periodo_anio)
             .distinct().order_by(Pago.periodo_anio.desc()).all() if a]
    tot_cobrado = sum(float(p.pagado or 0) for p in filas)
    tot_saldo = sum(float(p.saldo or 0) for p in filas)
    return render_template("cobros/pagos.html", pagos=filas, meses=MESES_ES,
                           q=request.args.get("q", ""), anio=anio, mes=mes,
                           estado=estado, anios=anios, tot_cobrado=tot_cobrado,
                           tot_saldo=tot_saldo, hoy=hoy)


@cobros_bp.route("/contrato/<int:cid>")
@login_required
def detalle(cid):
    contrato = db.session.get(Contrato, cid) or abort(404)
    pagos = sorted(contrato.pagos,
                   key=lambda p: (p.periodo_anio or 0, p.periodo_mes or 0), reverse=True)
    return render_template("cobros/detalle.html", c=contrato, pagos=pagos,
                           resumen=_resumen(contrato), meses=MESES_ES,
                           pendientes=len(_periodos_pendientes(contrato, date.today())))


def _periodos_pendientes(contrato, hoy):
    """Períodos del contrato (de inicio a hoy, sin pasar el fin) SIN un pago activo.
    Sirve para el alta múltiple de un contrato que arrancó hace meses."""
    inicio = contrato.fecha_inicio
    if not inicio:
        return []
    fin_ym = hoy.year * 12 + (hoy.month - 1)
    if contrato.fecha_fin:
        fin_ym = min(fin_ym, contrato.fecha_fin.year * 12 + (contrato.fecha_fin.month - 1))
    ini_ym = inicio.year * 12 + (inicio.month - 1)
    pagados = {(p.periodo_anio, p.periodo_mes) for p in contrato.pagos if p.estado != "Anulado"}
    out = []
    for ym in range(ini_ym, fin_ym + 1):
        a, m = ym // 12, ym % 12 + 1
        if (a, m) in pagados:
            continue
        out.append({"mes": m, "anio": a,
                    "esperado": canon_vigente(contrato, m, a),
                    "venc": vencimiento(a, m, contrato.dia_vencimiento or 10)})
    return out


@cobros_bp.route("/contrato/<int:cid>/pagos-multiples", methods=["GET", "POST"])
@login_required
def pagos_multiples(cid):
    """Registrar de una sola vez varios períodos (típico al cargar un contrato viejo)."""
    contrato = db.session.get(Contrato, cid) or abort(404)
    hoy = date.today()
    if request.method == "POST":
        fecha_modo = request.form.get("fecha_modo", "venc")   # venc | hoy | fija
        fecha_fija = parse_fecha(request.form.get("fecha_fija"))
        forma = (request.form.get("forma_pago") or "").strip()
        con_mora = bool(request.form.get("con_mora"))
        pagados = {(p.periodo_anio, p.periodo_mes) for p in contrato.pagos if p.estado != "Anulado"}
        nro = (max((p.numero or 0) for p in contrato.pagos) + 1) if contrato.pagos else 1
        creados, omitidos = 0, 0
        for token in request.form.getlist("periodo"):
            try:
                m, a = (int(x) for x in token.split("-"))
            except ValueError:
                continue
            if (a, m) in pagados:
                omitidos += 1
                continue
            esperado = canon_vigente(contrato, m, a)
            venc = vencimiento(a, m, contrato.dia_vencimiento or 10)
            fpago = hoy if fecha_modo == "hoy" else (fecha_fija if (fecha_modo == "fija" and fecha_fija) else venc)
            mora = calcular_mora(esperado, contrato.mora_diaria_pct, venc, fpago) if con_mora else 0
            total = q2(esperado) + q2(mora)
            db.session.add(Pago(
                contrato_id=contrato.id, numero=nro, periodo_mes=m, periodo_anio=a,
                fecha_pago=fpago, precio_alquiler=esperado, moneda=contrato.moneda or "Pesos",
                forma_pago=forma, mora=mora, total=total, pagado=total, saldo=q2(0), estado="Pagado"))
            pagados.add((a, m))
            nro += 1
            creados += 1
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Algún período ya tenía un pago. Volvé a intentar.", "error")
            return redirect(url_for("cobros.pagos_multiples", cid=cid))
        flash(f"Se registraron {creados} pago(s)."
              + (f" ({omitidos} ya existían y se saltearon.)" if omitidos else ""), "ok")
        return redirect(url_for("cobros.detalle", cid=cid))
    return render_template("cobros/pagos_multiples.html", c=contrato, meses=MESES_ES,
                           formas=FORMAS_PAGO, hoy=hoy,
                           pendientes=_periodos_pendientes(contrato, hoy))


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
    # Sin número de recibo va NULL (no ""): así no choca con el único de la base.
    pago.recibo_numero = request.form.get("recibo_numero", "").strip() or None

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

    # Evitar duplicar: si ya hay un pago ACTIVO de ese período, no crear otro.
    # (Un pago anulado no bloquea: se puede volver a cobrar el mes.)
    ya = next((p for p in contrato.pagos
               if p.periodo_mes == mes and p.periodo_anio == anio
               and p.estado != "Anulado"), None)
    if ya:
        return jsonify(ok=False, error="Ya existe un pago para ese período."), 409

    if not reservar("cobro-rapido", d.get("idem")):
        return jsonify(ok=False, error="Ese cobro ya se había registrado. "
                       "Actualizá la página para verlo."), 409

    # La mora la calcula el servidor con la misma función que el resto del
    # sistema; la pantalla solo muestra una vista previa. Solo se respeta el
    # valor del formulario si el usuario lo escribió a mano.
    if d.get("mora") is None:
        mora = calcular_mora(precio, contrato.mora_diaria_pct,
                             vencimiento(anio, mes, contrato.dia_vencimiento or 10),
                             parse_fecha(d.get("fecha")) or date.today())
    else:
        mora = parse_num(d.get("mora")) or 0
    # Gastos extras: lista de {desc, monto, trasladar} (suma con decimales exactos).
    # trasladar=True (default) -> se traslada a la liquidación del propietario;
    # False -> lo cobramos junto con el alquiler pero es plata nuestra (ej. seguro).
    gastos = []
    gastos_total = q2(0)
    for g in (d.get("gastos") or []):
        desc = (g.get("desc") or "").strip()
        monto = parse_num(g.get("monto"))
        if desc and monto is not None:
            trasladar = g.get("trasladar")
            trasladar = True if trasladar is None else bool(trasladar)
            gastos.append((desc, monto, trasladar))
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
    for desc, monto, trasladar in gastos:
        pago.gastos.append(GastoExtra(descripcion=desc, monto=monto,
                                      trasladar_liquidacion=trasladar))
    db.session.add(pago)
    try:
        db.session.commit()
    except IntegrityError:
        # Otra operación creó el pago de este período al mismo tiempo (o doble clic).
        db.session.rollback()
        return jsonify(ok=False, error="Ya existe un pago para ese período. "
                       "Actualizá la página para verlo."), 409
    # Datos para ofrecer el recibo apenas se guarda (imprimir / PDF / email / WhatsApp),
    # igual que el flujo clásico. El WhatsApp deja el mensaje escrito; el PDF se adjunta aparte.
    inq = contrato.inquilino
    direccion = contrato.inmueble.direccion if contrato.inmueble else ""
    periodo_txt = f"{MESES_ES[mes]} de {anio}" if mes else ""
    msj_wa = (f"Hola {inq.nombre if inq else ''}! Te enviamos tu recibo de pago del "
              f"alquiler de {direccion}"
              + (f" correspondiente a {periodo_txt}" if periodo_txt else "") + ". ¡Muchas gracias!")
    wa_url = (link_whatsapp(inq.telefono, msj_wa)
              if (inq and whatsapp_valido(inq.telefono)) else None)
    return jsonify(ok=True, pago_id=pago.id, estado=estado,
                   pagado=float(pagado), saldo=float(saldo), total=float(total),
                   moneda=pago.moneda, quien=(inq.nombre if inq else ""),
                   recibo_url=url_for("recibos.recibo", pid=pago.id),
                   pdf_url=url_for("recibos.recibo_pdf", pid=pago.id),
                   email_url=url_for("recibos.recibo_email", pid=pago.id),
                   wa_url=wa_url, tiene_email=bool(inq and inq.email),
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
        # Aviso claro si ya hay un pago de ese período (antes de tocar la base).
        if not error:
            dup = next((p for p in contrato.pagos
                        if p.periodo_mes == pago.periodo_mes
                        and p.periodo_anio == pago.periodo_anio
                        and p.estado != "Anulado"), None)
            if dup:
                error = (f"Ya existe un pago para {MESES_ES[pago.periodo_mes]} "
                         f"{pago.periodo_anio}. Abrí ese pago para completarlo o corregirlo.")
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
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(f"Ya existe un pago para {MESES_ES[pago.periodo_mes]} "
                  f"{pago.periodo_anio}. Abrí ese pago para completarlo o corregirlo.", "error")
            return redirect(url_for("cobros.detalle", cid=contrato.id))
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


@cobros_bp.route("/pago/<int:pid>/anular", methods=["POST"])
@login_required
def anular(pid):
    """Anula un pago sin borrarlo: conserva el número, el recibo y el rastro, y
    libera el período para volver a cobrarlo. No se pierde plata ni numeración."""
    pago = db.session.get(Pago, pid) or abort(404)
    cid = pago.contrato_id
    if pago.estado == "Anulado":
        flash("Ese pago ya estaba anulado.", "ok")
        return redirect(url_for("cobros.detalle", cid=cid))
    motivo = (request.form.get("motivo") or "").strip()
    from flask_login import current_user
    quien = getattr(current_user, "username", "") or "—"
    sello = date.today().strftime("%d/%m/%Y")
    nota = f"ANULADO {sello} por {quien}" + (f": {motivo}" if motivo else "") + "."
    pago.observaciones = ((pago.observaciones or "") + " " + nota).strip()
    pago.estado = "Anulado"
    pago.saldo = 0
    db.session.commit()
    flash("Pago anulado. Queda registrado como anulado y el período puede volver a "
          "cobrarse.", "ok")
    return redirect(url_for("cobros.detalle", cid=cid))


# Alias viejo: por si quedó algún enlace a /eliminar, ahora anula (no borra).
@cobros_bp.route("/pago/<int:pid>/eliminar", methods=["POST"])
@login_required
def eliminar(pid):
    return anular(pid)


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
                                   formas=FORMAS_PAGO, meses=MESES_ES,
                                   idem=nueva_clave())
        if q2(monto) > q2(saldo):
            flash(f"El saldo de ese período es {pago.moneda} {saldo:,.2f}: no se "
                  f"puede cobrar más que eso. Si sobra plata, cargala como pago "
                  f"del período siguiente.", "error")
            return render_template("cobros/abonar.html", pago=pago, saldo=saldo,
                                   formas=FORMAS_PAGO, meses=MESES_ES,
                                   idem=nueva_clave())
        # Antes de tocar la plata: este pago a cuenta no puede entrar dos veces
        # (doble clic, F5 sobre el POST, dos pestañas). El único por período no
        # cubre este caso porque acá se suma sobre un pago que ya existe.
        if not reservar("abono", request.form.get("idem")):
            flash("Ese pago a cuenta ya estaba registrado: no lo dupliqué.", "ok")
            return redirect(url_for("cobros.detalle", cid=pago.contrato_id))
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
                           formas=FORMAS_PAGO, meses=MESES_ES, idem=nueva_clave())


def _validar(pago):
    if not pago.periodo_mes or not pago.periodo_anio:
        return "Indicá el mes y el año del pago."
    if not pago.precio_alquiler or pago.precio_alquiler <= 0:
        return "El precio del alquiler debe ser mayor a 0."
    if not pago.fecha_pago:
        return "Indicá la fecha de pago."
    return None
