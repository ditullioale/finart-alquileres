"""El 'nro de pago' interno del contrato debe seguir el PERÍODO (mes/año), no la
fecha de carga: si se registra septiembre antes que agosto, agosto igual queda 1
y septiembre 2."""
from datetime import date

from app import db
from app.models import Contrato, Persona, Inmueble


def _contrato(app, ids, tag):
    with app.app_context():
        inq = Persona(nombre=f"Inq Nro {tag}", dni=f"44{tag}", es_inquilino=True)
        inm = Inmueble(direccion=f"Casa Nro {tag}", tipo="Casa",
                       propietario_id=ids["prop"], moneda="Pesos")
        db.session.add_all([inq, inm]); db.session.commit()
        c = Contrato(inmueble_id=inm.id, inquilino_id=inq.id,
                     fecha_inicio=date(2026, 8, 1), precio_inicial=400000,
                     precio_actual=400000, estado="Vigente", metodo_ajuste="sin_ajuste")
        db.session.add(c); db.session.commit()
        return c.id


def _cobrar(cl, cid, mes, anio):
    return cl.post("/cobros/rapido", json={"cid": cid, "mes": mes, "anio": anio,
                                           "precio": 400000, "pagado": 400000})


def test_numero_sigue_al_periodo_no_a_la_carga(client):
    cl, app, ids = client
    cid = _contrato(app, ids, "9101")
    # Se carga PRIMERO septiembre y DESPUÉS agosto (fuera de orden).
    assert _cobrar(cl, cid, 9, 2026).status_code == 200
    assert _cobrar(cl, cid, 8, 2026).status_code == 200
    with app.app_context():
        c = db.session.get(Contrato, cid)
        por_periodo = {(p.periodo_mes): p.numero for p in c.pagos}
        assert por_periodo[8] == 1   # agosto, aunque se cargó segundo
        assert por_periodo[9] == 2   # septiembre, aunque se cargó primero


def test_detalle_autocorrige_numeracion_vieja(client):
    cl, app, ids = client
    cid = _contrato(app, ids, "9102")
    # Simulo datos viejos cargados al revés (número por fecha de carga).
    with app.app_context():
        c = db.session.get(Contrato, cid)
        from app.models import Pago
        db.session.add_all([
            Pago(contrato_id=c.id, numero=1, periodo_mes=9, periodo_anio=2026,
                 precio_alquiler=400000, total=400000, pagado=400000, saldo=0, estado="Pagado"),
            Pago(contrato_id=c.id, numero=2, periodo_mes=8, periodo_anio=2026,
                 precio_alquiler=400000, total=400000, pagado=400000, saldo=0, estado="Pagado"),
        ])
        db.session.commit()
    # Al abrir el detalle, se autocorrige.
    assert cl.get(f"/cobros/contrato/{cid}").status_code == 200
    with app.app_context():
        c = db.session.get(Contrato, cid)
        por_periodo = {(p.periodo_mes): p.numero for p in c.pagos}
        assert por_periodo[8] == 1
        assert por_periodo[9] == 2
