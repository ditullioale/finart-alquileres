"""Cliente de integración con el Facturador ARCA.

Cuando se genera una liquidación al propietario, la inmobiliaria emite una factura
de honorarios (por la comisión) al propietario. Esa emisión la hace el servicio
externo `facturador-arca` vía su endpoint POST /api/integracion/liquidacion.

La integración es *best-effort*: si el facturador no está configurado o no responde,
la liquidación se genera igual y se informa el detalle por pantalla. Nunca lanza
excepciones hacia la vista.
"""
from __future__ import annotations

import os
from decimal import Decimal

import requests

# Concepto por defecto de la factura de honorarios.
CONCEPTO_DEFECTO = "HONORARIOS PROFESIONALES"


def habilitado() -> bool:
    """La integración está activa solo si se configuró la URL del facturador."""
    return bool(_base_url())


def _base_url() -> str:
    return (os.environ.get("FACTURADOR_URL") or "").rstrip("/")


def _timeout() -> float:
    try:
        return float(os.environ.get("FACTURADOR_TIMEOUT", "20"))
    except (TypeError, ValueError):
        return 20.0


def referencia_externa(liq) -> str:
    """Clave idempotente: identifica de forma única a la liquidación."""
    return f"gestor:{liq.inmobiliaria_id}:{liq.numero}"


def facturar_liquidacion(liq, propietario, ajustes, confirmar_bajo_minimo: bool = False) -> dict:
    """Pide al facturador emitir la factura de honorarios de una liquidación.

    Devuelve un dict con al menos la clave ``estado``:
    ``emitida`` | ``error`` | ``requiere_confirmacion`` | ``deshabilitado`` | ``sin_cuit``.
    """
    if not habilitado():
        return {"estado": "deshabilitado"}
    if not (propietario and propietario.cuit):
        return {"estado": "sin_cuit"}

    payload = {
        "receptor_cuit": propietario.cuit,
        "importe": str(Decimal(liq.total_comision or 0)),
        "fecha": (liq.fecha or None).isoformat() if liq.fecha else None,
        "referencia_externa": referencia_externa(liq),
        "emisor_cuit": (ajustes.cuit if ajustes else None),
        "concepto_descripcion": os.environ.get("FACTURA_CONCEPTO", CONCEPTO_DEFECTO),
        "razon_social": propietario.nombre,
        "domicilio": propietario.domicilio,
        "confirmar_bajo_minimo": confirmar_bajo_minimo,
    }
    try:
        r = requests.post(
            f"{_base_url()}/api/integracion/liquidacion",
            json=payload,
            timeout=_timeout(),
        )
    except requests.RequestException as exc:
        return {"estado": "error", "mensaje": f"No se pudo contactar al facturador: {exc}"}

    if r.status_code == 422:
        return {"estado": "error", "mensaje": "Datos inválidos para facturar (revisá el CUIT)."}
    if not r.ok:
        return {"estado": "error", "mensaje": f"El facturador respondió {r.status_code}."}
    try:
        return r.json()
    except ValueError:
        return {"estado": "error", "mensaje": "Respuesta inesperada del facturador."}


# --------------------------------------------------------------------------- #
#  Proxy de la pantalla "Facturador" (resumen bancario -> transferencias -> facturas)
#
#  Estas funciones hablan con el backend del facturador y devuelven la Response
#  de requests tal cual, para que el blueprint reenvíe el JSON y el status code.
# --------------------------------------------------------------------------- #
def subir_resumen(nombre: str, contenido: bytes, content_type: str):
    return requests.post(
        f"{_base_url()}/api/lotes",
        files={"archivo": (nombre, contenido, content_type or "application/octet-stream")},
        timeout=_timeout(),
    )


def listar_transferencias():
    return requests.get(f"{_base_url()}/api/transferencias", timeout=_timeout())


def actualizar_transferencia(transferencia_id: int, payload: dict):
    return requests.patch(
        f"{_base_url()}/api/transferencias/{transferencia_id}",
        json=payload,
        timeout=_timeout(),
    )


def facturar_transferencias(ids: list, confirmar_bajo_minimo: bool = False):
    return requests.post(
        f"{_base_url()}/api/transferencias/facturar",
        json={"transferencia_ids": ids, "confirmar_bajo_minimo": confirmar_bajo_minimo},
        timeout=_timeout(),
    )


def listar_facturas():
    return requests.get(f"{_base_url()}/api/facturas", timeout=_timeout())


def factura_pdf(factura_id: int):
    return requests.get(
        f"{_base_url()}/api/facturas/{factura_id}/pdf", timeout=_timeout()
    )
