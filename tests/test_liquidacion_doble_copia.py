"""La pantalla de la liquidación al propietario permite imprimir DOS copias:
una para el propietario (ORIGINAL) y otra de respaldo para la inmobiliaria."""
from datetime import date

from app import db
from app.models import Persona, Inmueble, Contrato


def _armar(app, tag):
    with app.app_context():
        prop = Persona(nombre=f"Prop Doble {tag}", dni=f"58{tag}", cuit="20305903990",
                       es_propietario=True)
        inq = Persona(nombre=f"Inq Doble {tag}", dni=f"59{tag}", es_inquilino=True)
        db.session.add_all([prop, inq]); db.session.commit()
        inm = Inmueble(direccion=f"Casa Doble {tag}", tipo="Casa", moneda="Pesos",
                       propietario_id=prop.id, comision_pct=8)
        db.session.add(inm); db.session.commit()
        c = Contrato(inmueble_id=inm.id, inquilino_id=inq.id, propietario_id=prop.id,
                     fecha_inicio=date(2026, 1, 1), precio_inicial=500000, precio_actual=500000,
                     estado="Vigente", metodo_ajuste="sin_ajuste", comision_pct=8)
        db.session.add(c); db.session.commit()
        return prop.id, c.id


def test_liquidacion_tiene_impresion_doble(client):
    cl, app, ids = client
    pid, cid = _armar(app, "1")
    hoy = date.today()
    cl.post("/cobros/rapido", json={"cid": cid, "mes": hoy.month, "anio": hoy.year,
                                    "precio": 500000, "pagado": 500000})
    cl.post("/liquidaciones/generar",
            data={"propietario_id": pid, "mes": hoy.month, "anio": hoy.year},
            follow_redirects=True)

    html = cl.get(f"/liquidaciones/imprimir/{pid}?mes={hoy.month}&anio={hoy.year}").get_data(as_text=True)
    assert "Imprimir 2 copias" in html
    assert "function imprimirDoble()" in html
    assert "ORIGINAL — PROPIETARIO" in html
    assert "DUPLICADO — RESPALDO INMOBILIARIA" in html
