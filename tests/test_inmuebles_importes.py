"""El alta de inmuebles tiene que entender el formato de importes es-AR.

Antes '250.000' se guardaba como 275500 (el punto se borraba y la coma decimal de
otro campo desordenaba el número) y '8,5' de comisión terminaba en 850.
"""


def test_alta_guarda_precio_y_comision_en_formato_argentino(client):
    cl, app, _ = client
    resp = cl.post("/inmuebles/nuevo", data={
        "codigo": "FMT-1", "tipo": "Departamento", "direccion": "Mitre 100",
        "localidad": "Rosario", "estado": "Disponible", "moneda": "Pesos",
        "dormitorios": "2", "banos": "1",
        "precio_referencia": "250.000", "comision_pct": "8,5",
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        from app.models import Inmueble
        i = Inmueble.query.filter_by(codigo="FMT-1").one()
        assert i.precio_referencia == 250000
        assert i.comision_pct == 8.5
        assert i.dormitorios == 2 and i.banos == 1
