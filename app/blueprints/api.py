"""API JSON para el front en React (islas).

Convención: rutas bajo /api que devuelven JSON. Usan la misma sesión (cookie)
y protección CSRF que el resto de la app. Los GET no requieren token; los POST
lo reciben en el header X-CSRFToken (el front lo agrega automáticamente).
"""
import json
from datetime import date, timedelta

from flask import Blueprint, jsonify, request, url_for
from flask_login import login_required
from sqlalchemy.orm import joinedload, selectinload

from .. import db
from ..models import Contrato, Persona, Inmueble, Pago, GasEstado
from ..utils import (MESES_ES, link_whatsapp, whatsapp_valido, normalizar_whatsapp,
                     proximo_ajuste, vencimiento)

api_bp = Blueprint("api", __name__, url_prefix="/api")

_BCRA_SIT = {
    1: "Normal / al día", 2: "Riesgo bajo (seguimiento especial)",
    3: "Riesgo medio (con problemas)", 4: "Riesgo alto (alto riesgo de insolvencia)",
    5: "Irrecuperable", 6: "Irrecuperable por disposición técnica",
}


@api_bp.route("/bcra/<cuit>")
@login_required
def bcra(cuit):
    """Situación crediticia de un CUIT según la Central de Deudores del BCRA
    (API pública y gratuita). Devuelve la peor situación y el detalle por entidad
    del período más reciente."""
    import ssl
    import urllib.request
    import urllib.error

    c = "".join(ch for ch in (cuit or "") if ch.isdigit())
    if len(c) != 11:
        return jsonify(ok=False, error="El CUIT/CUIL debe tener 11 dígitos."), 400

    url = f"https://api.bcra.gob.ar/CentralDeDeudores/v1.0/Deudas/{c}"

    def _fetch(ctx):
        req = urllib.request.Request(url, headers={"User-Agent": "FINART/1.0"})
        with urllib.request.urlopen(req, timeout=12, context=ctx) as r:
            return json.loads(r.read().decode("utf-8"))

    try:
        try:
            data = _fetch(None)                      # validando certificado
        except ssl.SSLError:
            unctx = ssl.create_default_context()      # fallback sin verificar
            unctx.check_hostname = False
            unctx.verify_mode = ssl.CERT_NONE
            data = _fetch(unctx)
    except urllib.error.HTTPError as e:
        if e.code in (400, 404):
            return jsonify(ok=True, sin_datos=True, cuit=c)
        return jsonify(ok=False, error=f"El BCRA respondió con error {e.code}."), 502
    except Exception:
        return jsonify(ok=False, error="No se pudo consultar el BCRA en este momento."), 502

    res = (data or {}).get("results") or {}
    periodos = res.get("periodos") or []
    if not periodos:
        return jsonify(ok=True, sin_datos=True, cuit=c,
                       denominacion=res.get("denominacion"))
    per = periodos[0]
    ents = per.get("entidades") or []
    peor = max((e.get("situacion") or 1) for e in ents) if ents else 1
    total = sum(float(e.get("monto") or 0) for e in ents)
    entidades = [dict(
        entidad=e.get("entidad"), situacion=e.get("situacion") or 1,
        situacion_texto=_BCRA_SIT.get(e.get("situacion") or 1, str(e.get("situacion"))),
        monto=float(e.get("monto") or 0), dias_atraso=e.get("diasAtrasoPago") or 0,
    ) for e in ents]
    entidades.sort(key=lambda x: (-x["situacion"], -x["monto"]))
    return jsonify(ok=True, cuit=c, denominacion=res.get("denominacion"),
                   periodo=per.get("periodo"), peor_situacion=peor,
                   peor_situacion_texto=_BCRA_SIT.get(peor, str(peor)),
                   total=total, entidades=entidades)


def _simbolo(moneda):
    return "US$" if (moneda or "").strip().lower().startswith("d") else "$"


