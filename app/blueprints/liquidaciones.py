"""Liquidaciones a propietarios: por período, todas juntas o individuales."""
from datetime import date

import os

from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, abort, jsonify)
from flask_login import login_required

from .. import db
from .. import facturador
from ..idempotencia import nueva_clave, reservar
from ..models import Contrato, Pago, Persona, Liquidacion, Ajustes, ConceptoLiquidacion
from ..ui import render_ui
from ..utils import parse_num, pesos_letras, MESES_ES

liquidaciones_bp = Blueprint("liquidaciones", __name__, url_prefix="/liquidaciones")


def _pagos_periodo(propietario_id, mes, anio, contrato_id=None, solo_pendientes=False):
    """Pagos cobrados (pagado>0) de ese propietario en el período.

    - contrato_id: si se indica, solo ese contrato.
    - solo_pendientes: solo los que aún NO fueron liquidados al propietario.
    """
    pagos = []
    for p in (Pago.query.filter_by(periodo_mes=mes, periodo_anio=anio)
              .filter(Pago.estado != "Anulado").all()):
        c = p.contrato
        if not c or float(p.pagado or 0) <= 0:
            continue
        prop = c.propietario_id or (c.inmueble.propietario_id if c.inmueble else None)
        if prop != propietario_id:
            continue
        if contrato_id and c.id != contrato_id:
            continue
        if solo_pendientes and p.pagado_al_propietario:
            continue
        pagos.append(p)
    return pagos


def _comision_pct(c):
    if c.comision_pct is not None:
        return float(c.comision_pct)
    return float(c.inmueble.comision_pct or 0) if c.inmueble else 0


def _detalle(pagos):
    """Arma el detalle con comisión por inmueble y totales.

    Los gastos extra de cada pago (agua, expensas, seguro...) marcados como
    "trasladar al propietario" se suman al neto tal cual, sin comisión -- no son
    alquiler, son plata del propietario que pasa de largo. Los que NO se marcaron
    para trasladar quedan afuera: se cobraron junto con el alquiler pero son de la
    inmobiliaria (ej.: un seguro que paga la inmobiliaria, no el propietario)."""
    items, ingresos, comision, extras = [], 0.0, 0.0, 0.0
    for p in pagos:
        c = p.contrato
        pct = _comision_pct(c)
        alq = float(p.precio_alquiler or 0)
        com = round(alq * pct / 100.0, 2)
        gastos_trasl = [g for g in p.gastos if g.trasladar_liquidacion]
        gex = round(sum(float(g.monto or 0) for g in gastos_trasl), 2)
        ingresos += alq
        comision += com
        extras += gex
        items.append(dict(pago=p, contrato=c, inmueble=c.inmueble,
                          inquilino=c.inquilino, alquiler=alq, pct=pct, comision=com,
                          extras=gex,
                          # Desglose de cada gasto extra trasladado (no solo el total),
                          # para que en la liquidación se vea qué es cada importe.
                          gastos=[dict(descripcion=g.descripcion or "Gasto",
                                       monto=round(float(g.monto or 0), 2))
                                  for g in gastos_trasl],
                          neto=round(alq - com + gex, 2),
                          liquidada=p.pagado_al_propietario is not None))
    return (items, round(ingresos, 2), round(comision, 2),
           round(ingresos - comision + extras, 2))


