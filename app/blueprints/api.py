"""API JSON para el front en React (islas).

Convención: rutas bajo /api que devuelven JSON. Usan la misma sesión (cookie)
y protección CSRF que el resto de la app. Los GET no requieren token; los POST
lo reciben en el header X-CSRFToken (el front lo agrega automáticamente).
"""
from datetime import date

from flask import Blueprint, jsonify, request, url_for
from flask_login import login_required

from .. import db
from ..models import Contrato, Persona, Inmueble
from ..utils import MESES_ES, link_whatsapp, whatsapp_valido

api_bp = Blueprint("api", __name__, url_prefix="/api")


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
    for c in Contrato.query.filter_by(estado="Vigente").all():
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

        filas.append(dict(
            cid=c.id, inquilino=nombre,
            inmueble=c.inmueble.direccion if c.inmueble else "",
            localidad=(c.inmueble.localidad if c.inmueble else "") or "",
            codigo=(c.inmueble.codigo if c.inmueble else "") or "",
            propietario=c.propietario.nombre if c.propietario else "",
            moneda=c.moneda or "Pesos", esperado=esperado, cobrado=cobrado,
            saldo=saldo, estado=estado, prox_nro=prox_nro,
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
    for p in Persona.query.order_by(Persona.nombre).all():
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
    for i in Inmueble.query.order_by(Inmueble.direccion).all():
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
    for c in Contrato.query.order_by(Contrato.fecha_inicio.desc()).all():
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