def _money(n):
    return f"{float(n or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@api_bp.route("/cobranzas")
@login_required
def cobranzas():
    """Datos del panel de cobranzas de un mes: totales + filas."""
    hoy = date.today()
    mes = request.args.get("mes", type=int) or hoy.month
    anio = request.args.get("anio", type=int) or hoy.year

    filas = []
    tot_esp = tot_cob = tot_pen = 0.0
    _cs = (Contrato.query.filter_by(estado="Vigente")
           .options(joinedload(Contrato.inquilino), joinedload(Contrato.propietario),
                    joinedload(Contrato.inmueble), selectinload(Contrato.pagos)).all())
    for c in _cs:
        pago = next((p for p in c.pagos
                     if p.periodo_mes == mes and p.periodo_anio == anio), None)
        esperado = float(c.precio_actual or c.precio_inicial or 0)
        if pago:
            estado = pago.estado
            cobrado = float(pago.pagado or 0)
            saldo = float(pago.saldo or 0)
        else:
            estado = "Sin cobrar"
            cobrado = 0.0
            saldo = esperado
        tot_esp += esperado
        tot_cob += cobrado
        if estado != "Pagado":
            tot_pen += saldo

        inq = c.inquilino
        nombre = inq.nombre if inq else ""
        prox_nro = (max((p.numero or 0) for p in c.pagos) + 1) if c.pagos else 1
        msj = (f"Hola {nombre}! Te escribo por el alquiler de {c.inmueble.direccion}. "
               f"El período {MESES_ES[mes]} {anio} figura {estado.lower()}"
               + (f" (falta ${saldo:,.2f})" if estado == "Parcial" else "")
               + ". ¿Podés confirmarme cuándo lo abonás? ¡Gracias!")
        wa = link_whatsapp(inq.telefono, msj) if inq else None

        venc = vencimiento(anio, mes, c.dia_vencimiento or 10)
        filas.append(dict(
            cid=c.id, inquilino=nombre,
            inmueble=c.inmueble.direccion if c.inmueble else "",
            localidad=(c.inmueble.localidad if c.inmueble else "") or "",
            codigo=(c.inmueble.codigo if c.inmueble else "") or "",
            propietario=c.propietario.nombre if c.propietario else "",
            moneda=c.moneda or "Pesos", esperado=esperado, cobrado=cobrado,
            saldo=saldo, estado=estado, prox_nro=prox_nro,
            venc=venc.isoformat(), mora_pct=float(c.mora_diaria_pct or 0),
            pago_id=pago.id if pago else None,
            recibo_url=url_for("recibos.recibo", pid=pago.id) if pago else None,
            wa=wa, gas=(c.inmueble.cuenta_gas if c.inmueble else None),
        ))
    filas.sort(key=lambda f: (f["estado"] == "Pagado", f["inquilino"].lower()))

    return jsonify(
        mes=mes, anio=anio, meses=MESES_ES,
        anios=list(range(hoy.year - 4, hoy.year + 2)),
        formas=["Efectivo", "Transferencia", "Transferencia prop / inmo", "Cheque", "Otro"],
        totales=dict(esperado=tot_esp, cobrado=tot_cob, pendiente=tot_pen),
        filas=filas,
    )


# --------------------------------------------------------------------------- #
#  Listados (Sprint 2)
# --------------------------------------------------------------------------- #
@api_bp.route("/personas")
@login_required
def personas():
    filas = []
    for p in Persona.query.options(selectinload(Persona.inmuebles)).order_by(Persona.nombre).all():
        wa = link_whatsapp(p.telefono, f"Hola {p.nombre}!") if p.telefono else None
        filas.append(dict(
            id=p.id, nombre=p.nombre or "", dni=p.dni or "", cuit=p.cuit or "",
            roles=p.roles_texto, es_propietario=bool(p.es_propietario),
            es_inquilino=bool(p.es_inquilino),
            telefono=p.telefono or "", email=p.email or "", wa=wa,
            tiene_inmuebles=bool(p.inmuebles),
            editar_url=url_for("personas.editar", pid=p.id),
        ))
    return jsonify(filas=filas)


