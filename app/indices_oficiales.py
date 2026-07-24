"""Consulta best-effort de índices oficiales.

El ICL (Índice para Contratos de Locación) lo publica el BCRA. Esta consulta es
tolerante a fallos: si la API no está disponible o cambia, devuelve un error
controlado y el usuario carga los valores manualmente o por importación.

Nota: la disponibilidad y el formato de la API oficial pueden cambiar; esta
función está pensada para ajustarse fácilmente sin afectar al resto del sistema.
"""
from datetime import date


def traer_icl_bcra(desde: date = None, hasta: date = None):
    """Intenta traer la serie diaria del ICL desde la API del BCRA.

    Devuelve (valores, error) donde:
      - valores: lista de dicts {periodo(date, día 1), valor(float)} tomando el
        último valor de cada mes.
      - error: None si salió bien, o un mensaje explicativo si no.
    """
    try:
        import requests
    except ImportError:
        return None, "Falta la librería 'requests'. Instalala o cargá el índice a mano."

    # ID de la variable ICL en la API monetaria v3 del BCRA.
    url = "https://api.bcra.gob.ar/estadisticas/v3.0/monetarias/40"
    params = {}
    if desde:
        params["desde"] = desde.isoformat()
    if hasta:
        params["hasta"] = hasta.isoformat()

    try:
        # El BCRA usa un certificado que a veces no valida en todos los entornos.
        r = requests.get(url, params=params, timeout=15, verify=False,
                         headers={"Accept": "application/json"})
        if r.status_code != 200:
            return None, f"El BCRA respondió con estado {r.status_code}. Probá más tarde o cargá a mano."
        data = r.json()
    except Exception as e:  # noqa: BLE001
        return None, f"No se pudo conectar con el BCRA ({type(e).__name__}). Cargá el índice a mano."

    detalle = data.get("results", {}).get("detalle") if isinstance(data, dict) else None
    if not detalle:
        return None, "La API del BCRA no devolvió datos de ICL. Cargá el índice a mano."

    # Quedarse con el último valor de cada mes.
    por_mes = {}
    for item in detalle:
        f = item.get("fecha")
        v = item.get("valor")
        if not f or v is None:
            continue
        try:
            y, m, d = (int(x) for x in f.split("-"))
        except ValueError:
            continue
        clave = (y, m)
        if clave not in por_mes or d > por_mes[clave][0]:
            por_mes[clave] = (d, float(v))

    valores = [{"periodo": date(y, m, 1), "valor": val}
               for (y, m), (d, val) in sorted(por_mes.items())]
    if not valores:
        return None, "No se pudieron interpretar los valores del BCRA. Cargá a mano."
    return valores, None
