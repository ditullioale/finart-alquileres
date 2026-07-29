"""Robot de Litoral Gas: lee la deuda de gas de TODAS tus cuentas (de una o
varias sesiones de Litoral Gas) y la guarda en la app (panel "Control de gas").

Cómo funciona: inicia sesión en la Oficina Virtual y le pide los datos a la API
interna del portal (rápido, sin recorrer cuenta por cuenta). Soporta 2 cuentas
de Litoral Gas: las lee de las variables del archivo .env.

    LITORALGAS_USER / LITORALGAS_PASS      (primera cuenta)
    LITORALGAS_USER2 / LITORALGAS_PASS2    (segunda cuenta, opcional)

Uso:
    python litoralgas_bot.py --ver --prueba   (muestra sin guardar; navegador visible)
    python litoralgas_bot.py                   (lee y ENVÍA a la app)
"""
import os
import re
import sys
import json
import argparse
from datetime import date

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

LOGIN_URL = "https://www.litoralgas.com.ar/ov/"
API = "https://www.litoralgas.com.ar/ovapi/api"


def parse_fecha(s):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s or "")
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def cuenta_str(srvcode, cntnumber):
    return f"{srvcode}/{int(cntnumber):02d}"


def ar(monto):
    return f"{monto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def procesar_cuenta_litoral(p, usuario, clave, headless):
    """Loguea en una cuenta de Litoral Gas y devuelve la lista de suministros
    con su estado de deuda."""
    resultados = []
    token_holder = {}

    def on_response(resp):
        if resp.url.rstrip("/").endswith("/auth/login"):
            try:
                token_holder["token"] = resp.json().get("token", {}).get("access_token")
            except Exception:
                pass

    browser = p.chromium.launch(headless=headless)
    ctx = browser.new_context()
    page = ctx.new_page()
    page.on("response", on_response)

    page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
    try:
        page.get_by_label("Correo Electrónico").fill(usuario)
        page.get_by_label("Contraseña").fill(clave)
    except Exception:
        page.locator("input[type='email'], input[type='text']").first.fill(usuario)
        page.locator("input[type='password']").first.fill(clave)
    page.get_by_text("Ingresar", exact=True).first.click()

    for _ in range(40):
        if token_holder.get("token"):
            break
        page.wait_for_timeout(500)
    token = token_holder.get("token")
    if not token:
        print(f"  No se pudo iniciar sesión en {usuario} (¿usuario/clave correctos?).")
        browser.close()
        return resultados

    api = ctx.request
    headers = {"Authorization": "Bearer " + token}
    info = api.get(f"{API}/Clientes/Info", headers=headers)
    contratos = (info.json() or {}).get("lstContratos", [])
    print(f"  {len(contratos)} cuenta(s) en {usuario}")

    for c in contratos:
        srv = c.get("srvcode"); cnt = c.get("cntnumber"); hform = c.get("hForm")
        cuenta = cuenta_str(srv, cnt)
        items = []
        try:
            r = api.get(f"{API}/Contratos/OverDueBillsUni", headers=headers,
                        params={"srvcode": srv, "cntnumber": cnt, "includepaid": 0,
                                "hForm": hform, "offset": 0})
            items = (r.json() or {}).get("items", []) or []
        except Exception as e:  # noqa: BLE001
            print(f"    {cuenta}: no se pudo leer la deuda ({e})")

        deuda = 0.0
        ultimo = None
        facturas = []
        for it in items:
            saldo = round(float(it.get("docamount") or 0) + float(it.get("docdueinterwtax") or 0), 2)
            deuda += saldo
            f = parse_fecha(it.get("docduedate"))
            if f and (ultimo is None or f > ultimo):
                ultimo = f
            facturas.append({"num": str(it.get("docnumber") or ""),
                             "venc": f.isoformat() if f else None,
                             "imp": saldo})
        # ordenar facturas de la más vieja a la más nueva
        facturas.sort(key=lambda x: x["venc"] or "")
        deuda = round(deuda, 2)
        tiene = len(items) > 0
        estado = ("DEBE $%s (%d fact.)" % (ar(deuda), len(items))) if tiene else "al día"
        print(f"    {cuenta:12}  {(c.get('prsname') or '')[:26]:26}  {estado}")
        resultados.append(dict(
            cuenta=cuenta, titular=c.get("prsname") or "", direccion=c.get("srvadress") or "",
            contrato_vigente=("NO VIGENTE" not in (c.get("cntstatus") or "").upper()),
            tiene_deuda=tiene, deuda_total=deuda, ultimo_vencimiento=ultimo,
            detalle=json.dumps(facturas, ensure_ascii=False)))
    browser.close()
    return resultados


