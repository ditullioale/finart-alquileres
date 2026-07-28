"""API JSON para el front en React (islas).

Convención: rutas bajo /api que devuelven JSON. Usan la misma sesión (cookie)
y protección CSRF que el resto de la app. Los GET no requieren token; los POST
lo reciben en el header X-CSRFToken (el front lo agrega automáticamente).
"""
from datetime import date

from flask import Blueprint, jsonify, request, url_for
from flask_login import login_required

from .. import db
from ..models import Contrato
from ..utils import MESES_ES, link_whatsapp, whatsapp_valido

api_bp = Blueprint("api", __name__, url_prefix="/api")


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
