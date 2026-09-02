"""Pruebas de dos mejoras del alta de contrato:

1) El alta rápida de personas (/personas/nueva-rapida) guarda también email y
   teléfono, no solo nombre y DNI. Así, un inquilino cargado sin salir de la
   pantalla de nuevo contrato queda listo para recibir el mail de bienvenida.

2) Los conceptos fijos del contrato (ej.: seguro) se cobran junto con el
   alquiler en cada recibo, conservando si se trasladan al propietario en la
   liquidación o si quedan para la inmobiliaria.
"""
from datetime import date

from app import db
from app.models import Persona, Inmueble, Contrato, ContratoConcepto


# --- 1) Alta rápida con email y teléfono -----------------------------------

def test_nueva_rapida_guarda_email_y_telefono(client):
    cl, app, ids = client
    r = cl.post("/personas/nueva-rapida", json={
        "nombre": "Rápido Con Mail", "dni": "40555666",
        "email": "rapido@mail.com", "telefono": "3415551234", "rol": "inquilino"})
    assert r.status_code == 200
    j = r.get_json()
    assert j["ok"] is True
    assert j.get("email") == "rapido@mail.com"
    assert j.get("telefono") == "3415551234"
    with app.app_context():
        p = db.session.get(Persona, j["id"])
        assert p.es_inquilino is True
        assert p.email == "rapido@mail.com"
        assert p.telefono == "3415551234"


# --- 2) Conceptos fijos en cada cobro --------------------------------------

def _contrato_con_concepto(app, ids, traslada="0", monto="5000"):
    """Crea inmueble + inquilino y un contrato con un concepto fijo 'Seguro'."""
    with app.app_context():
        inq = Persona(nombre="Inq Conceptos", dni="41000111", es_inquilino=True)
        inm = Inmueble(direccion="Casa Conceptos", tipo="Casa",
                       propietario_id=ids["prop"], moneda="Pesos")
        db.session.add_all([inq, inm]); db.session.commit()
        inq_id, inm_id = inq.id, inm.id
    return inq_id, inm_id


def _crear_contrato_via_form(cl, inm_id, inq_id, **concepto):
    data = dict(inmueble_id=inm_id, inquilino_id=inq_id,
                fecha_inicio="2026-01-01", precio_inicial="150000",
                metodo_ajuste="sin_ajuste", dia_vencimiento="10", moneda="Pesos")
    data.update(concepto)
    return cl.post("/contratos/nuevo", data=data, follow_redirects=True)


def test_concepto_fijo_se_guarda_en_el_contrato(client):
    cl, app, ids = client
    inq_id, inm_id = _contrato_con_concepto(app, ids)
    r = _crear_contrato_via_form(cl, inm_id, inq_id,
                                 concepto_desc="Seguro", concepto_monto="5000",
                                 concepto_traslada="0")
    assert r.status_code == 200
    with app.app_context():
        c = Contrato.query.filter_by(inmueble_id=inm_id).first()
        assert c is not None
        conceptos = list(c.conceptos_fijos)
        assert len(conceptos) == 1
        assert conceptos[0].descripcion == "Seguro"
        assert float(conceptos[0].monto) == 5000
        assert conceptos[0].trasladar_liquidacion is False


def test_concepto_fijo_aparece_en_cobro_rapido(client):
    cl, app, ids = client
    inq_id, inm_id = _contrato_con_concepto(app, ids)
    _crear_contrato_via_form(cl, inm_id, inq_id,
                             concepto_desc="Seguro", concepto_monto="5000",
                             concepto_traslada="0")
    with app.app_context():
        cid = Contrato.query.filter_by(inmueble_id=inm_id).first().id

    hoy = date.today()
    r = cl.post("/cobros/rapido", json={
        "cid": cid, "mes": hoy.month, "anio": hoy.year,
        "precio": 150000, "pagado": 155000})
    assert r.status_code == 200 and r.get_json()["ok"] is True

    with app.app_context():
        c = db.session.get(Contrato, cid)
        pago = c.pagos[-1]
        seguros = [g for g in pago.gastos if g.descripcion == "Seguro"]
        assert len(seguros) == 1
        assert float(seguros[0].monto) == 5000
        assert seguros[0].trasladar_liquidacion is False
        # El total del recibo suma el alquiler + el seguro.
        assert float(pago.total) == 155000


def test_concepto_fijo_no_se_duplica_si_ya_viene_cargado(client):
    cl, app, ids = client
    inq_id, inm_id = _contrato_con_concepto(app, ids)
    _crear_contrato_via_form(cl, inm_id, inq_id,
                             concepto_desc="Seguro", concepto_monto="5000",
                             concepto_traslada="1")
    with app.app_context():
        cid = Contrato.query.filter_by(inmueble_id=inm_id).first().id

    hoy = date.today()
    # El cobro rápido ya trae un gasto "Seguro" a mano: no debe duplicarse.
    r = cl.post("/cobros/rapido", json={
        "cid": cid, "mes": hoy.month, "anio": hoy.year, "precio": 150000,
        "gastos": [{"desc": "Seguro", "monto": 6000, "trasladar": True}]})
    assert r.status_code == 200 and r.get_json()["ok"] is True

    with app.app_context():
        c = db.session.get(Contrato, cid)
        pago = c.pagos[-1]
        seguros = [g for g in pago.gastos if g.descripcion == "Seguro"]
        assert len(seguros) == 1
        # Gana el que cargó el usuario a mano (6000), no el concepto fijo.
        assert float(seguros[0].monto) == 6000