@api_bp.route("/inmuebles")
@login_required
def inmuebles():
    estados = ["Disponible", "Alquilado", "Reservado"]
    filas = []
    for i in (Inmueble.query.options(joinedload(Inmueble.propietario),
              selectinload(Inmueble.contratos)).order_by(Inmueble.direccion).all()):
        precio = (f"{_simbolo(i.moneda)} {_money(i.precio_referencia)}"
                  if i.precio_referencia else "—")
        filas.append(dict(
            id=i.id, codigo=i.codigo or "", direccion=i.direccion or "",
            tipo=i.tipo or "", localidad=i.localidad or "", estado=i.estado or "",
            propietario=(i.propietario.nombre if i.propietario else ""),
            precio=float(i.precio_referencia or 0), precio_txt=precio,
            tiene_contratos=bool(i.contratos),
            editar_url=url_for("inmuebles.editar", iid=i.id),
        ))
    return jsonify(estados=estados, filas=filas)


@api_bp.route("/contratos")
@login_required
def contratos():
    estados = ["Vigente", "Rescindido", "Finalizado"]
    filas = []
    _cs = (Contrato.query.options(joinedload(Contrato.inquilino),
           joinedload(Contrato.propietario), joinedload(Contrato.inmueble))
           .order_by(Contrato.fecha_inicio.desc()).all())
    for c in _cs:
        inq = c.inquilino
        if c.metodo_ajuste == "indice":
            ajuste = c.indice_tipo or "Índice"
        elif c.metodo_ajuste == "porcentaje":
            ajuste = f"{c.porcentaje_ajuste}%"
        else:
            ajuste = "—"
        wa = None
        if inq:
            msj = (f"Hola {inq.nombre}! Te escribo por el alquiler de "
                   f"{c.inmueble.direccion if c.inmueble else ''}.")
            wa = link_whatsapp(inq.telefono, msj)
        filas.append(dict(
            id=c.id, numero=c.numero or "",
            inquilino=(inq.nombre if inq else ""),
            propietario=(c.propietario.nombre if c.propietario else ""),
            inmueble=(c.inmueble.direccion if c.inmueble else ""),
            localidad=((c.inmueble.localidad if c.inmueble else "") or ""),
            codigo=((c.inmueble.codigo if c.inmueble else "") or ""),
            precio=float(c.precio_actual or 0),
            precio_txt=f"{_simbolo(c.moneda)} {_money(c.precio_actual)}",
            ajuste=ajuste, estado=c.estado or "",
            vigente=(c.estado == "Vigente"),
            tiene_documento=bool(c.documento_html), wa=wa,
            ver_url=url_for("contratos.ver", cid=c.id),
            cobrar_url=url_for("cobros.nuevo", cid=c.id),
            documento_url=url_for("contratos.documento", cid=c.id),
        ))
    return jsonify(estados=estados, filas=filas)


# --------------------------------------------------------------------------- #
#  Eliminar / rescindir desde las listas React (JSON, con las mismas guardas)
# --------------------------------------------------------------------------- #
@api_bp.route("/personas/<int:pid>/eliminar", methods=["POST"])
@login_required
def personas_eliminar(pid):
    p = db.session.get(Persona, pid)
    if not p:
        return jsonify(ok=False, error="No se encontró la persona."), 404
    if p.inmuebles:
        return jsonify(ok=False, error="No se puede eliminar: tiene inmuebles asociados."), 409
    db.session.delete(p)
    db.session.commit()
    return jsonify(ok=True)


@api_bp.route("/inmuebles/<int:iid>/eliminar", methods=["POST"])
@login_required
def inmuebles_eliminar(iid):
    i = db.session.get(Inmueble, iid)
    if not i:
        return jsonify(ok=False, error="No se encontró el inmueble."), 404
    if i.contratos:
        return jsonify(ok=False, error="No se puede eliminar: tiene contratos asociados."), 409
    db.session.delete(i)
    db.session.commit()
    return jsonify(ok=True)


