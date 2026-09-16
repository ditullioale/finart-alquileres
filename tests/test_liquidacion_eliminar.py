"""Se puede borrar una liquidación ya generada: se elimina la liquidación (y sus
conceptos) y los cobros vuelven a quedar pendientes de liquidar. Si la liquidación
tiene una factura de honorarios YA EMITIDA en ARCA, sólo se borra confirmando."""
from datetime import date

from app import db
from app.models import Persona, Inmueble, Contrato, Pago, Liquidacion, ConceptoLiquidacion


def _armar_y_cobrar(app, cl, tag):
    with app.app_context():
        prop = Persona(nombre=f"Prop Del {tag}", dni=f"56{tag}",
                       cuit="20305903990", es_propietario=True)
        inq = Persona(nombre=f"Inq Del {tag}", dni=f"57{tag}", es_inquilino=True)
        db.session.add_all([prop, inq]); db.session.commit()
        inm = Inmueble(direccion=f"Casa Del {tag}", tipo="Casa",
                       propietario_id=prop.id, moneda="Pesos")
        db.session.add(inm); db.session.commit()
        c = Contrato(inmueble_id=inm.id, inquilino_id=inq.id, propietario_id=prop.id,
                     fecha_inicio=date(2026, 1, 1), precio_inicial=100000,
                     precio_actual=100000, estado="Vigente", comision_pct=5,
                     metodo_ajuste="sin_ajuste")
        db.session.add(c); db.session.commit()
        pid, cid = prop.id, c.id
    hoy = date.today()
    cl.post("/cobros/rapido", json={"cid": cid, "mes": hoy.month, "anio": hoy.year,
                                    "precio": 100000, "pagado": 100000})
    return pid, cid


def _generar(cl, pid):
    hoy = date.today()
    cl.post("/liquidaciones/generar",
            data={"propietario_id": pid, "mes": hoy.month, "anio": hoy.year},
            follow_redirects=True)


def test_borrar_libera_los_cobros(client):
    cl, app, ids = client
    pid, cid = _armar_y_cobrar(app, cl, "9001")
    _generar(cl, pid)

    with app.app_context():
        liq = Liquidacion.query.filter_by(propietario_id=pid).first()
        assert liq is not None
        liq_id = liq.id
        # el cobro quedó marcado como liquidado al propietario
        pago = Pago.query.filter_by(contrato_id=cid,
                                    periodo_mes=date.today().month,
                                    periodo_anio=date.today().year).first()
        assert pago.pagado_al_propietario is not None

    cl.post(f"/liquidaciones/{liq_id}/eliminar", follow_redirects=True)

    with app.app_context():
        assert db.session.get(Liquidacion, liq_id) is None
        assert ConceptoLiquidacion.query.filter_by(liquidacion_id=liq_id).count() == 0
        # el cobro vuelve a quedar pendiente de liquidar
        pago = Pago.query.filter_by(contrato_id=cid,
                                    periodo_mes=date.today().month,
                                    periodo_anio=date.today().year).first()
        assert pago.pagado_al_propietario is None


def test_facturada_no_se_borra_sin_confirmar(client):
    cl, app, ids = client
    pid, _cid = _armar_y_cobrar(app, cl, "9002")
    _generar(cl, pid)

    with app.app_context():
        liq = Liquidacion.query.filter_by(propietario_id=pid).first()
        liq.factura_estado = "emitida"      # simula factura ya emitida en ARCA
        liq.factura_cae = "75000000000001"
        db.session.commit()
        liq_id = liq.id

    # sin confirmar: NO se borra
    cl.post(f"/liquidaciones/{liq_id}/eliminar", follow_redirects=True)
    with app.app_context():
        assert db.session.get(Liquidacion, liq_id) is not None

    # confirmando: se borra
    cl.post(f"/liquidaciones/{liq_id}/eliminar",
            data={"confirmar_facturada": "1"}, follow_redirects=True)
    with app.app_context():
        assert db.session.get(Liquidacion, liq_id) is None
