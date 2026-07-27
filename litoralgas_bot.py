"""Robot de Litoral Gas: lee la deuda de gas de TODAS tus cuentas y la guarda
en la app (panel "Control de gas").

Cómo funciona: inicia sesión una sola vez en la Oficina Virtual y después le
pide los datos directamente a la API interna del portal (rápido y sin recorrer
cuenta por cuenta). Usuario y clave se leen del archivo .env.

Uso:
    python litoralgas_bot.py --ver --prueba   (muestra sin guardar; navegador visible)
    python litoralgas_bot.py                   (lee y GUARDA en la app)
"""
import os
import re
import sys
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
    """962500 + 1 -> '962500/01' (igual que se ve en Litoral Gas)."""
    return f"{srvcode}/{int(cntnumber):02d}"


def ar(monto):
    """Formato argentino: 1782.96 -> '1.782,96'."""
    return f"{monto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ver", action="store_true", help="Navegador visible")
    ap.add_argument("--prueba", action="store_true", help="No guardar, solo mostrar")
    args = ap.parse_args()

    usuario = os.environ.get("LITORALGAS_USER")
    clave = os.environ.get("LITORALGAS_PASS")
    if not usuario or not clave:
        print("ERROR: falta LITORALGAS_USER o LITORALGAS_PASS en el archivo .env.")
        sys.exit(1)

    from playwright.sync_api import sync_playwright

    token_holder = {}

    def on_response(resp):
        if resp.url.rstrip("/").endswith("/auth/login"):
            try:
                token_holder["token"] = resp.json().get("token", {}).get("access_token")
            except Exception:
                pass

    resultados = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.ver)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.on("response", on_response)

        print("Entrando a Litoral Gas…")
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
        try:
            page.get_by_label("Correo Electrónico").fill(usuario)
            page.get_by_label("Contraseña").fill(clave)
        except Exception:
            page.locator("input[type='email'], input[type='text']").first.fill(usuario)
            page.locator("input[type='password']").first.fill(clave)
        page.get_by_text("Ingresar", exact=True).first.click()

        # Esperar el token de sesión (aparece en la respuesta del login).
        for _ in range(40):
            if token_holder.get("token"):
                break
            page.wait_for_timeout(500)
        token = token_holder.get("token")
        if not token:
            print("No se pudo iniciar sesión (¿usuario/clave correctos?).")
            browser.close(); sys.exit(2)
        print("Sesión iniciada. Leyendo cuentas por la API…")

        api = ctx.request
        headers = {"Authorization": "Bearer " + token}

        info = api.get(f"{API}/Clientes/Info", headers=headers)
        contratos = (info.json() or {}).get("lstContratos", [])
        print(f"Se encontraron {len(contratos)} cuenta(s).\n")

        for c in contratos:
            srv = c.get("srvcode"); cnt = c.get("cntnumber")
            hform = c.get("hForm")
            cuenta = cuenta_str(srv, cnt)
            items = []
            try:
                r = api.get(f"{API}/Contratos/OverDueBillsUni", headers=headers,
                            params={"srvcode": srv, "cntnumber": cnt, "includepaid": 0,
                                    "hForm": hform, "offset": 0})
                items = (r.json() or {}).get("items", []) or []
            except Exception as e:  # noqa: BLE001
                print(f"  {cuenta}: no se pudo leer la deuda ({e})")

            deuda = 0.0
            ultimo = None
            for it in items:
                saldo = float(it.get("docamount") or 0) + float(it.get("docdueinterwtax") or 0)
                deuda += saldo
                f = parse_fecha(it.get("docduedate"))
                if f and (ultimo is None or f > ultimo):
                    ultimo = f
            deuda = round(deuda, 2)
            tiene = len(items) > 0
            estado = ("DEBE $%s (%d fact.)" % (ar(deuda), len(items))) if tiene else "al día"
            print(f"  {cuenta:12}  {(c.get('prsname') or '')[:26]:26}  {estado}")
            resultados.append(dict(
                cuenta=cuenta, titular=c.get("prsname") or "", direccion=c.get("srvadress") or "",
                contrato_vigente=("NO VIGENTE" not in (c.get("cntstatus") or "").upper()),
                tiene_deuda=tiene, deuda_total=deuda, ultimo_vencimiento=ultimo,
                detalle=f"{len(items)} factura(s) pendiente(s)"))
        browser.close()

    con_deuda = sum(1 for r in resultados if r["tiene_deuda"])
    total_deuda = sum(r["deuda_total"] for r in resultados)
    print(f"\nResumen: {len(resultados)} cuentas | {con_deuda} con deuda | "
          f"total $ {ar(total_deuda)}")

    if args.prueba:
        print("\n(modo prueba: no se guardó nada en la app)")
        return

    # Enviar los datos a la app (por internet, con un token secreto).
    app_url = os.environ.get("GAS_APP_URL")
    token = os.environ.get("GAS_IMPORT_TOKEN")
    if not app_url or not token:
        print("\nPara guardar en la app configurá GAS_APP_URL y GAS_IMPORT_TOKEN en el .env.")
        print("(La lectura salió bien igual; solo falta ese paso para que aparezca en la app.)")
        return

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
    payload = json.dumps({"cuentas": cuentas}).encode("utf-8")
    url = app_url.rstrip("/") + "/gas/importar"
    req = urllib.request.Request(url, data=payload, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "X-Gas-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            print("\n¡Listo! Datos enviados a la app:", resp.read().decode("utf-8"))
            print("Miralo en la sección 'Control de gas' de tu app.")
    except Exception as e:  # noqa: BLE001
        print(f"\nNo se pudo enviar a la app: {e}")
        print("Revisá GAS_APP_URL (la dirección de tu app) y que GAS_IMPORT_TOKEN coincida "
              "con el configurado en Railway.")


if __name__ == "__main__":
    main()