@api_bp.route("/contratos/<int:cid>/eliminar", methods=["POST"])
@login_required
def contratos_eliminar(cid):
    c = db.session.get(Contrato, cid)
    if not c:
        return jsonify(ok=False, error="No se encontró el contrato."), 404
    if c.pagos:
        return jsonify(ok=False, error="No se puede eliminar: tiene pagos registrados. Usá Rescindir."), 409
    if c.inmueble and c.inmueble.estado == "Alquilado":
        c.inmueble.estado = "Disponible"
    db.session.delete(c)
    db.session.commit()
    return jsonify(ok=True)


@api_bp.route("/contratos/<int:cid>/rescindir", methods=["POST"])
@login_required
def contratos_rescindir(cid):
    c = db.session.get(Contrato, cid)
    if not c:
        return jsonify(ok=False, error="No se encontró el contrato."), 404
    c.estado = "Rescindido"
    hoy = date.today()
    if not c.fecha_fin or c.fecha_fin > hoy:
        c.fecha_fin = hoy
    if c.inmueble and c.inmueble.estado == "Alquilado":
        c.inmueble.estado = "Disponible"
    db.session.commit()
    return jsonify(ok=True, estado="Rescindido")


# --------------------------------------------------------------------------- #
#  Sprint 3 — Panel de inicio y control de gas
# --------------------------------------------------------------------------- #
@api_bp.route("/dashboard")
@login_required
def dashboard():
    hoy = date.today()
    stats = dict(
        personas=Persona.query.count(),
        propietarios=Persona.query.filter_by(es_propietario=True).count(),
        inquilinos=Persona.query.filter_by(es_inquilino=True).count(),
        inmuebles=Inmueble.query.count(),
        alquilados=Inmueble.query.filter_by(estado="Alquilado").count(),
        contratos_vigentes=Contrato.query.filter_by(estado="Vigente").count(),
    )
    from sqlalchemy import func
    from ..models import Aumento
    deuda = float(db.session.query(func.coalesce(func.sum(Pago.saldo), 0)).scalar() or 0)
    _cnt = dict(db.session.query(Aumento.contrato_id, func.count(Aumento.id))
                .group_by(Aumento.contrato_id).all())
    aumentos_pend = 0
    for c in Contrato.query.filter_by(estado="Vigente").all():
        if c.metodo_ajuste == "sin_ajuste" or not c.ajuste_cada_meses:
            continue
        prox = proximo_ajuste(c.fecha_inicio, c.ajuste_cada_meses, _cnt.get(c.id, 0))
        if prox and prox <= hoy:
            aumentos_pend += 1

    limite = hoy + timedelta(days=60)
    por_vencer = []
    q = (Contrato.query
         .filter(Contrato.estado == "Vigente",
                 Contrato.fecha_fin.isnot(None),
                 Contrato.fecha_fin >= hoy,
                 Contrato.fecha_fin <= limite)
         .options(joinedload(Contrato.inquilino), joinedload(Contrato.inmueble))
         .order_by(Contrato.fecha_fin).all())
    for c in q:
        dias = (c.fecha_fin - hoy).days
        por_vencer.append(dict(
            id=c.id, fecha_fin=c.fecha_fin.strftime("%d/%m/%Y"), dias=dias,
            inquilino=(c.inquilino.nombre if c.inquilino else ""),
            inmueble=(c.inmueble.direccion if c.inmueble else ""),
            precio_txt=f"{_simbolo(c.moneda)} {_money(c.precio_actual)}",
            ver_url=url_for("contratos.ver", cid=c.id),
        ))

    return jsonify(
        stats=stats,
        pendientes=dict(deuda=deuda, deuda_txt=_money(deuda),
                        aumentos=aumentos_pend, vencen=len(por_vencer)),
        por_vencer=por_vencer,
        links=dict(
            inmuebles=url_for("inmuebles.listar"),
            alquilados=url_for("inmuebles.listar", estado="Alquilado"),
            contratos=url_for("contratos.listar", estado="Vigente"),
            propietarios=url_for("personas.listar", rol="propietario"),
            inquilinos=url_for("personas.listar", rol="inquilino"),
            deuda=url_for("cobros.index"),
            aumentos=url_for("aumentos.index"),
            nuevo_contrato=url_for("contratos.nuevo"),
            generar_contrato=url_for("contratos.generador"),
            nuevo_inmueble=url_for("inmuebles.nuevo"),
        ),
    )