def _facturar_honorarios(liq, prop, confirmar=False):
    """Emite (best-effort) la factura de honorarios de la liquidación al propietario.

    Aplica siempre que se genera una liquidación: toma la CUIT del propietario y
    factura la comisión. Si la comisión no supera el mínimo, el facturador pide
    confirmación y acá se informa para que el usuario decida. Devuelve el estado.
    """
    ajustes = Ajustes.get()
    if not facturador.inmobiliaria_autorizada(ajustes):
        return "no_autorizado"
    resultado = facturador.facturar_liquidacion(liq, prop, ajustes,
                                                 confirmar_bajo_minimo=confirmar)
    estado = resultado.get("estado")
    _guardar_factura(liq, resultado)   # deja el CAE/estado guardado en la liquidación
    if estado == "emitida":
        cae = liq.factura_cae
        num = liq.factura_numero
        flash("Factura de honorarios emitida al propietario"
              + (f" — {('C ' + num) if num else 'comprobante'}" if num else "")
              + (f" · CAE {cae}." if cae else "."), "ok")
    elif estado == "error":
        flash("La liquidación se generó, pero la factura de honorarios no se pudo "
              f"emitir: {resultado.get('mensaje') or 'error del facturador'}. "
              "Quedó en la bandeja de pendientes de facturar.", "error")
    elif estado == "requiere_reconciliacion":
        flash("La liquidación se generó. La factura quedó con estado a confirmar "
              "(no recibimos respuesta del facturador). Se va a reconciliar sola; "
              "también podés forzarlo desde 'Pendientes de facturar'.", "ok")
    elif estado == "sin_cuit":
        flash("La liquidación se generó, pero no se facturó: el propietario no "
              "tiene CUIT cargado. Quedó en la bandeja de pendientes de facturar.", "error")
    # 'requiere_confirmacion' y 'deshabilitado' no se avisan por toast:
    #   - requiere_confirmacion: se resuelve con el banner de la liquidación.
    #   - deshabilitado: la integración no está configurada (FACTURADOR_URL vacío).
    return estado


# Tipos de comprobante de ARCA → letra para mostrar.
_TIPO_LETRA = {1: "A", 6: "B", 11: "C", 51: "M", 201: "A", 206: "B", 211: "C"}


def _num_comprobante(f):
    """'0001-00000123' a partir de punto_venta + numero (formato del Facturador).
    Cae a un valor ya formateado si viniera como string."""
    pv, nro = f.get("punto_venta"), f.get("numero")
    if isinstance(pv, int) and isinstance(nro, int):
        return f"{pv:04d}-{nro:08d}"
    return f.get("numero") or f.get("comprobante") or None


def _tipo_letra(f):
    t = f.get("tipo_comprobante")
    if isinstance(t, int):
        return _TIPO_LETRA.get(t, str(t))
    return str(f.get("tipo") or f.get("letra") or "") or None


def _guardar_factura(liq, resultado):
    """Persiste en la liquidación el resultado de la emisión (CAE, número, PDF, etc.).
    Mapea los campos reales de FacturaOut del Facturador (numero+punto_venta,
    tipo_comprobante, fecha_comprobante, cae_vencimiento). Best-effort."""
    from ..utils import parse_fecha

    def _fecha(v):
        return parse_fecha(v) if isinstance(v, str) else None

    try:
        estado = resultado.get("estado")
        liq.factura_estado = estado
        if estado == "emitida":
            f = resultado.get("factura") or {}
            liq.factura_id = f.get("id")
            liq.factura_numero = _num_comprobante(f)
            liq.factura_tipo = _tipo_letra(f)
            liq.factura_cae = f.get("cae")
            liq.factura_cae_vto = _fecha(f.get("cae_vencimiento") or f.get("cae_vto"))
            liq.factura_fecha = (_fecha(f.get("fecha_comprobante") or f.get("fecha"))
                                 or liq.fecha)
            liq.factura_detalle = None
        else:
            liq.factura_detalle = (resultado.get("mensaje")
                                   or resultado.get("detail") or None)
        db.session.commit()
    except Exception:
        db.session.rollback()


def _pendientes_facturar_query():
    """Liquidaciones cuya factura de honorarios NO quedó emitida (o nunca se intentó).
    Sirve para que un facturador caído o un CUIT faltante no queden en el olvido."""
    from sqlalchemy import or_
    return (Liquidacion.query
            .filter(or_(Liquidacion.factura_estado.is_(None),
                        Liquidacion.factura_estado != "emitida"))
            .order_by(Liquidacion.fecha.desc().nullslast(), Liquidacion.id.desc()))


