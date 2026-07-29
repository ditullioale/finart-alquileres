"""Reglas de negocio centralizadas.

Un único lugar para calcular el canon vigente, la deuda, el estado de un período
y la mora. Antes, el dashboard, cobranzas, recibos y liquidaciones repetían esta
lógica y podían diverger (un bug silencioso de plata). Estas funciones son la
fuente de verdad y están cubiertas por pruebas.
"""
from datetime import date

from .utils import q2, vencimiento


def canon_vigente(contrato):
    """Precio actual del alquiler (cae al inicial si no hay actualizado)."""
    return float(contrato.precio_actual or contrato.precio_inicial or 0)


def pago_de_periodo(contrato, mes, anio):
    """El pago de ese período (o None)."""
    return next((p for p in contrato.pagos
                 if p.periodo_mes == mes and p.periodo_anio == anio), None)


def deuda_total(contrato, excluir_id=None):
    """Suma de saldos pendientes del contrato (decimal exacto)."""
    return float(sum(q2(p.saldo) for p in contrato.pagos
                     if (p.saldo or 0) > 0 and p.id != excluir_id))


def estado_periodo(contrato, mes, anio, hoy=None):
    """Estado del alquiler de un contrato en un período dado. Fuente única para
    'esperado / pagado / saldo / estado / vencimiento / vencido / días de atraso'."""
    hoy = hoy or date.today()
    pago = pago_de_periodo(contrato, mes, anio)
    esperado = canon_vigente(contrato)
    venc = vencimiento(anio, mes, contrato.dia_vencimiento or 10)
    if pago:
        estado = pago.estado
        cobrado = float(pago.pagado or 0)
        saldo = float(pago.saldo or 0)
    else:
        estado = "Sin registrar"
        cobrado = 0.0
        saldo = esperado
    vencido = bool(estado != "Pagado" and venc and hoy > venc)
    dias_atraso = (hoy - venc).days if vencido else 0
    return dict(pago=pago, esperado=esperado, estado=estado, cobrado=cobrado,
                saldo=saldo, venc=venc, vencido=vencido, dias_atraso=dias_atraso)


def etiqueta_operativa(info):
    """Estado operativo derivado (para la bandeja de trabajo y los filtros).

    Recibe el dict de estado_periodo() y devuelve una etiqueta corta."""
    if info["estado"] == "Pagado":
        return "Pagado"
    if info["estado"] == "Parcial":
        return "Parcial"
    if info["vencido"]:
        return "Vencido 1-5" if info["dias_atraso"] <= 5 else "Vencido +5"
    return "Sin cobrar"
