"""Robot de Litoral Gas: entra a la Oficina Virtual, recorre todas las cuentas
y guarda el estado de deuda de cada una en la app (tabla GasEstado).

CÓMO FUNCIONA
-------------
1. Lee tu usuario y contraseña de Litoral Gas desde variables de entorno
   (NUNCA van escritas en el código):
       LITORALGAS_USER=tucorreo@gmail.com
       LITORALGAS_PASS=tu-contraseña
2. Abre un navegador automatizado, inicia sesión, abre "Ver todos" para listar
   todas las cuentas, y por cada una lee si tiene facturas vencidas y el saldo.
3. Guarda todo en la base de datos de la app.

CÓMO PROBARLO (en tu PC, la primera vez)
----------------------------------------
    pip install playwright
    playwright install chromium
    set LITORALGAS_USER=tucorreo@gmail.com      (Windows CMD)
    set LITORALGAS_PASS=tu-clave
    python litoralgas_bot.py --ver              (--ver abre el navegador visible
                                                 para que veas qué hace y ajustar)

Para que NO guarde y solo muestre lo que encontró:
    python litoralgas_bot.py --ver --prueba

NOTA: como los portales cambian, es probable que los "selectores" (las marcas
que usa el robot para encontrar los botones) necesiten un pequeño ajuste la
primera vez. Los dejé arriba, comentados, para tocarlos fácil.
"""
import os
import re
import sys
import argparse
from datetime import datetime

LOGIN_URL = "https://www.litoralgas.com.ar/ov/"


def parse_money(txt):
    """'$ 24.167,49' -> 24167.49"""
    if not txt:
        return 0.0
    s = re.sub(r"[^\d,.-]", "", txt).replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_fecha(txt):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", txt or "")
    if not m:
        return None
    from datetime import date
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))


def leer_cuentas(page):
    """Devuelve [(cuenta, titular, direccion, vigente)] desde 'Ver todos'."""
    # Abrir el selector de cliente (arriba, al centro) y "Ver todos".
    try:
        page.get_by_text("Ver todos", exact=False).first.click(timeout=8000)
    except Exception:
        # Si no está abierto el panel, primero hay que abrir el selector de cliente.
        page.locator("header, .header").first.click()
        page.get_by_text("Ver todos", exact=False).first.click(timeout=8000)
    page.wait_for_timeout(1500)

    cuentas = []
    # Cada fila del listado muestra "Cliente: 962500/01", un nombre, una dirección
    # y un estado "Contrato vigente / no vigente". Recorremos por el texto "Cliente:".
    filas = page.locator("text=/Cliente:\\s*\\d+\\/\\d+/").all()
    vistos = set()
    for f in filas:
        try:
            bloque = f.locator("xpath=ancestor::*[self::div or self::li][1]")
            texto = bloque.inner_text(timeout=2000)
        except Exception:
            texto = f.inner_text()
        m = re.search(r"Cliente:\s*(\d+/\d+)", texto)
        if not m:
            continue
        cuenta = m.group(1)
        if cuenta in vistos:
            continue
        vistos.add(cuenta)
        vigente = "no vigente" not in texto.lower()
        # nombre y direccion: líneas del bloque (best-effort)
        lineas = [l.strip() for l in texto.splitlines() if l.strip()]
        titular = next((l for l in lineas if l.isupper() and "CLIENTE" not in l.upper()), "")
        direccion = next((l for l in lineas if any(x in l.upper() for x in
                         ["ROSARIO", "ARROYO", "FIGHIERA", "CALLE", "AV", "SAN "])), "")
        cuentas.append((cuenta, titular, direccion, vigente))
    return cuentas