@liquidaciones_bp.app_context_processor
def _inyectar_pendientes():
    """Contador para el menú/enlaces (solo si el facturador está habilitado)."""
    try:
        if not facturador.habilitado():
            return {"pendientes_facturar": 0}
        return {"pendientes_facturar": _pendientes_facturar_query().count()}
    except Exception:
        return {"pendientes_facturar": 0}


@liquidaciones_bp.route("/pendientes-facturar")
@login_required
def pendientes_facturar():
    """Bandeja de liquidaciones sin factura emitida (error, sin CUIT, sin intentar…)."""
    liqs = _pendientes_facturar_query().all()
    props = {p.id: p for p in Persona.query.all()}
    filas = [dict(liq=l, prop=props.get(l.propietario_id)) for l in liqs]
    return render_template("liquidaciones/pendientes.html", filas=filas,
                           meses=MESES_ES, habilitado=facturador.habilitado())


def _reconciliar_liquidacion(liq, ajustes):
    """Si el comprobante de esta liquidación ya se emitió en el Facturador (aunque acá
    figure pendiente/error), trae el CAE y actualiza la liquidación. Devuelve True si
    la reconcilió."""
    if liq.factura_estado == "emitida":
        return False
    res = facturador.buscar_comprobante(facturador.referencia_externa(liq), ajustes)
    if res.get("estado") == "emitida":
        _guardar_factura(liq, res)
        return True
    return False


@liquidaciones_bp.route("/reconciliar", methods=["POST"])
@login_required
def reconciliar():
    """Fase 6.3: revisa las liquidaciones pendientes contra el Facturador y actualiza
    las que en realidad ya tienen comprobante emitido (resuelve timeouts, cortes)."""
    if not facturador.habilitado():
        flash("El facturador no está configurado, no hay nada que reconciliar.", "error")
        return redirect(url_for("liquidaciones.pendientes_facturar"))
    ajustes = Ajustes.get()
    facturador.reconciliar_pendientes_en_facturador(ajustes)
    reconciliadas = 0
    for liq in _pendientes_facturar_query().all():
        try:
            if _reconciliar_liquidacion(liq, ajustes):
                reconciliadas += 1
        except Exception:
            db.session.rollback()
    if reconciliadas:
        flash(f"Reconciliación lista: {reconciliadas} liquidación(es) que ya estaban "
              "facturadas quedaron actualizadas con su CAE.", "ok")
    else:
        flash("Reconciliación lista: no había comprobantes emitidos pendientes de "
              "sincronizar.", "ok")
    return redirect(url_for("liquidaciones.pendientes_facturar"))


@liquidaciones_bp.route("/reconciliar-cron", methods=["POST"])
def reconciliar_cron():
    """Reconciliación AUTOMÁTICA para un cron (p. ej. Railway cada 5 min). No requiere
    login: se autentica con el header X-Reconciliar-Token contra la variable
    RECONCILIAR_TOKEN. Reconcilia las liquidaciones pendientes de TODAS las inmobiliarias
    (usa el token del facturador de cada una). Idempotente y seguro: solo lee del
    Facturador y actualiza a 'emitida' lo que ya tiene CAE."""
    from ..seguridad import token_igual
    token_env = os.environ.get("RECONCILIAR_TOKEN")
    if not token_env:
        abort(404)   # función deshabilitada si no se configuró el token
    if not token_igual(request.headers.get("X-Reconciliar-Token"), token_env):
        abort(403)
    if not facturador.habilitado():
        return jsonify(ok=True, reconciliadas=0, revisadas=0,
                       detalle="facturador no configurado"), 200

    ajustes_por_inmo = {}

    def _ajustes_de(inmo_id):
        if inmo_id not in ajustes_por_inmo:
            ajustes_por_inmo[inmo_id] = Ajustes.query.filter_by(
                inmobiliaria_id=inmo_id).first()
        return ajustes_por_inmo[inmo_id]

    pendientes = _pendientes_facturar_query().all()

    # Primero el Facturador resuelve lo suyo: los comprobantes que quedaron en
    # "revisar" por un timeout de ARCA pueden estar autorizados allá sin CAE registrado.
    # Recién después tiene sentido preguntarle por cada liquidación.
    resueltas_en_facturador = 0
    for inmo_id in {liq.inmobiliaria_id for liq in pendientes}:
        resueltas_en_facturador += facturador.reconciliar_pendientes_en_facturador(
            _ajustes_de(inmo_id)
        )

    reconciliadas = revisadas = 0
    for liq in pendientes:
        revisadas += 1
        try:
            if _reconciliar_liquidacion(liq, _ajustes_de(liq.inmobiliaria_id)):
                reconciliadas += 1
        except Exception:
            db.session.rollback()
    return jsonify(ok=True, reconciliadas=reconciliadas, revisadas=revisadas,
                   resueltas_en_facturador=resueltas_en_facturador), 200