def _obtener_credenciales(app_url, token):
    """Junta TODAS las credenciales de Litoral Gas a consultar:
      1) las que cada inmobiliaria cargó en la app (con su inmobiliaria_id), y
      2) las del .env (tus cuentas históricas), que van a la inmobiliaria principal.
    Se combinan ambas fuentes (no una u otra), sin duplicar por usuario. Así, aunque
    otras inmobiliarias configuren sus credenciales, tus dos cuentas del .env siguen
    consultándose igual que siempre."""
    import json
    import urllib.request
    creds = []
    vistos = set()

    # 1) Credenciales cargadas en la app (multiempresa).
    if app_url and token:
        url = app_url.rstrip("/") + "/gas/robot/credenciales"
        req = urllib.request.Request(url, headers={"X-Gas-Token": token})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for i in (data.get("inmobiliarias", []) if data.get("ok") else []):
                usuario, clave = i.get("usuario"), i.get("clave")
                if usuario and clave and usuario.lower() not in vistos:
                    creds.append((i.get("inmobiliaria_id"), usuario, clave))
                    vistos.add(usuario.lower())
        except Exception as e:  # noqa: BLE001
            print(f"No se pudieron traer las credenciales desde la app ({e}). "
                  "Sigo con las del .env si están.")

    # 2) Credenciales del .env (van a la inmobiliaria principal).
    for u, c in [("LITORALGAS_USER", "LITORALGAS_PASS"),
                 ("LITORALGAS_USER2", "LITORALGAS_PASS2")]:
        usuario = os.environ.get(u); clave = os.environ.get(c)
        if usuario and clave and usuario.lower() not in vistos:
            creds.append((None, usuario, clave))
            vistos.add(usuario.lower())
    return creds


def _enviar(app_url, token, inmobiliaria_id, resultados):
    import json
    import urllib.request
    cuentas = []
    for r in resultados:
        cuentas.append(dict(
            cuenta=r["cuenta"], titular=r["titular"], direccion=r["direccion"],
            contrato_vigente=r["contrato_vigente"], tiene_deuda=r["tiene_deuda"],
            deuda_total=r["deuda_total"],
            ultimo_vencimiento=(r["ultimo_vencimiento"].isoformat() if r["ultimo_vencimiento"] else None),
            detalle=r["detalle"]))
    payload = json.dumps({"inmobiliaria_id": inmobiliaria_id,
                          "cuentas": cuentas}).encode("utf-8")
    url = app_url.rstrip("/") + "/gas/importar"
    req = urllib.request.Request(url, data=payload, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "X-Gas-Token": token})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ver", action="store_true", help="Navegador visible")
    ap.add_argument("--prueba", action="store_true", help="No guardar, solo mostrar")
    args = ap.parse_args()

    app_url = os.environ.get("GAS_APP_URL")
    token = os.environ.get("GAS_IMPORT_TOKEN")

    # Una entrada por inmobiliaria: (inmobiliaria_id, usuario, clave).
    credenciales = _obtener_credenciales(app_url, token)
    if not credenciales:
        print("ERROR: no hay credenciales de Litoral Gas. Configuralas en la app "
              "(Ajustes → Litoral Gas) o en el .env (LITORALGAS_USER / LITORALGAS_PASS).")
        sys.exit(1)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        for inmo_id, usuario, clave in credenciales:
            etiqueta = f"inmobiliaria #{inmo_id}" if inmo_id else "(.env)"
            print(f"\nEntrando a Litoral Gas: {usuario}  [{etiqueta}] …")
            resultados = procesar_cuenta_litoral(p, usuario, clave, headless=not args.ver)

            # Quitar duplicados por número de cuenta dentro de esta inmobiliaria.
            por_cuenta = {r["cuenta"]: r for r in resultados}
            resultados = list(por_cuenta.values())
            con_deuda = sum(1 for r in resultados if r["tiene_deuda"])
            total_deuda = sum(r["deuda_total"] for r in resultados)
            print(f"  {len(resultados)} cuentas | {con_deuda} con deuda | "
                  f"total $ {ar(total_deuda)}")

            if args.prueba:
                continue
            if not app_url or not token:
                print("  (para guardar en la app configurá GAS_APP_URL y "
                      "GAS_IMPORT_TOKEN en el .env)")
                continue
            try:
                r = _enviar(app_url, token, inmo_id, resultados)
                print("  Enviado a la app:", r)
            except Exception as e:  # noqa: BLE001
                print(f"  No se pudo enviar a la app: {e}")

    if args.prueba:
        print("\n(modo prueba: no se guardó nada en la app)")


if __name__ == "__main__":
    main()
