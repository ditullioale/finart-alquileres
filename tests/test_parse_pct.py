"""El parseo de porcentajes (mora, comisión, ajuste) no debe tomar el punto como
separador de miles: '0.300' es 0,3 y NO 300. Esto arregla la mora que quedaba
cargada como 300%/400% en vez de 0,3/0,4."""
from app.utils import parse_pct


def test_punto_con_tres_decimales_no_es_miles():
    # El bug: parse_num('0.300') daba 300. parse_pct debe dar 0.3.
    assert parse_pct("0.300") == 0.3
    assert parse_pct("0.400") == 0.4


def test_decimales_normales():
    assert parse_pct("0.3") == 0.3
    assert parse_pct("0,3") == 0.3
    assert parse_pct("0,30") == 0.3
    assert parse_pct("12.5") == 12.5
    assert parse_pct("12,5") == 12.5


def test_enteros_y_vacios():
    assert parse_pct("1") == 1.0
    assert parse_pct("8") == 8.0
    assert parse_pct("") is None
    assert parse_pct(None) is None
    assert parse_pct("texto") is None


def test_simbolos_y_signos():
    assert parse_pct("0,3 %") == 0.3
    assert parse_pct("-0.300") == -0.3


def test_numeros_ya_numericos():
    assert parse_pct(0.3) == 0.3
    assert parse_pct(5) == 5.0
