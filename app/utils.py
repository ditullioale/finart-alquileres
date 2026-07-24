"""Utilidades compartidas: fechas, montos, mapeo de índices."""
from datetime import date
import calendar


def add_months(d: date, meses: int) -> date:
    """Suma meses a una fecha ajustando el día al último válido del mes."""
    if d is None:
        return None
    m = d.month - 1 + int(meses)
    y = d.year + m // 12
    m = m % 12 + 1
    ultimo = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, ultimo))


def parse_fecha(valor):
    """Convierte 'YYYY-MM-DD' o 'DD/MM/YYYY' a date. Devuelve None si no puede."""
    if not valor:
        return None
    valor = valor.strip()
    for sep, orden in (("-", "ymd"), ("/", "dmy")):
        if sep in valor:
            partes = valor.split(sep)
            if len(partes) == 3:
                try:
                    a, b, c = (int(p) for p in partes)
                except ValueError:
                    return None
                if orden == "ymd":
                    return date(a, b, c)
                return date(c, b, a)
    return None


def parse_num(valor, entero=False):
    """Convierte texto a número tolerando formato es-AR (miles con punto)."""
    if valor is None:
        return None
    s = str(valor).strip()
    if s == "":
        return None
    # Si tiene coma decimal, quitar puntos de miles.
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return int(float(s)) if entero else float(s)
    except ValueError:
        return None


# Mapeo del índice del generador -> código interno
INDICE_MAP = {
    "I.C.L": "ICL", "ICL": "ICL",
    "I.P.C.": "IPC", "IPC": "IPC",
    "Casa Propia": "CasaPropia", "CasaPropia": "CasaPropia",
    "Sin ajuste": None,
}

INDICE_NOMBRE = {"ICL": "ICL (BCRA)", "IPC": "IPC (INDEC)", "CasaPropia": "Casa Propia"}

MESES_ES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
            "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def vencimiento(anio, mes, dia):
    """Fecha de vencimiento de un período, ajustando el día al último válido."""
    import calendar
    ultimo = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, min(int(dia or 1), ultimo))


def calcular_mora(precio, mora_diaria_pct, venc, fecha_pago):
    """Mora = precio × (%/100) × días de atraso. 0 si se paga en fecha o antes."""
    if not (precio and mora_diaria_pct and venc and fecha_pago):
        return 0.0
    dias = (fecha_pago - venc).days
    if dias <= 0:
        return 0.0
    return round(float(precio) * (float(mora_diaria_pct) / 100.0) * dias, 2)


def periodo_siguiente(mes, anio):
    """Devuelve (mes, anio) del mes siguiente."""
    if mes >= 12:
        return 1, anio + 1
    return mes + 1, anio


def periodo_date(anio, mes):
    """Primer día del mes (clave usada para guardar valores de índice)."""
    return date(int(anio), int(mes), 1)


def parse_periodo(texto):
    """Convierte 'YYYY-MM' o 'MM/YYYY' al primer día del mes."""
    if not texto:
        return None
    texto = texto.strip()
    if "-" in texto:
        p = texto.split("-")
        if len(p) >= 2:
            try:
                return date(int(p[0]), int(p[1]), 1)
            except ValueError:
                return None
    if "/" in texto:
        p = texto.split("/")
        if len(p) == 2:
            try:
                return date(int(p[1]), int(p[0]), 1)
            except ValueError:
                return None
    return None


def proximo_ajuste(fecha_inicio, cada_meses, n_aumentos):
    """Fecha del próximo ajuste = inicio + (n+1) × cada_meses (en meses)."""
    if not fecha_inicio or not cada_meses:
        return None
    return add_months(fecha_inicio, (n_aumentos + 1) * int(cada_meses))


# --------------------------------------------------------------------------- #
#  Importe en letras (para recibos y pagarés)
# --------------------------------------------------------------------------- #
_UNI = ['', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho',
        'nueve', 'diez', 'once', 'doce', 'trece', 'catorce', 'quince',
        'dieciséis', 'diecisiete', 'dieciocho', 'diecinueve', 'veinte']
_DEC = ['', '', 'veinti', 'treinta', 'cuarenta', 'cincuenta', 'sesenta',
        'setenta', 'ochenta', 'noventa']
_CEN = ['', 'ciento', 'doscientos', 'trescientos', 'cuatrocientos', 'quinientos',
        'seiscientos', 'setecientos', 'ochocientos', 'novecientos']


def _seccion(n):
    s = ''
    c, r = divmod(n, 100)
    if c:
        s += 'cien' if n == 100 else _CEN[c]
    if r:
        if s:
            s += ' '
        if r <= 20:
            s += _UNI[r]
        else:
            d, u = divmod(r, 10)
            if d == 2:
                s += ('veinti' + _UNI[u]) if u else 'veinte'
            else:
                s += _DEC[d] + (' y ' + _UNI[u] if u else '')
    return s


def numero_letras(num):
    num = int(abs(num))
    if num == 0:
        return 'cero'
    mill, resto = divmod(num, 1000000)
    mil, resto = divmod(resto, 1000)
    res = ''
    if mill:
        res += 'un millón' if mill == 1 else _seccion(mill) + ' millones'
    if mil:
        res += (' ' if res else '') + ('mil' if mil == 1 else _seccion(mil) + ' mil')
    if resto:
        res += (' ' if res else '') + _seccion(resto)
    return res


def pesos_letras(n):
    n = float(n or 0)
    entero = int(n)
    centavos = round((n - entero) * 100)
    s = numero_letras(entero) + ' pesos'
    if centavos:
        s += f' con {centavos:02d}/100'
    return s.capitalize()