# --------------------------------------------------------------------------- #
#  Panel por período
# --------------------------------------------------------------------------- #
@liquidaciones_bp.route("/")
@login_required
def index():
    hoy = date.today()
    mes = parse_num(request.args.get("mes"), entero=True) or hoy.month
    anio = parse_num(request.args.get("anio"), entero=True) or hoy.year

    por_prop = {}
    for p in (Pago.query.filter_by(periodo_mes=mes, periodo_anio=anio)
              .filter(Pago.estado != "Anulado").all()):
        c = p.contrato
        if not c or float(p.pagado or 0) <= 0:
            continue
        prop_id = c.propietario_id or (c.inmueble.propietario_id if c.inmueble else None)
        if not prop_id:
            continue
        por_prop.setdefault(prop_id, []).append(p)

    filas = []
    for prop_id, pagos in por_prop.items():
        prop = db.session.get(Persona, prop_id)
        _, ingresos, comision, neto = _detalle(pagos)
        liquidados = sum(1 for p in pagos if p.pagado_al_propietario)
        if liquidados == 0:
            estado = "Pendiente"
        elif liquidados == len(pagos):
            estado = "Liquidada"
        else:
            estado = "Parcial"
        filas.append(dict(prop=prop, cant=len(pagos), ingresos=ingresos,
                          comision=comision, neto=neto, estado=estado))
    filas.sort(key=lambda f: f["prop"].nombre if f["prop"] else "")

    return render_ui("liquidaciones/index.html", filas=filas, mes=mes, anio=anio,
                     meses=MESES_ES, anios=list(range(hoy.year - 4, hoy.year + 2)),
                     tot_ingresos=sum(f["ingresos"] for f in filas),
                     tot_comision=sum(f["comision"] for f in filas),
                     tot_neto=sum(f["neto"] for f in filas),
                     sin_facturar=_pendientes_facturar_query().limit(8).all())


# --------------------------------------------------------------------------- #
#  Gestión por propietario (elegir todas o individual)
# --------------------------------------------------------------------------- #
@liquidaciones_bp.route("/propietario/<int:pid>")
@login_required
def gestionar(pid):
    prop = db.session.get(Persona, pid) or abort(404)
    hoy = date.today()
    mes = parse_num(request.args.get("mes"), entero=True) or hoy.month
    anio = parse_num(request.args.get("anio"), entero=True) or hoy.year
    pagos = _pagos_periodo(pid, mes, anio)
    items, ingresos, comision, neto = _detalle(pagos)
    pendientes = sum(1 for it in items if not it["liquidada"])
    # Clave de idempotencia por botón: evita que un doble clic / F5 sobre el POST
    # genere dos liquidaciones (y, peor, dos facturas de honorarios) para el mismo
    # período. Se regenera en cada carga de la pantalla, igual que en cobros/abonar.
    for it in items:
        it["idem"] = nueva_clave()
    return render_template("liquidaciones/gestionar.html", prop=prop, items=items,
                           ingresos=ingresos, comision=comision, neto=neto,
                           pendientes=pendientes, mes=mes, anio=anio, meses=MESES_ES,
                           idem_todas=nueva_clave())


