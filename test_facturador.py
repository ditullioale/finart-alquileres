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

    def _post_ok(url, json=None, timeout=None):
        capturado["url"] = url
        capturado["json"] = json
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