@api_bp.route("/gas")
@login_required
def gas():
    inmuebles = Inmueble.query.filter(Inmueble.cuenta_gas.isnot(None),
                                      Inmueble.cuenta_gas != "").all()
    estados = {g.cuenta: g for g in GasEstado.query.all()}
    filas = []
    con_deuda = 0
    deuda_total = 0.0
    ultima = None
    for inm in inmuebles:
        g = estados.get((inm.cuenta_gas or "").strip())
        cont = Contrato.query.filter_by(inmueble_id=inm.id, estado="Vigente").first()
        inquilino = cont.inquilino.nombre if (cont and cont.inquilino) else ""
        if g:
            if g.tiene_deuda:
                con_deuda += 1
                deuda_total += float(g.deuda_total or 0)
            if g.actualizado and (ultima is None or g.actualizado > ultima):
                ultima = g.actualizado
        filas.append(dict(
            inmueble_id=inm.id, direccion=inm.direccion or "", codigo=inm.codigo or "",
            editar_url=url_for("inmuebles.editar", iid=inm.id),
            inquilino=inquilino, cuenta=inm.cuenta_gas or "",
            tiene_datos=bool(g), gas_id=(g.id if g else None),
            tiene_deuda=bool(g.tiene_deuda) if g else False,
            deuda_txt=(_money(g.deuda_total) if (g and g.tiene_deuda) else None),
            vencimiento=(g.ultimo_vencimiento.strftime("%d/%m/%Y")
                         if (g and g.ultimo_vencimiento) else None),
        ))
    filas.sort(key=lambda f: (0 if f["tiene_deuda"] else 1, f["direccion"]))

    asignadas = {(i.cuenta_gas or "").strip() for i in inmuebles}
    sin_asignar = []
    for g in estados.values():
        if g.cuenta in asignadas:
            continue
        sin_asignar.append(dict(
            gas_id=g.id, cuenta=g.cuenta, titular=g.titular or "",
            direccion=g.direccion or "", tiene_deuda=bool(g.tiene_deuda),
        ))
    disponibles = [dict(id=i.id, texto=((i.codigo + " · " if i.codigo else "") + (i.direccion or "")))
                   for i in (Inmueble.query
                             .filter(db.or_(Inmueble.cuenta_gas.is_(None), Inmueble.cuenta_gas == ""))
                             .order_by(Inmueble.direccion).all())]

    return jsonify(
        filas=filas, sin_asignar=sin_asignar, disponibles=disponibles,
        total=len(inmuebles), con_deuda=con_deuda, deuda_total=deuda_total,
        deuda_total_txt=_money(deuda_total),
        actualizado=(ultima.strftime("%d/%m/%Y %H:%M") if ultima else None),
    )