@liquidaciones_bp.route("/imprimir/<int:pid>")
@login_required
def ver(pid):
    """Liquidación imprimible. Con ?contrato=<id> imprime solo ese inmueble."""
    prop = db.session.get(Persona, pid) or abort(404)
    hoy = date.today()
    mes = parse_num(request.args.get("mes"), entero=True) or hoy.month
    anio = parse_num(request.args.get("anio"), entero=True) or hoy.year
    contrato_id = parse_num(request.args.get("contrato"), entero=True)
    pagos = _pagos_periodo(pid, mes, anio, contrato_id=contrato_id)
    items, ingresos, comision, neto = _detalle(pagos)
    liq = Liquidacion.query.filter_by(propietario_id=pid, periodo_mes=mes,
                                      periodo_anio=anio, contrato_id=contrato_id).first()
    conceptos = list(liq.conceptos) if liq else []
    neto_final = round(neto + float(sum(float(c.monto or 0) for c in conceptos)), 2)
    a = Ajustes.get()
    return render_template("liquidaciones/ver.html", prop=prop, items=items,
                           ingresos=ingresos, comision=comision, neto=neto,
                           conceptos=conceptos, neto_final=neto_final,
                           neto_letras=pesos_letras(neto_final), mes=mes, anio=anio,
                           meses=MESES_ES, a=a, liq=liq, hoy=hoy,
                           individual=bool(contrato_id),
                           fact=request.args.get("fact"),
                           facturador_habilitado=facturador.habilitado())


@liquidaciones_bp.route("/<int:liq_id>/facturar-honorarios", methods=["POST"])
@login_required
def facturar_honorarios(liq_id):
    """Confirma y emite la factura de honorarios cuando la comisión está bajo el mínimo."""
    liq = db.session.get(Liquidacion, liq_id) or abort(404)
    prop = db.session.get(Persona, liq.propietario_id)
    _facturar_honorarios(liq, prop, confirmar=True)
    return redirect(url_for("liquidaciones.ver", pid=liq.propietario_id,
                            mes=liq.periodo_mes, anio=liq.periodo_anio,
                            contrato=liq.contrato_id) if liq.contrato_id else
                    url_for("liquidaciones.ver", pid=liq.propietario_id,
                            mes=liq.periodo_mes, anio=liq.periodo_anio))


def _leer_conceptos():
    """Lee las líneas de 'Otros conceptos' del form → lista de (descripción, monto).
    El signo lo da 'concepto_signo' (+/-); el monto se ingresa positivo."""
    descs = request.form.getlist("concepto_desc")
    montos = request.form.getlist("concepto_monto")
    signos = request.form.getlist("concepto_signo")
    out = []
    for i, d in enumerate(descs):
        d = (d or "").strip()
        m = parse_num(montos[i]) if i < len(montos) else None
        if not d or m is None:
            continue
        m = abs(float(m))
        if i < len(signos) and signos[i] == "-":
            m = -m
        out.append((d, round(m, 2)))
    return out


