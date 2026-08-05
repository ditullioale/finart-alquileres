"""Cliente de integración con el Facturador ARCA (multiempresa).

- Cada inmobiliaria factura con **su** emisor. El gestor manda el token del emisor
  (guardado cifrado en Ajustes) en el header Authorization de cada request.
- Si la inmobiliaria no tiene emisor propio configurado, no se manda token y el
  facturador usa su "emisor por defecto" (compatibilidad con una sola empresa).
- La integración es best-effort: nunca lanza excepciones hacia la vista.
"""
from __future__ import annotations

import base64
import os
from decimal import Decimal

import requests

CONCEPTO_DEFECTO = "HONORARIOS PROFESIONALES"


def _solo_digitos(v) -> str:
    return "".join(ch for ch in str(v or "") if ch.isdigit())


def _base_url() -> str:
    return (os.environ.get("FACTURADOR_URL") or "").rstrip("/")


def _timeout() -> float:
    try:
        return float(os.environ.get("FACTURADOR_TIMEOUT", "20"))
    except (TypeError, ValueError):
        return 20.0


def habilitado() -> bool:
    """La integración está activa solo si se configuró la URL del facturador."""
    return bool(_base_url())


def _headers(ajustes=None) -> dict:
    """Header de autenticación con el token del emisor de la inmobiliaria actual."""
    try:
        if ajustes is None:
            from .models import Ajustes
            ajustes = Ajustes.get()
        token = ajustes.get_facturador_token() if ajustes else None
        return {"Authorization": f"Bearer {token}"} if token else {}
    except Exception:
        return {}


def inmobiliaria_autorizada(ajustes) -> bool:
    """La inmobiliaria puede facturar si tiene su emisor propio, o es la "por defecto".

    - Con emisor propio (token cargado) → sí.
    - Si hay FACTURADOR_CUIT y coincide con su CUIT → sí (usa el emisor por defecto).
    - Si no hay FACTURADOR_CUIT configurado → sin restricción (deploy de una empresa).
    """
    if ajustes and getattr(ajustes, "facturador_configurado", False):
        return True
    autorizado = _solo_digitos(os.environ.get("FACTURADOR_CUIT"))
    if not autorizado:
        return True
    return _solo_digitos(ajustes.cuit if ajustes else "") == autorizado


def referencia_externa(liq) -> str:
    """Clave idempotente: identifica de forma única a la liquidación."""
    return f"gestor:{liq.inmobiliaria_id}:{liq.numero}"


def registrar_emisor(
    ajustes,
    *,
    cert_bytes: bytes | None,
    key_bytes: bytes | None,
    punto_venta: int,
    tipo_comprobante: int,
    arca_mode: str,
    razon_social: str | None = None,
    consultar_padron: bool = True,
) -> dict:
    """Registra/actualiza el emisor de esta inmobiliaria en el facturador.

    Devuelve {"ok": True, "token": ...} o {"ok": False, "error": ...}.
    """
    if not habilitado():
        return {"ok": False, "error": "El facturador no está configurado (FACTURADOR_URL)."}
    admin = os.environ.get("FACTURADOR_ADMIN_TOKEN")
    if not admin:
        return {"ok": False, "error": "Falta FACTURADOR_ADMIN_TOKEN en el servidor del gestor."}
    payload = {
        "cuit": _solo_digitos(ajustes.cuit),
        "razon_social": razon_social or (ajustes.nombre if ajustes else None),
        "punto_venta": punto_venta,
        "tipo_comprobante": tipo_comprobante,
        "arca_mode": arca_mode,
        "consultar_padron": consultar_padron,
        "cert_b64": base64.b64encode(cert_bytes).decode() if cert_bytes else None,
        "key_b64": base64.b64encode(key_bytes).decode() if key_bytes else None,
    }
    try:
        r = requests.post(
            f"{_base_url()}/api/emisores",
            json=payload,
            headers={"X-Admin-Token": admin},
            timeout=_timeout(),
        )
    except requests.RequestException as exc:
        return {"ok": False, "error": f"No se pudo contactar al facturador: {exc}"}
    if r.status_code == 401:
        return {"ok": False, "error": "El facturador rechazó el token de administrador."}
    if not r.ok:
        try:
            detalle = r.json().get("detail")
        except ValueError:
            detalle = None
        return {"ok": False, "error": detalle or f"El facturador respondió {r.status_code}."}
    data = r.json()
    return {"ok": True, "token": data.get("token"), "emisor": data.get("emisor")}


def facturar_liquidacion(liq, propietario, ajustes, confirmar_bajo_minimo: bool = False) -> dict:
    """Pide al facturador emitir la factura de honorarios de una liquidación."""
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
            headers=_headers(ajustes),
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
#  Proxy de la pantalla "Facturador" (devuelven la Response de requests tal cual).
# --------------------------------------------------------------------------- #
def subir_resumen(nombre: str, contenido: bytes, content_type: str):
    return requests.post(
        f"{_base_url()}/api/lotes",
        files={"archivo": (nombre, contenido, content_type or "application/octet-stream")},
        headers=_headers(),
        timeout=_timeout(),
    )


def listar_transferencias():
    return requests.get(
        f"{_base_url()}/api/transferencias", headers=_headers(), timeout=_timeout()
    )


def actualizar_transferencia(transferencia_id: int, payload: dict):
    return requests.patch(
        f"{_base_url()}/api/transferencias/{transferencia_id}",
        json=payload,
        headers=_headers(),
        timeout=_timeout(),
    )


def facturar_transferencia(transferencia_id: int, confirmar: bool = False):
    return requests.post(
        f"{_base_url()}/api/transferencias/{transferencia_id}/facturar",
        params={"confirmar": "true" if confirmar else "false"},
        headers=_headers(),
        timeout=_timeout(),
    )


def facturar_transferencias(ids: list, confirmar_bajo_minimo: bool = False):
    return requests.post(
        f"{_base_url()}/api/transferencias/facturar",
        json={"transferencia_ids": ids, "confirmar_bajo_minimo": confirmar_bajo_minimo},
        headers=_headers(),
        timeout=_timeout(),
    )


def listar_facturas():
    return requests.get(f"{_base_url()}/api/facturas", headers=_headers(), timeout=_timeout())


def factura_pdf(factura_id: int):
    return requests.get(
        f"{_base_url()}/api/facturas/{factura_id}/pdf", headers=_headers(), timeout=_timeout()
    )
