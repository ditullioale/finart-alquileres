"""El tipo de aviso "Deuda de gas" arma el texto con la deuda de la cuenta del
inmueble del inquilino. (Sin credenciales de Litoral Gas cargadas, la
verificación en el momento es un no-op y usa el último dato guardado.)"""
from datetime import date

from app import db
from app.models import Persona, Inmueble, Contrato, GasEstado, Usuario


def _sembrar_gas(app, tag, con_deuda=True):
    with app.app_context():
        tid = Usuario.query.filter_by(username="admin").first().inmobiliaria_id
        cuenta = f"GAS{tag}"
        inq = Persona(nombre=f"Inq Gas {tag}", dni=f"80{tag}", es_inquilino=True,
                      inmobiliaria_id=tid)
        db.session.add(inq); db.session.commit()
        inm = Inmueble(direccion=f"Casa Gas {tag}", tipo="Casa", moneda="Pesos",
                       cuenta_gas=cuenta, inmobiliaria_id=tid)
        db.session.add(inm); db.session.commit()
        c = Contrato(inmueble_id=inm.id, inquilino_id=inq.id, fecha_inicio=date(2026, 1, 1),
                     precio_inicial=100000, precio_actual=100000, estado="Vigente",
                     metodo_ajuste="sin_ajuste", inmobiliaria_id=tid)
        db.session.add(c); db.session.commit()
        g = GasEstado(cuenta=cuenta, inmobiliaria_id=tid, tiene_deuda=con_deuda,
                      deuda_total=(50000 if con_deuda else 0))
        db.session.add(g); db.session.commit()
        return inq.id


def test_datos_gas_con_deuda(client):
    cl, app, ids = client
    pid = _sembrar_gas(app, "1", con_deuda=True)
    r = cl.get(f"/notificaciones/datos?persona_id={pid}&tipo=Deuda de gas")
    j = r.get_json()
    assert j["ok"] is True
    assert "deuda" in j["texto"].lower()
    assert "50.000" in j["texto"]


def test_datos_gas_sin_deuda(client):
    cl, app, ids = client
    pid = _sembrar_gas(app, "2", con_deuda=False)
    r = cl.get(f"/notificaciones/datos?persona_id={pid}&tipo=Deuda de gas")
    j = r.get_json()
    assert j["ok"] is True
    assert "no registra deuda" in j["texto"].lower()