@liquidaciones_bp.route("/generar", methods=["POST"])
@login_required
def generar():
    pid = parse_num(request.form.get("propietario_id"), entero=True)
    mes = parse_num(request.form.get("mes"), entero=True)
    anio = parse_num(request.form.get("anio"), entero=True)
    contrato_id = parse_num(request.form.get("contrato_id"), entero=True)
    prop = db.session.get(Persona, pid) or abort(404)

    pagos = _pagos_periodo(pid, mes, anio, contrato_id=contrato_id, solo_pendientes=True)
    if not pagos:
        flash("No hay cobros pendientes de liquidar en ese período.", "error")
        return redirect(url_for("liquidaciones.gestionar", pid=pid, mes=mes, anio=anio))

    # Anti doble-generación: un doble clic, F5 sobre el POST o dos pestañas no debe
    # crear dos liquidaciones (y, peor, disparar dos facturas de honorarios reales
    # al Facturador) para los mismos cobros. Mismo mecanismo que cobros/abonar.
    if not reservar("liquidacion-generar", request.form.get("idem")):
        flash("Esa liquidación ya se había generado: no la dupliqué.", "ok")
        return redirect(url_for("liquidaciones.ver", pid=pid, mes=mes, anio=anio,
                                contrato=contrato_id))

    _, ingresos, comision, neto = _detalle(pagos)
    conceptos = _leer_conceptos()
    neto_final = round(neto + sum(m for _d, m in conceptos), 2)
    a = Ajustes.get()
    liq = Liquidacion(numero=a.siguiente_liquidacion(), propietario_id=pid,
                      periodo_mes=mes, periodo_anio=anio, contrato_id=contrato_id,
                      fecha=date.today(), total_ingresos=ingresos,
                      total_comision=comision, total_neto=neto_final,
                      moneda=pagos[0].moneda or "Pesos")
    db.session.add(liq)
    db.session.flush()
    for desc, monto in conceptos:
        db.session.add(ConceptoLiquidacion(liquidacion_id=liq.id, descripcion=desc, monto=monto))
    for p in pagos:
        p.pagado_al_propietario = date.today()
    db.session.commit()

    # Emisión automática de la factura de honorarios al propietario.
    fact = _facturar_honorarios(liq, prop)

    if contrato_id:
        flash(f"Liquidación individual {liq.numero} generada.", "ok")
        return redirect(url_for("liquidaciones.ver", pid=pid, mes=mes, anio=anio,
                                contrato=contrato_id, fact=fact))
    flash(f"Liquidación {liq.numero} generada (todas juntas) para {prop.nombre}.", "ok")
    return redirect(url_for("liquidaciones.ver", pid=pid, mes=mes, anio=anio, fact=fact))


# --------------------------------------------------------------------------- #
#  Resumen mensual (todos los inmuebles, cobrados o no)
# --------------------------------------------------------------------------- #
@liquidaciones_bp.route("/resumen/<int:pid>")
@login_required
def resumen(pid):
    prop = db.session.get(Persona, pid) or abort(404)
    hoy = date.today()
    mes = parse_num(request.args.get("mes"), entero=True) or hoy.month
    anio = parse_num(request.args.get("anio"), entero=True) or hoy.year

    filas, tot_alq, tot_com, tot_neto, tot_pend = [], 0.0, 0.0, 0.0, 0.0
    for c in Contrato.query.filter_by(estado="Vigente").all():
        prop_id = c.propietario_id or (c.inmueble.propietario_id if c.inmueble else None)
        if prop_id != pid:
            continue
        pago = next((p for p in c.pagos
                     if p.periodo_mes == mes and p.periodo_anio == anio
                     and not p.anulado), None)
        pct = _comision_pct(c)
        if pago and float(pago.pagado or 0) > 0:
            alq = float(pago.precio_alquiler or 0)
            com = round(alq * pct / 100.0, 2)
            # Gastos extra trasladados (agua, expensas...): se suman al neto tal
            # cual, sin comisión -- misma regla que liquidaciones._detalle().
            gastos_trasl = [g for g in pago.gastos if g.trasladar_liquidacion]
            extras = round(sum(float(g.monto or 0) for g in gastos_trasl), 2)
            gastos = [dict(descripcion=g.descripcion or "Gasto",
                           monto=round(float(g.monto or 0), 2)) for g in gastos_trasl]
            neto = round(alq - com + extras, 2)
            estado = "Cobrado"
            tot_alq += alq; tot_com += com; tot_neto += neto
        else:
            alq = float(c.precio_actual or c.precio_inicial or 0)
            com = neto = extras = 0.0
            gastos = []
            estado = "Pendiente"
            tot_pend += alq
        filas.append(dict(c=c, estado=estado, alquiler=alq, pct=pct,
                          comision=com, extras=extras, gastos=gastos, neto=neto))
    filas.sort(key=lambda f: f["estado"])

    a = Ajustes.get()
    return render_template("liquidaciones/resumen.html", prop=prop, filas=filas,
                           mes=mes, anio=anio, meses=MESES_ES, a=a, hoy=hoy,
                           tot_alq=tot_alq, tot_com=tot_com, tot_neto=tot_neto,
                           tot_pend=tot_pend, neto_letras=pesos_letras(tot_neto))
