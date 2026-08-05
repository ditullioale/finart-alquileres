"""Reglas de negocio centralizadas.

Un único lugar para calcular el canon vigente, la deuda, el estado de un período
y la mora. Antes, el dashboard, cobranzas, recibos y liquidaciones repetían esta
lógica y podían diverger (un bug silencioso de plata). Estas funciones son la
fuente de verdad y están cubiertas por pruebas.
"""
from datetime import date

from .utils import q2, vencimiento, add_months, proximo_ajuste


def _grilla_aumento(inicio, cada, hoy):
    """Grilla de aumentos desde 'inicio' cada 'cada' meses (inicio+cada, +2·cada…).
    Devuelve (corresponde, proximo):
      - corresponde: la fecha de aumento más reciente que ya llegó (<= hoy), o None
        si todavía no llegó el primero.
      - proximo: la próxima fecha de aumento (> hoy)."""
    if not inicio or not cada:
        return (None, None)
    cada = int(cada)
    prev, k = None, 1
    while k <= 3000:
        f = add_months(inicio, k * cada)
        if f > hoy:
            return (prev, f)
        prev, k = f, k + 1
    return (prev, None)


def estado_aumento(contrato, hoy=None):
    """Estado del aumento de un contrato, calculado sobre la grilla que arranca en
    la fecha de inicio (o en 'aumento_base' si se cargó una a mano). Devuelve
    dict(corresponde, proximo, pendiente). 'pendiente' es True cuando ya llegó una
    fecha de aumento y todavía NO se aplicó un aumento en/después de esa fecha."""
    hoy = hoy or date.today()
    cada = contrato.ajuste_cada_meses
    if contrato.metodo_ajuste == "sin_ajuste" or not cada:
        return {"corresponde": None, "proximo": None, "pendiente": False}
    inicio = getattr(contrato, "aumento_base", None) or contrato.fecha_inicio
    corresponde, proximo = _grilla_aumento(inicio, cada, hoy)
    pendiente = False
    if corresponde:
        aplicado = any(a.fecha_vigencia and a.fecha_vigencia >= corresponde
                       for a in (contrato.aumentos or []))
        pendiente = not aplicado
    return {"corresponde": corresponde, "proximo": proximo, "pendiente": pendiente}


def proximo_aumento(contrato, hoy=None):
    """Fecha de aumento a mostrar: la que corresponde ahora si está pendiente; si
    no, la próxima de la grilla. Se cuenta desde la fecha de inicio del contrato,
    sin depender del historial de aumentos aplicados (útil tras importar)."""
    e = estado_aumento(contrato, hoy)
    if e["pendiente"] and e["corresponde"]:
        return e["corresponde"]
    return e["proximo"]


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
