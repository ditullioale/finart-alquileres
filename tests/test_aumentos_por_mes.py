"""Dos mejoras de aumentos:

1) El aviso de aumento corresponde al MES completo (desde el día 1), no al día
   exacto en que arrancó el contrato: si entró el 15 y viene a pagar el 10, el
   aumento de ese mes ya tiene que figurar.
2) El asistente IA puede decir qué contratos aumentan en un mes dado.
"""
from datetime import date

from app import db, asistente
from app.calculos import estado_aumento
from app.models import Contrato, Persona, Inmueble


def _mk_contrato(app, ids, inicio, cada, tag, pct=10):
    with app.app_context():
        inq = Persona(nombre=f"Inq Aum {tag}", dni=f"43{tag}", es_inquilino=True)
        inm = Inmueble(direccion=f"Casa Aum {tag}", tipo="Casa",
                       propietario_id=ids["prop"], moneda="Pesos")
        db.session.add_all([inq, inm]); db.session.commit()
        c = Contrato(inmueble_id=inm.id, inquilino_id=inq.id, fecha_inicio=inicio,
                     precio_inicial=100000, precio_actual=100000, estado="Vigente",
                     metodo_ajuste="porcentaje", porcentaje_ajuste=pct,
                     ajuste_cada_meses=cada)
        db.session.add(c); db.session.commit()
        return c.id


def test_aumento_pendiente_desde_el_1_del_mes(client):
    cl, app, ids = client
    # Arranca el 15/03/2025 y aumenta cada 6 meses -> corresponde el 15/09/2025.
    cid = _mk_contrato(app, ids, date(2025, 3, 15), 6, "9001")
    with app.app_context():
        c = db.session.get(Contrato, cid)
        # El 10/09, ANTES del día 15, ya debe figurar como pendiente.
        e = estado_aumento(c, date(2025, 9, 10))
        assert e["pendiente"] is True
        assert e["corresponde"] == date(2025, 9, 15)
        # A fin del mes anterior, todavía no.
        assert estado_aumento(c, date(2025, 8, 31))["pendiente"] is False


def test_ia_aumentos_del_mes(client):
    cl, app, ids = client
    _mk_contrato(app, ids, date(2025, 3, 15), 6, "9002")
    with app.app_context():
        r = asistente.h_aumentos_del_mes(mes=9, anio=2025)
        item = next((x for x in r["contratos"] if "9002" in x["inmueble"]), None)
        assert item is not None
        assert item["fecha_aumento"] == "2025-09-15"
        assert item["precio_estimado"] == 110000.0
        assert item["ya_aplicado"] is False


def test_ia_aumentos_del_mes_sin_aumentos(client):
    cl, app, ids = client
    # Un mes sin aumento para este contrato (arranca en marzo, cada 6 -> sep/mar).
    _mk_contrato(app, ids, date(2025, 3, 15), 6, "9003")
    with app.app_context():
        r = asistente.h_aumentos_del_mes(mes=10, anio=2025)
        assert not any("9003" in x["inmueble"] for x in r["contratos"])
