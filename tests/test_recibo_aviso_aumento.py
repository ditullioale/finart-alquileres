"""En el recibo del mes inmediatamente anterior a un aumento programado, aparece
un recordatorio de que el mes siguiente se actualiza el precio del alquiler."""
from datetime import date

from app import db
from app.models import Persona, Inmueble, Contrato, Pago


def _contrato_con_aumento(app, tag, inicio, cada):
    """Contrato con ajuste cada 'cada' meses desde 'inicio'."""
    with app.app_context():
        prop = Persona(nombre=f"Prop Av {tag}", dni=f"66{tag}", es_propietario=True)
        inq = Persona(nombre=f"Inq Av {tag}", dni=f"67{tag}", es_inquilino=True)
        db.session.add_all([prop, inq]); db.session.commit()
        inm = Inmueble(direccion=f"Casa Av {tag}", tipo="Casa",
                       propietario_id=prop.id, moneda="Pesos")
        db.session.add(inm); db.session.commit()
        c = Contrato(inmueble_id=inm.id, inquilino_id=inq.id, propietario_id=prop.id,
                     fecha_inicio=inicio, precio_inicial=100000, precio_actual=100000,
                     estado="Vigente", metodo_ajuste="trimestral", ajuste_cada_meses=cada)
        db.session.add(c); db.session.commit()
        return c.id


def _pago(app, cid, mes, anio):
    with app.app_context():
        p = Pago(contrato_id=cid, periodo_mes=mes, periodo_anio=anio,
                 precio_alquiler=100000, total=100000, pagado=100000, estado="Pagado")
        db.session.add(p); db.session.commit()
        return p.id


def test_recibo_del_mes_previo_avisa(client):
    cl, app, ids = client
    # Inicio enero 2026, aumenta cada 3 meses => abril 2026 tiene aumento.
    cid = _contrato_con_aumento(app, "7001", date(2026, 1, 1), 3)
    # Recibo de marzo 2026 (mes anterior a abril): debe avisar.
    pid = _pago(app, cid, 3, 2026)
    html = cl.get(f"/recibos/pago/{pid}").get_data(as_text=True)
    assert "Recordatorio" in html
    assert "actualización del precio" in html


def test_recibo_de_otro_mes_no_avisa(client):
    cl, app, ids = client
    cid = _contrato_con_aumento(app, "7002", date(2026, 1, 1), 3)
    # Recibo de enero 2026 (febrero NO tiene aumento): no avisa.
    pid = _pago(app, cid, 1, 2026)
    html = cl.get(f"/recibos/pago/{pid}").get_data(as_text=True)
    assert "Recordatorio" not in html


def test_contrato_sin_ajuste_no_avisa(client):
    cl, app, ids = client
    with app.app_context():
        prop = Persona(nombre="Prop Av 7003", dni="667003", es_propietario=True)
        inq = Persona(nombre="Inq Av 7003", dni="677003", es_inquilino=True)
        db.session.add_all([prop, inq]); db.session.commit()
        inm = Inmueble(direccion="Casa Av 7003", tipo="Casa",
                       propietario_id=prop.id, moneda="Pesos")
        db.session.add(inm); db.session.commit()
        c = Contrato(inmueble_id=inm.id, inquilino_id=inq.id, propietario_id=prop.id,
                     fecha_inicio=date(2026, 1, 1), precio_inicial=100000,
                     precio_actual=100000, estado="Vigente", metodo_ajuste="sin_ajuste")
        db.session.add(c); db.session.commit()
        cid = c.id
    pid = _pago(app, cid, 3, 2026)
    html = cl.get(f"/recibos/pago/{pid}").get_data(as_text=True)
    assert "Recordatorio" not in html
