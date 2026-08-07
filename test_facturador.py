"""Pruebas del cliente de integración con el Facturador ARCA (app/facturador.py).

Uso:  python test_facturador.py
No toca la red: reemplaza requests.post por un doble de prueba.
"""
import os
import sys
from datetime import date
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import facturador  # noqa: E402

_pasa, _falla, _fallos = 0, 0, []


def check(nombre, cond):
    global _pasa, _falla
    if cond:
        _pasa += 1
        print(f"  PASA  {nombre}")
    else:
        _falla += 1
        _fallos.append(nombre)
        print(f"  FALLA {nombre}")


class _RespFalsa:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._data = data or {}

    def json(self):
        return self._data


def _liq(comision="120000.00", numero="0001-00000001", inmo=1):
    return SimpleNamespace(
        inmobiliaria_id=inmo, numero=numero, fecha=date(2026, 7, 31),
        total_comision=comision, propietario_id=9,
    )


def _prop(cuit="27123456780"):
    return SimpleNamespace(nombre="PEREZ SA", cuit=cuit, domicilio="Calle 1")


def _ajustes(cuit="20111111112"):
    return SimpleNamespace(cuit=cuit)


def run():
    # habilitado() depende de FACTURADOR_URL
    os.environ.pop("FACTURADOR_URL", None)
    check("sin FACTURADOR_URL, la integración está deshabilitada", not facturador.habilitado())
    os.environ["FACTURADOR_URL"] = "http://localhost:8000/"
    check("con FACTURADOR_URL, la integración está habilitada", facturador.habilitado())

    # Versionado de la API (Fase 0.3): prefijo configurable, /api por defecto.
    os.environ.pop("FACTURADOR_API_PREFIX", None)
    check("por defecto la API usa el prefijo /api",
          facturador._api("/facturas") == "http://localhost:8000/api/facturas")
    os.environ["FACTURADOR_API_PREFIX"] = "/api/v1"
    check("se puede versionar la API a /api/v1 por variable de entorno",
          facturador._api("/facturas") == "http://localhost:8000/api/v1/facturas")
    os.environ.pop("FACTURADOR_API_PREFIX", None)

    # referencia idempotente
    check("referencia externa con inmobiliaria y número",
          facturador.referencia_externa(_liq(numero="0001-00000009", inmo=3))
          == "gestor:3:0001-00000009")

    # sin CUIT del propietario => no se llama al facturador
    check("propietario sin CUIT => estado sin_cuit",
          facturador.facturar_liquidacion(_liq(), _prop(cuit=None), _ajustes())["estado"]
          == "sin_cuit")

    # captura el payload enviado y devuelve 'emitida'
    capturado = {}

    def _post_ok(url, json=None, timeout=None, headers=None, **kw):
        capturado["url"] = url
        capturado["json"] = json
        capturado["headers"] = headers or {}
        return _RespFalsa(200, {"estado": "emitida", "factura": {"cae": "7123", "id": 5}})

    facturador.requests.post = _post_ok
    r = facturador.facturar_liquidacion(_liq(), _prop(), _ajustes())
    check("emitida: estado propagado", r["estado"] == "emitida")
    check("payload lleva la comisión como importe", capturado["json"]["importe"] == "120000.00")
    check("payload lleva el CUIT del propietario como receptor",
          capturado["json"]["receptor_cuit"] == "27123456780")
    check("payload lleva el CUIT de la inmobiliaria como emisor",
          capturado["json"]["emisor_cuit"] == "20111111112")
    check("pega al endpoint de integración",
          capturado["url"].endswith("/api/integracion/liquidacion"))
    # 5.4 — Idempotency-Key formal en la emisión.
    check("la emisión manda una Idempotency-Key",
          capturado["headers"].get("Idempotency-Key") == "gestor:1:0001-00000001")

    # 5.6 — Reintentos controlados (no reintentar a ciegas una operación fiscal).
    os.environ["TESTING"] = "1"          # sin sleeps
    os.environ["FACTURADOR_RETRIES"] = "2"
    _c = {"n": 0}

    def _post_5xx(url, **kw):
        _c["n"] += 1
        return _RespFalsa(500 if _c["n"] < 3 else 200, {"ok": True})
    facturador.requests.post = _post_5xx
    check("reintenta ante 5xx transitorio y termina en 200",
          facturador._post_con_reintentos("http://x").status_code == 200 and _c["n"] == 3)

    _c2 = {"n": 0}

    def _post_422(url, **kw):
        _c2["n"] += 1
        return _RespFalsa(422, {"detail": "datos inválidos"})
    facturador.requests.post = _post_422
    _r422 = facturador._post_con_reintentos("http://x")
    check("NO reintenta un 4xx (es determinista)",
          _r422.status_code == 422 and _c2["n"] == 1)

    _c3 = {"n": 0}

    def _post_caido(url, **kw):
        _c3["n"] += 1
        raise facturador.requests.RequestException("timeout")
    facturador.requests.post = _post_caido
    try:
        facturador._post_con_reintentos("http://x")
        _relanzo = False
    except facturador.requests.RequestException:
        _relanzo = True
    check("ante caída total de red, agota los intentos y relanza (3 intentos)",
          _relanzo and _c3["n"] == 3)

    # 6.3 — Reconciliación: buscar un comprobante ya emitido por referencia externa.
    def _get_facturas(url, headers=None, timeout=None, **kw):
        return _RespFalsa(200, [
            {"referencia_externa": "gestor:1:0001-9", "estado": "emitida", "cae": "111", "id": 9},
            {"referencia_externa": "gestor:1:otra", "estado": "emitida", "cae": "222", "id": 10}])
    facturador.requests.get = _get_facturas
    _b = facturador.buscar_comprobante("gestor:1:0001-9")
    check("reconciliación encuentra el comprobante por referencia externa",
          _b["estado"] == "emitida" and _b["factura"]["cae"] == "111")
    check("reconciliación: 'no_encontrada' si no hay match",
          facturador.buscar_comprobante("gestor:1:inexistente")["estado"] == "no_encontrada")

    # requiere_confirmacion se propaga tal cual
    facturador.requests.post = lambda *a, **k: _RespFalsa(200, {"estado": "requiere_confirmacion"})
    check("bajo mínimo => requiere_confirmacion",
          facturador.facturar_liquidacion(_liq("30000"), _prop(), _ajustes())["estado"]
          == "requiere_confirmacion")

    # error de red => estado error, nunca excepción
    def _post_falla(*a, **k):
        raise facturador.requests.RequestException("timeout")

    facturador.requests.post = _post_falla
    check("caída del facturador => estado error (sin excepción)",
          facturador.facturar_liquidacion(_liq(), _prop(), _ajustes())["estado"] == "error")

    print("\n" + "=" * 44)
    print(f"RESULTADO:  {_pasa} PASA  /  {_falla} FALLA")
    for f in _fallos:
        print("   -", f)
    print("=" * 44)
    return _falla == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
