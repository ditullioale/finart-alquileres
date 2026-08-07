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


def _api_prefix() -> str:
    """Prefijo (versionado) de la API del Facturador. Por defecto '/api'; se puede
    apuntar a '/api/v1' con FACTURADOR_API_PREFIX cuando el Facturador lo exponga,
    sin tocar código. Ver FINART_INTEGRACION_API.md."""
    p = (os.environ.get("FACTURADOR_API_PREFIX") or "/api").strip()
    if not p.startswith("/"):
        p = "/" + p
    return p.rstrip("/")


def _api(path: str) -> str:
    """URL completa de un endpoint de la API del Facturador."""
    return f"{_base_url()}{_api_prefix()}{path}"


def _timeout() -> float:
    try:
        return float(os.environ.get("FACTURADOR_TIMEOUT", "20"))
    except (TypeError, ValueError):
        return 20.0


def _reintentos() -> int:
    """Cantidad de REINTENTOS ante fallas transitorias (además del primer intento)."""
    try:
        return max(0, int(os.environ.get("FACTURADOR_RETRIES", "2")))
    except (TypeError, ValueError):
        return 2


def _dormir(segundos: float):
    # En pruebas no dormimos, para que la batería siga siendo rápida.
    if os.environ.get("TESTING"):
        return
    import time
    time.sleep(segundos)


def _post_con_reintentos(url, **kw):
    """POST con reintentos SOLO ante fallas transitorias (error de red / timeout /
    HTTP 5xx). Nunca reintenta un 4xx: son respuestas deterministas (p. ej. 422 por
    datos inválidos) y reintentar no cambiaría el resultado. Pensado para operaciones
    fiscales: se acompaña de una Idempotency-Key para que un reintento no emita dos
    veces. Devuelve la Response; si se agotan los intentos por red, relanza la
    excepción de requests."""
    intentos = _reintentos() + 1
    backoff = 0.5
    ultima_exc = None
    for i in range(intentos):
        try:
            r = requests.post(url, timeout=_timeout(), **kw)
        except requests.RequestException as exc:
            ultima_exc = exc
        else:
            if r.status_code < 500:
                return r            # éxito o error determinista: no reintentar
            ultima_exc = None       # 5xx transitorio: se puede reintentar
            if i == intentos - 1:
                return r            # se acabaron los intentos: devolver el 5xx
        if i < intentos - 1:
            _dormir(backoff)
            backoff *= 2            # 0.5s, 1s, 2s...
    raise ultima_exc                # se agotaron los intentos por error de red


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
            _api("/emisores"),
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
    # Idempotency-Key formal (Fase 5.4): identifica la operación fiscal de forma
    # única. Con los reintentos (5.6), garantiza que un reintento no emita dos veces.
    headers = dict(_headers(ajustes))
    headers["Idempotency-Key"] = referencia_externa(liq)
    try:
        r = _post_con_reintentos(
            _api("/integracion/liquidacion"),
            json=payload,
            headers=headers,
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
        _api("/lotes"),
        files={"archivo": (nombre, contenido, content_type or "application/octet-stream")},
        headers=_headers(),
        timeout=_timeout(),
    )


def listar_transferencias():
    return requests.get(
        _api("/transferencias"), headers=_headers(), timeout=_timeout()
    )


def actualizar_transferencia(transferencia_id: int, payload: dict):
    return requests.patch(
        _api(f"/transferencias/{transferencia_id}"),
        json=payload,
        headers=_headers(),
        timeout=_timeout(),
    )


def facturar_transferencia(transferencia_id: int, confirmar: bool = False):
    return requests.post(
        _api(f"/transferencias/{transferencia_id}/facturar"),
        params={"confirmar": "true" if confirmar else "false"},
        headers=_headers(),
        timeout=_timeout(),
    )


def facturar_transferencias(ids: list, confirmar_bajo_minimo: bool = False):
    return requests.post(
        _api("/transferencias/facturar"),
        json={"transferencia_ids": ids, "confirmar_bajo_minimo": confirmar_bajo_minimo},
        headers=_headers(),
        timeout=_timeout(),
    )


def listar_facturas():
    return requests.get(_api("/facturas"), headers=_headers(), timeout=_timeout())


def buscar_comprobante(referencia_ext: str, ajustes=None) -> dict:
    """Reconciliación (Fase 6.3): busca en el Facturador un comprobante ya emitido
    para esa referencia externa. Sirve para resolver liquidaciones que quedaron
    'pendientes'/'error' cuando en realidad la factura sí se emitió (p. ej. un timeout
    tras el cual ARCA devolvió CAE).

    Devuelve {"estado": "emitida", "factura": {...}} si lo encuentra emitido,
    {"estado": "no_encontrada"} si no está, o {"estado": "error"} si no se pudo
    consultar. No lanza excepciones.

    Nota: hoy filtra sobre el listado de /facturas del lado del gestor. Lo ideal es
    que el Facturador exponga una consulta directa por referencia_externa (documentado
    en FINART_INTEGRACION_API.md)."""
    if not habilitado():
        return {"estado": "deshabilitado"}
    # 1) Consulta directa por referencia (endpoint dedicado del Facturador). Si aún no
    #    está desplegado (404) o falla, se cae al listado como respaldo.
    try:
        r = requests.get(_api("/integracion/liquidacion"),
                         params={"referencia_externa": referencia_ext},
                         headers=_headers(ajustes), timeout=_timeout())
        if r.ok:
            data = r.json()
            if isinstance(data, dict) and data.get("estado") == "emitida" and data.get("factura"):
                return {"estado": "emitida", "factura": data["factura"]}
    except (requests.RequestException, ValueError):
        pass
    # 2) Respaldo: buscar en el listado de /facturas y hacer el match acá.
    try:
        r = requests.get(_api("/facturas"), headers=_headers(ajustes), timeout=_timeout())
        if not r.ok:
            return {"estado": "error"}
        data = r.json()
    except (requests.RequestException, ValueError):
        return {"estado": "error"}
    facturas = data if isinstance(data, list) else (data.get("facturas") or data.get("items") or [])
    for f in facturas:
        if not isinstance(f, dict):
            continue
        ref = f.get("referencia_externa") or f.get("referencia") or f.get("external_ref")
        estado = (f.get("estado") or "").lower()
        if ref == referencia_ext and (estado == "emitida" or f.get("cae")):
            return {"estado": "emitida", "factura": f}
    return {"estado": "no_encontrada"}


def factura_pdf(factura_id: int):
    return requests.get(
        _api(f"/facturas/{factura_id}/pdf"), headers=_headers(), timeout=_timeout()
    )
