"""El generador no debe crear el mismo contrato muchas veces. Si ya hay un
contrato vigente para el mismo inmueble e inquilino, pide confirmación; solo con
confirmarDuplicado=True carga otro."""
from app import db
from app.models import Contrato


def _payload(tag):
    return {
        "loc": {"nombre": f"Propietario Dup {tag}", "dni": f"30{tag}"},
        "lat": {"nombre": f"Inquilino Dup {tag}", "dni": f"31{tag}"},
        "inm": {"dir": f"Calle Falsa {tag} 123", "ciudad": "Rosario"},
        "econ": {"canon": "500000", "plazo": "24", "fechaFirma": "2026-10-01"},
        "fiadores": [],
    }


def test_no_duplica_sin_confirmar(client):
    cl, app, ids = client
    p = _payload("A1")

    # 1er guardado: crea el contrato.
    r1 = cl.post("/contratos/desde-generador", json=p)
    assert r1.get_json()["ok"] is True

    # 2do guardado idéntico: NO crea otro, pide confirmación.
    r2 = cl.post("/contratos/desde-generador", json=p)
    j2 = r2.get_json()
    assert j2["ok"] is False
    assert j2.get("duplicado") is True

    with app.app_context():
        n = Contrato.query.filter_by(estado="Vigente").join(Contrato.inmueble).filter_by(
            direccion="Calle Falsa A1 123").count()
        assert n == 1  # sigue habiendo uno solo


def test_confirmando_carga_otro(client):
    cl, app, ids = client
    p = _payload("A2")
    cl.post("/contratos/desde-generador", json=p)

    p2 = dict(p); p2["confirmarDuplicado"] = True
    r = cl.post("/contratos/desde-generador", json=p2)
    assert r.get_json()["ok"] is True

    with app.app_context():
        n = (Contrato.query.filter_by(estado="Vigente")
             .join(Contrato.inmueble).filter_by(direccion="Calle Falsa A2 123").count())
        assert n == 2
