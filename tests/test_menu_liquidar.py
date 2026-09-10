"""En el menú (…) de cada contrato aparece "Liquidar alquiler" solo cuando hay
un cobro del mes en curso todavía sin liquidar al propietario."""
from datetime import date

from app import db
from app.models import Contrato, Persona, Inmueble


def _contrato(app, ids):
    with app.app_context():
        inq = Persona(nombre="Inq LiqMenu ZZQ", dni="48000111", es_inquilino=True)
        inm = Inmueble(direccion="Casa LiqMenu ZZQ", tipo="Casa",
                       propietario_id=ids["prop"], moneda="Pesos")
        db.session.add_all([inq, inm]); db.session.commit()
        c = Contrato(inmueble_id=inm.id, inquilino_id=inq.id, propietario_id=ids["prop"],
                     fecha_inicio=date(2026, 1, 1), precio_inicial=100000,
                     precio_actual=100000, estado="Vigente", metodo_ajuste="sin_ajuste")
        db.session.add(c); db.session.commit()
        return c.id


def test_liquidar_en_menu_solo_con_cobro_pendiente(client):
    cl, app, ids = client
    cid = _contrato(app, ids)
    # Sin cobro del mes: la opción no aparece.
    html0 = cl.get("/contratos/?q=ZZQ").get_data(as_text=True)
    assert "Liquidar alquiler" not in html0
    # Registro el cobro del mes en curso (queda sin liquidar al propietario).
    hoy = date.today()
    r = cl.post("/cobros/rapido", json={"cid": cid, "mes": hoy.month, "anio": hoy.year,
                                        "precio": 100000, "pagado": 100000})
    assert r.status_code == 200
    html1 = cl.get("/contratos/?q=ZZQ").get_data(as_text=True)
    assert "Liquidar alquiler" in html1
