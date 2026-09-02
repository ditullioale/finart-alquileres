"""Utilidades compartidas: fechas, montos, mapeo de índices."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import calendar
import re
from urllib.parse import quote


def q2(x):
    """Devuelve x como Decimal redondeado a 2 decimales (centavos exactos).

    Se usa para toda la aritmética de dinero, evitando los errores de redondeo
    de la coma flotante (float). Convierte vía str() para no arrastrar el ruido
    binario de los float (p. ej. 0.1 + 0.2)."""
    if x is None or x == "":
        return Decimal("0.00")
    try:
        return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


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
    """Convierte texto a número tolerando el formato es-AR.

    Reconoce el punto como separador de miles ('250.000' -> 250000), la coma como
    decimal ('1.234,56' -> 1234.56) y descarta el símbolo de moneda y los espacios
    ('$ 250.000' -> 250000). Devuelve None si el texto no representa un número, para
    que quien llama pueda avisar 'no entendí el número' en vez de guardar cualquier
    cosa (antes '250.000' se guardaba como 250)."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return int(valor) if entero else float(valor)
    s = str(valor).strip()
    if s == "":
        return None
    # Sacar moneda, espacios y separadores de miles no numéricos; dejar dígitos,
    # signo y los separadores . , para decidir el decimal.
    neg = s.lstrip().startswith("-")
    s = re.sub(r"[^0-9.,]", "", s)
    if s in ("", ".", ","):
        return None

    if "," in s and "." in s:
        # El último separador que aparece es el decimal.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")   # es-AR: 1.234,56
        else:
            s = s.replace(",", "")                        # en-US: 1,234.56
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")         # coma decimal
    elif "." in s:
        partes = s.split(".")
        # Varios puntos => separador de miles ('1.250.000'). Un solo punto es de
        # miles solo si detrás hay 3 dígitos y la parte entera tiene 1 a 3 dígitos
        # ('250.000', '1.500'); si no, es decimal ('0.75', '100000.005').
        miles = (len(partes) > 2 or
                 (len(partes) == 2 and 1 <= len(partes[0]) <= 3
                  and len(partes[1]) == 3))
        if miles:
            s = s.replace(".", "")

    try:
        n = float(s)
    except ValueError:
        return None
    if neg:
        n = -n
    return int(n) if entero else n


def parse_pct(valor):
    """Parsea un porcentaje (mora diaria, comisión, ajuste).

    A diferencia de parse_num, NUNCA interpreta el punto como separador de miles:
    un porcentaje no se escribe en miles, así que '0.300' es 0.3 (no 300) y
    '12.5' es 12.5. Acepta coma o punto como decimal. Este era el origen del bug
    de la mora cargada como 300%/400% en vez de 0,3/0,4. Devuelve None si el
    texto no representa un número."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    s = re.sub(r"[^0-9.,\-]", "", str(valor).strip())
    if s in ("", ".", ",", "-"):
        return None
    neg = s.startswith("-")
    s = s.lstrip("-").replace(",", ".")
    # Si quedara más de un punto, el último es el decimal; los demás se descartan.
    if s.count(".") > 1:
        ent, _, dec = s.rpartition(".")
        s = ent.replace(".", "") + "." + dec
    try:
        n = float(s)
    except ValueError:
        return None
    return -n if neg else n


# Umbral por encima del cual una mora diaria (%/día) se considera mal cargada.
# Una mora normal está entre 0 y ~5 %/día; 300 o 400 es el bug del ×1000.
MORA_UMBRAL_SOSPECHOSA = 5.0


def sugerir_mora_corregida(valor):
    """Para una mora diaria sospechosa (ej.: 300), sugiere el valor corregido
    dividiendo por 1000 (300 -> 0,3 ; 400 -> 0,4), que es como quedó el bug del
    parser. Devuelve (Decimal, nota) o (None, motivo) si conviene revisarla a
    mano."""
    if valor is None:
        return None, "sin valor"
    corr = (Decimal(str(valor)) / Decimal(1000)).quantize(Decimal("0.001"))
    if corr <= 0:
        return None, "queda 0 o negativo"
    if corr > 10:
        return None, "sigue alto tras /1000"
    return corr, "/1000"


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
    """Mora = precio × (%/100) × días.

    Hay gracia hasta el vencimiento: si se paga en fecha o antes, la mora es 0. Si se paga
    tarde, los días se cuentan **desde el día 1 del mes** del período (no desde el
    vencimiento). Ej.: vence el día 10 y paga el 15 → 15 días de mora."""
    if not (precio and mora_diaria_pct and venc and fecha_pago):
        return 0.0
    if fecha_pago <= venc:               # dentro del plazo de pago → sin mora
        return 0.0
    dia1 = date(venc.year, venc.month, 1)
    dias = (fecha_pago - dia1).days
    if dias <= 0:
        return 0.0
    # Mora con aritmética decimal exacta.
    return q2(q2(precio) * (q2(mora_diaria_pct) / Decimal(100)) * dias)


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


# --------------------------------------------------------------------------- #
#  WhatsApp: armar links "wa.me" con el mensaje precargado
# --------------------------------------------------------------------------- #
def normalizar_whatsapp(tel):
    """Convierte un teléfono argentino al formato que espera wa.me:
    549 + código de área + número (el área + número deben sumar 10 dígitos).

    Tolera 0 inicial, el 15 de celular y el prefijo de país 54/549. Si el
    número no puede normalizarse a 10 dígitos válidos, devuelve None (así no
    se genera un link roto que WhatsApp rechace)."""
    if not tel:
        return None
    # Los teléfonos importados desde Excel suelen venir como decimales
    # (ej: "3402539090.0"). Ese ".0" agregaba un cero de más: lo quitamos.
    s = re.sub(r"\.0+$", "", str(tel).strip())
    d = re.sub(r"\D", "", s)
    if not d:
        return None
    # Quitar prefijo de país (54) y el 9 de móvil si vienen pegados.
    if d.startswith("549"):
        d = d[3:]
    elif d.startswith("54"):
        d = d[2:]
    # Quitar 0 de larga distancia (ej. 0341...).
    if d.startswith("0"):
        d = d[1:]
    # Un número AR (código de área + abonado) tiene 10 dígitos. Si trae el
    # "15" de celular aparece justo después del área y sobran 2 dígitos: se quita.
    if len(d) == 12:
        for i in (2, 3, 4):
            if d[i:i + 2] == "15":
                d = d[:i] + d[i + 2:]
                break
    # Un 9 de móvil que haya quedado suelto al principio.
    if len(d) == 11 and d.startswith("9"):
        d = d[1:]
    # Números claramente incompletos (sin código de área) no sirven.
    if len(d) < 10:
        return None
    # Best-effort: si quedaron 10 dígitos es un número AR válido; si quedaron
    # más, igual armamos el link (puede fallar en WhatsApp, pero mostramos el
    # botón). Lo ideal es que el número tenga 10 dígitos (área + abonado).
    return "549" + d


def whatsapp_valido(tel):
    """True solo si el teléfono queda como un número argentino correcto
    (549 + exactamente 10 dígitos). Se usa para avisar al cargar personas."""
    num = normalizar_whatsapp(tel)
    return bool(num) and len(num) == 13


def link_whatsapp(tel, mensaje=""):
    """Link https://wa.me/... que abre WhatsApp con el mensaje ya escrito.
    Devuelve None si el teléfono no es válido/usable."""
    numero = normalizar_whatsapp(tel)
    if not numero:
        return None
    return f"https://wa.me/{numero}?text={quote(mensaje)}"
