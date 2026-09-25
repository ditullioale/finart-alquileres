"""Al borrar un suministro del panel de gas, la cuenta se desvincula del inmueble
para que la propiedad vuelva a quedar disponible (antes quedaba 'colgada')."""
from app import db
from app.models import Inmueble, GasEstado, Usuario


def _seed(app, tag):
    with app.app_context():
        tid = Usuario.query.filter_by(username="admin").first().inmobiliaria_id
        cuenta = f"GASDEL{tag}"
        inm = Inmueble(direccion=f"Casa GasDel {tag}", tipo="Casa", moneda="Pesos",
                       cuenta_gas=cuenta, inmobiliaria_id=tid)
        db.session.add(inm); db.session.commit()
        g = GasEstado(cuenta=cuenta, inmobiliaria_id=tid, tiene_deuda=True, deuda_total=1000)
        db.session.add(g); db.session.commit()
        return inm.id, g.id, cuenta


def test_borrar_suministro_desvincula_inmueble(client):
    cl, app, ids = client
    inm_id, gid, cuenta = _seed(app, "1")

    r = cl.post(f"/gas/{gid}/eliminar", follow_redirects=True)
    assert r.status_code == 200

    with app.app_context():
        assert db.session.get(GasEstado, gid) is None            # se borró el estado
        inm = db.session.get(Inmueble, inm_id)
        assert (inm.cuenta_gas or "") == ""                       # y se desvinculó la cuenta
