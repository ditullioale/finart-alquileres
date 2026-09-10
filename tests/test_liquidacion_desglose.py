"""En el resumen de la liquidación, los gastos extra trasladados se desglosan por
su concepto real (no con un texto genérico), agrupando por descripción."""
from app.blueprints.liquidaciones import _desglose_extras


def test_desglosa_y_agrupa_por_concepto():
    items = [
        {"gastos": [{"descripcion": "Seguro", "monto": 5000},
                    {"descripcion": "Agua", "monto": 3000}]},
        {"gastos": [{"descripcion": "Seguro", "monto": 5000}]},
        {"gastos": []},
    ]
    d = _desglose_extras(items)
    por = {x["descripcion"]: x["monto"] for x in d}
    assert por == {"Seguro": 10000.0, "Agua": 3000.0}


def test_conserva_descuentos_negativos():
    items = [{"gastos": [{"descripcion": "Descuento cuota arreglos", "monto": -100000}]}]
    d = _desglose_extras(items)
    assert d == [{"descripcion": "Descuento cuota arreglos", "monto": -100000.0}]


def test_sin_gastos_da_lista_vacia():
    assert _desglose_extras([{"gastos": []}, {"gastos": None}]) == []