@api_bp.route("/gas/estado")
@login_required
def gas_estado():
    """Facturas de una cuenta (para la ventanita 'Ver gas')."""
    cuenta = (request.args.get("cuenta") or "").strip()
    g = GasEstado.query.filter_by(cuenta=cuenta).first()
    if not g:
        return jsonify(ok=False, cuenta=cuenta)
    facturas = []
    try:
        parsed = json.loads(g.detalle) if g.detalle else []
        if isinstance(parsed, list):
            facturas = parsed
    except Exception:
        facturas = []
    return jsonify(ok=True, cuenta=g.cuenta, titular=g.titular,
                   tiene_deuda=bool(g.tiene_deuda),
                   deuda_total=float(g.deuda_total or 0),
                   deuda_total_txt=_money(g.deuda_total), facturas=facturas,
                   actualizado=(g.actualizado.strftime("%d/%m/%Y %H:%M")
                                if g.actualizado else None))


@api_bp.route("/gas/asignar", methods=["POST"])
@login_required
def gas_asignar():
    d = request.get_json(silent=True) or {}
    cuenta = (d.get("cuenta") or "").strip()
    inm = db.session.get(Inmueble, int(d.get("inmueble_id") or 0))
    if not cuenta or not inm:
        return jsonify(ok=False, error="Faltan datos."), 400
    inm.cuenta_gas = cuenta
    db.session.commit()
    return jsonify(ok=True, inmueble=inm.direccion)


@api_bp.route("/gas/<int:gid>/eliminar", methods=["POST"])
@login_required
def gas_eliminar(gid):
    g = db.session.get(GasEstado, gid)
    if not g:
        return jsonify(ok=False, error="No se encontró el suministro."), 404
    db.session.delete(g)
    db.session.commit()
    return jsonify(ok=True)


# --------------------------------------------------------------------------- #
#  Sprint 4 — Guardado de formularios (personas e inmuebles)
# --------------------------------------------------------------------------- #
def _persona_dict(p):
    return dict(id=p.id, nombre=p.nombre or "", dni=p.dni or "", cuit=p.cuit or "",
                domicilio=p.domicilio or "", localidad=p.localidad or "",
                cond_iva=p.cond_iva or "Consumidor Final",
                telefono=p.telefono or "", email=p.email or "",
                es_propietario=bool(p.es_propietario),
                es_inquilino=bool(p.es_inquilino),
                observaciones=p.observaciones or "")


@api_bp.route("/personas/nueva", methods=["GET"])
@login_required
def personas_nueva():
    """Datos iniciales para el formulario de alta."""
    return jsonify(persona=_persona_dict(Persona()))


@api_bp.route("/personas/<int:pid>", methods=["GET"])
@login_required
def personas_uno(pid):
    p = db.session.get(Persona, pid)
    if not p:
        return jsonify(ok=False, error="No se encontró la persona."), 404
    return jsonify(persona=_persona_dict(p))


@api_bp.route("/personas/guardar", methods=["POST"])
@api_bp.route("/personas/<int:pid>/guardar", methods=["POST"])
@login_required
def personas_guardar(pid=None):
    d = request.get_json(silent=True) or {}
    p = db.session.get(Persona, pid) if pid else Persona()
    if pid and not p:
        return jsonify(ok=False, error="No se encontró la persona."), 404
    nombre = (d.get("nombre") or "").strip()
    if not nombre:
        return jsonify(ok=False, error="El nombre es obligatorio."), 400
    tel = (d.get("telefono") or "").strip()
    if tel and normalizar_whatsapp(tel) is None:
        return jsonify(ok=False, error=("El teléfono no parece válido para WhatsApp. "
                                        "Cargalo con código de área.")), 400
    p.nombre = nombre
    p.dni = (d.get("dni") or "").strip()
    p.cuit = (d.get("cuit") or "").strip()
    p.domicilio = (d.get("domicilio") or "").strip()
    p.localidad = (d.get("localidad") or "").strip()
    p.cond_iva = (d.get("cond_iva") or "").strip()
    p.telefono = tel
    p.email = (d.get("email") or "").strip()
    p.es_propietario = bool(d.get("es_propietario"))
    p.es_inquilino = bool(d.get("es_inquilino"))
    p.observaciones = (d.get("observaciones") or "").strip()
    if not pid:
        db.session.add(p)
    db.session.commit()
    return jsonify(ok=True, id=p.id, redirect=url_for("personas.listar"))