def leer_deuda_cuenta(page, cuenta):
    """Selecciona la cuenta y lee su estado de deuda desde 'Mis facturas'."""
    # Seleccionar la cuenta desde el buscador del selector de cliente.
    page.get_by_text("Ver todos", exact=False).first.click(timeout=8000)
    page.wait_for_timeout(600)
    page.get_by_text(cuenta, exact=False).first.click(timeout=8000)
    page.wait_for_timeout(1500)

    # Ir a "Mis facturas" (barra lateral) y ver solo pendientes.
    page.get_by_text("Mis facturas", exact=False).first.click(timeout=8000)
    page.wait_for_timeout(1500)
    try:
        page.get_by_text("Mostrar solo pendientes", exact=False).first.click(timeout=3000)
        page.wait_for_timeout(800)
    except Exception:
        pass

    # Leer las filas de facturas: Número, Vencimiento, Importe, Saldo actualizado.
    texto = page.locator("body").inner_text()
    saldos = re.findall(r"\$\s*[\d\.]+,\d{2}", texto)
    # El saldo actualizado es la 2da columna de montos por fila; sumamos de forma
    # conservadora los saldos encontrados en la tabla (se ajusta al probar).
    vencs = re.findall(r"\d{2}/\d{2}/\d{4}", texto)
    tiene_deuda = "vencidas" in texto.lower() or bool(saldos)
    deuda_total = 0.0
    # Buscar el patrón de tabla: tomamos los "Saldo actualizado" (los mayores por fila).
    montos = [parse_money(s) for s in saldos]
    if montos:
        # heurística: los saldos actualizados suelen ser los valores más grandes.
        deuda_total = round(sum(sorted(montos, reverse=True)[:len(vencs) or len(montos)]), 2)
    ultimo_venc = parse_fecha(sorted(vencs)[-1]) if vencs else None
    return tiene_deuda, deuda_total, ultimo_venc, texto[:1500]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ver", action="store_true", help="Abrir el navegador visible")
    ap.add_argument("--prueba", action="store_true", help="No guardar, solo mostrar")
    args = ap.parse_args()

    usuario = os.environ.get("LITORALGAS_USER")
    clave = os.environ.get("LITORALGAS_PASS")
    if not usuario or not clave:
        print("ERROR: definí las variables LITORALGAS_USER y LITORALGAS_PASS.")
        sys.exit(1)

    from playwright.sync_api import sync_playwright

    resultados = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.ver)
        page = browser.new_page()
        print("Entrando a Litoral Gas…")
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)

        # --- LOGIN ---
        page.get_by_label("Correo Electrónico").fill(usuario)
        page.get_by_label("Contraseña").fill(clave)
        page.get_by_text("Ingresar", exact=True).first.click()
        page.wait_for_timeout(4000)
        if "Correo" in page.locator("body").inner_text() and "Ingresar" in page.locator("body").inner_text():
            print("No se pudo iniciar sesión. Revisá usuario/clave o si apareció un CAPTCHA.")
            browser.close(); sys.exit(2)
        print("Sesión iniciada. Buscando cuentas…")

        cuentas = leer_cuentas(page)
        print(f"Se encontraron {len(cuentas)} cuenta(s).")
        for cuenta, titular, direccion, vigente in cuentas:
            try:
                tiene_deuda, deuda, venc, detalle = leer_deuda_cuenta(page, cuenta)
            except Exception as e:  # noqa: BLE001
                print(f"  {cuenta}: no se pudo leer ({e})")
                continue
            estado = "DEBE $%.2f" % deuda if tiene_deuda else "al día"
            print(f"  {cuenta}  {titular[:24]:24}  {estado}")
            resultados.append(dict(cuenta=cuenta, titular=titular, direccion=direccion,
                                   contrato_vigente=vigente, tiene_deuda=tiene_deuda,
                                   deuda_total=deuda, ultimo_vencimiento=venc,
                                   detalle=detalle))
        browser.close()

    if args.prueba:
        print("\n(modo prueba: no se guardó nada)")
        return

    # Guardar en la base de la app.
    from app import create_app, db
    from app.models import GasEstado
    app = create_app()
    with app.app_context():
        for r in resultados:
            GasEstado.upsert(r["cuenta"], titular=r["titular"], direccion=r["direccion"],
                             contrato_vigente=r["contrato_vigente"], tiene_deuda=r["tiene_deuda"],
                             deuda_total=r["deuda_total"], ultimo_vencimiento=r["ultimo_vencimiento"],
                             detalle=r["detalle"])
        db.session.commit()
    print(f"\nGuardadas {len(resultados)} cuentas en la app. ¡Listo!")


if __name__ == "__main__":
    main()
