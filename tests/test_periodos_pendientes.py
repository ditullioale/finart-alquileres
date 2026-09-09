"""«Pagos anteriores» / deuda: el mes en curso cuyo vencimiento todavía no llegó
NO debe figurar como período pendiente (no está atrasado)."""
from datetime import date

from app import db
from app.blueprints.cobros import _periodos_pendientes
from app.models import Contrato, Persona, Inmueble


def _contrato(app, ids):
    with app.app_context():
        inq = Persona(nombre="Inq PP", dni="45000111", es_inquilino=True)
        inm = Inmueble(direccion="Casa PP", tipo="Casa",
                       propietario_id=ids["prop"], moneda="Pesos")
        db.session.add_all([inq, inm]); db.session.commit()
        c = Contrato(inmueble_id=inm.id, inquilino_id=inq.id, fecha_inicio=date(2026, 7, 1),
                     precio_inicial=100000, precio_actual=100000, estado="Vigente",
                     dia_vencimiento=10, metodo_ajuste="sin_ajuste")
        db.session.add(c); db.session.commit()
        return c.id


def test_excluye_mes_en_curso_sin_vencer(client):
    cl, app, ids = client
    cid = _contrato(app, ids)
    with app.app_context():
        c = db.session.get(Contrato, cid)
        # Hoy 09/09: septiembre vence el 10 -> todavía no vencido.
        meses = {(p["mes"], p["anio"]) for p in _periodos_pendientes(c, date(2026, 9, 9))}
        assert (9, 2026) not in meses      # mes en curso sin vencer: NO
        assert (7, 2026) in meses          # julio atrasado: sí
        assert (8, 2026) in meses          # agosto atrasado: sí


def test_incluye_el_mes_cuando_vence(client):
    cl, app, ids = client
    cid = _contrato(app, ids)
    with app.app_context():
        c = db.session.get(Contrato, cid)
        # El 10/09 (día de vencimiento) ya corresponde.
        meses = {(p["mes"], p["anio"]) for p in _periodos_pendientes(c, date(2026, 9, 10))}
        assert (9, 2026) in meses
