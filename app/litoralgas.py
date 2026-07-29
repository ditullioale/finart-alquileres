"""Consulta de deuda de Litoral Gas desde el servidor, SIN navegador.

Reproduce por HTTP lo que hace el robot: inicia sesión en la Oficina Virtual
(POST /auth/login con usrLogin/usrClave) y consulta la API interna con el token.
Así el botón "Actualizar" del panel de gas funciona directo desde la app.
"""
import json
import ssl
import urllib.parse
import urllib.request
from datetime import date

API = "https://www.litoralgas.com.ar/ovapi/api"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_BASE_HEADERS = {
    "User-Agent": _UA, "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.litoralgas.com.ar",
    "Referer": "https://www.litoralgas.com.ar/ov/",
}


class GasError(Exception):
    """Error genérico al consultar Litoral Gas."""


class CredencialesError(GasError):
    """Usuario o contraseña incorrectos."""


def _ctx():
    try:
        return ssl.create_default_context()
    except Exception:
        c = ssl.create_default_context()
        c.check_hostname = False
        c.verify_mode = ssl.CERT_NONE
        return c


def _pedir(url, token=None, metodo="GET", cuerpo=None, params=None, timeout=45):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = dict(_BASE_HEADERS)
    data = None
    if cuerpo is not None:
        data = json.dumps(cuerpo).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (400, 401, 403):
            raise CredencialesError("Usuario o contraseña de Litoral Gas incorrectos.")
        raise GasError(f"Litoral Gas respondió con error {e.code}.")
    except Exception as e:  # noqa: BLE001
        raise GasError(f"No se pudo conectar con Litoral Gas ({e}).")


def _parse_fecha(s):
    try:
        y, m, d = str(s)[:10].split("-")
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def login(usuario, clave):
    """Devuelve el token de acceso o lanza CredencialesError."""
    r = _pedir(API + "/auth/login", metodo="POST",
               cuerpo={"usrLogin": usuario, "usrClave": clave})
    token = ((r or {}).get("token") or {}).get("access_token")
    if not token:
        raise CredencialesError("No se pudo iniciar sesión en Litoral Gas.")
    return token


def consultar_deuda(usuario, clave):
    """Inicia sesión y devuelve la lista de suministros con su estado de deuda,
    en el mismo formato que espera GasEstado.upsert."""
    token = login(usuario, clave)
    info = _pedir(API + "/Clientes/Info", token=token)
    contratos = (info or {}).get("lstContratos", []) or []

    resultados = []
    for c in contratos:
        srv, cnt, hform = c.get("srvcode"), c.get("cntnumber"), c.get("hForm")
        cuenta = f"{srv}/{int(cnt):02d}"
        items = []
        try:
            r = _pedir(API + "/Contratos/OverDueBillsUni", token=token,
                       params={"srvcode": srv, "cntnumber": cnt, "includepaid": 0,
                               "hForm": hform, "offset": 0})
            items = (r or {}).get("items", []) or []
        except GasError:
            items = []

        deuda, ultimo, facturas = 0.0, None, []
        for it in items:
            saldo = round(float(it.get("docamount") or 0)
                          + float(it.get("docdueinterwtax") or 0), 2)
            deuda += saldo
            f = _parse_fecha(it.get("docduedate"))
            if f and (ultimo is None or f > ultimo):
                ultimo = f
            facturas.append({"num": str(it.get("docnumber") or ""),
                             "venc": f.isoformat() if f else None, "imp": saldo})
        facturas.sort(key=lambda x: x["venc"] or "")
        resultados.append(dict(
            cuenta=cuenta, titular=c.get("prsname") or "",
            direccion=c.get("srvadress") or "",
            contrato_vigente=("NO VIGENTE" not in (c.get("cntstatus") or "").upper()),
            tiene_deuda=len(items) > 0, deuda_total=round(deuda, 2),
            ultimo_vencimiento=ultimo,
            detalle=json.dumps(facturas, ensure_ascii=False)))
    return resultados