TIPOS_INM = ["Casa", "Departamento", "Local", "Campo", "Cochera", "Oficina", "Terreno"]
ESTADOS_INM = ["Disponible", "Alquilado", "Reservado"]


def _num(v, entero=False):
    s = str(v or "").strip().replace(".", "").replace(",", ".")
    if s == "":
        return None
    try:
        return int(float(s)) if entero else float(s)
    except ValueError:
        return None


def _inmueble_dict(i):
    return dict(id=i.id, codigo=i.codigo or "", tipo=i.tipo or "",
                direccion=i.direccion or "", localidad=i.localidad or "",
                provincia=i.provincia or "", barrio=i.barrio or "",
                estado=i.estado or "Disponible", moneda=i.moneda or "Pesos",
                cuenta_gas=i.cuenta_gas or "", descripcion=i.descripcion or "",
                observaciones=i.observaciones or "",
                dormitorios=(i.dormitorios if i.dormitorios is not None else ""),
                banos=(i.banos if i.banos is not None else ""),
                precio_referencia=(i.precio_referencia if i.precio_referencia is not None else ""),
                comision_pct=(i.comision_pct if i.comision_pct is not None else ""),
                propietario_id=(i.propietario_id or ""))


def _opciones_inm():
    props = [dict(id=p.id, nombre=p.nombre)
             for p in Persona.query.filter_by(es_propietario=True).order_by(Persona.nombre).all()]
    return dict(propietarios=props, tipos=TIPOS_INM, estados=ESTADOS_INM)


@api_bp.route("/inmuebles/nuevo", methods=["GET"])
@login_required
def inmuebles_nuevo():
    return jsonify(inmueble=_inmueble_dict(Inmueble()), **_opciones_inm())


@api_bp.route("/inmuebles/<int:iid>", methods=["GET"])
@login_required
def inmuebles_uno(iid):
    i = db.session.get(Inmueble, iid)
    if not i:
        return jsonify(ok=False, error="No se encontró el inmueble."), 404
    return jsonify(inmueble=_inmueble_dict(i), **_opciones_inm())


@api_bp.route("/inmuebles/guardar", methods=["POST"])
@api_bp.route("/inmuebles/<int:iid>/guardar", methods=["POST"])
@login_required
def inmuebles_guardar(iid=None):
    d = request.get_json(silent=True) or {}
    i = db.session.get(Inmueble, iid) if iid else Inmueble()
    if iid and not i:
        return jsonify(ok=False, error="No se encontró el inmueble."), 404
    direccion = (d.get("direccion") or "").strip()
    if not direccion:
        return jsonify(ok=False, error="La dirección es obligatoria."), 400
    i.codigo = (d.get("codigo") or "").strip()
    i.tipo = (d.get("tipo") or "").strip()
    i.direccion = direccion
    i.localidad = (d.get("localidad") or "").strip()
    i.provincia = (d.get("provincia") or "").strip()
    i.barrio = (d.get("barrio") or "").strip()
    i.estado = (d.get("estado") or "Disponible").strip()
    i.moneda = (d.get("moneda") or "Pesos").strip()
    i.cuenta_gas = (d.get("cuenta_gas") or "").strip()
    i.descripcion = (d.get("descripcion") or "").strip()
    i.observaciones = (d.get("observaciones") or "").strip()
    i.dormitorios = _num(d.get("dormitorios"), entero=True)
    i.banos = _num(d.get("banos"), entero=True)
    i.precio_referencia = _num(d.get("precio_referencia"))
    i.comision_pct = _num(d.get("comision_pct"))
    pid = d.get("propietario_id")
    i.propietario_id = int(pid) if pid else None
    if not iid:
        db.session.add(i)
    db.session.commit()
    return jsonify(ok=True, id=i.id, redirect=url_for("inmuebles.listar"))
