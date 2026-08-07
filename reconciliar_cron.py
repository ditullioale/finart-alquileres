"""Cron de reconciliación de facturación.

Pega al endpoint del gestor para reconciliar las liquidaciones pendientes (las que
quedaron en 'estado a confirmar' por un timeout). Pensado para el cron nativo de
Railway: se despliega desde este mismo repo, corre este script y termina.

No toca la base ni levanta el servidor: es solo un cliente HTTP. Necesita una variable:
    RECONCILIAR_TOKEN   -> el mismo valor que configuraste en el servicio 'web'.
Opcional:
    RECONCILIAR_URL     -> por si cambia el dominio (por defecto usa el de producción).
"""
import os
import sys
import urllib.request

URL = (os.environ.get("RECONCILIAR_URL")
       or "https://web-production-ddb2a.up.railway.app/liquidaciones/reconciliar-cron")
TOKEN = os.environ.get("RECONCILIAR_TOKEN", "")

if not TOKEN:
    print("Falta la variable RECONCILIAR_TOKEN.")
    sys.exit(1)

req = urllib.request.Request(URL, data=b"", method="POST")
req.add_header("X-Reconciliar-Token", TOKEN)
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        print(f"OK {r.status}: {r.read().decode('utf-8', 'ignore')}")
except Exception as exc:  # noqa: BLE001
    print(f"Error al reconciliar: {exc}")
    sys.exit(1)
