"""El botón de Ajustes que corrige la mora diaria mal cargada (300 -> 0,3)."""
from datetime import date

from app import db
from app.models import Contrato, Persona, Inmueble


def _contrato_con_mora(app, ids, mora, tag):
    """Crea inmueble + inquilino (con datos únicos por `tag`) y un contrato con
    la mora indicada. El tag evita choques de DNI en la base compartida."""
    with app.app_context():
        inq = Persona(nombre=f"Inq Mora {tag}", dni=f"4200{tag}", es_inquilino=True)
        inm = Inmueble(direccion=f"Casa Mora {tag}", tipo="Casa",
                       propietario_id=ids["prop"], moneda="Pesos")
        db.session.add_all([inq, inm]); db.session.commit()
        c = Contrato(inmueble_id=inm.id, inquilino_id=inq.id,
                     fecha_inicio=date(2026, 1, 1), precio_inicial=100000,
                     precio_actual=100000, mora_diaria_pct=mora, estado="Vigente")
        db.session.add(c); db.session.commit()
        return c.id


def test_corrige_mora_inflada(client):
    cl, app, ids = client
    cid = _contrato_con_mora(app, ids, 300, "0071")
    r = cl.post("/ajustes/mora/corregir", follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        c = db.session.get(Contrato, cid)
        assert float(c.mora_diaria_pct) == 0.3


def test_no_toca_mora_sana(client):
    cl, app, ids = client
    cid = _contrato_con_mora(app, ids, "0.4", "0072")   # ya está bien cargada
    cl.post("/ajustes/mora/corregir", follow_redirects=True)
    with app.app_context():
        c = db.session.get(Contrato, cid)
        assert float(c.mora_diaria_pct) == 0.4   # sin cambios


def test_ajustes_muestra_aviso_de_mora(client):
    cl, app, ids = client
    _contrato_con_mora(app, ids, 400, "0073")
    html = cl.get("/ajustes/").get_data(as_text=True)
    assert "Revisar mora diaria" in html
