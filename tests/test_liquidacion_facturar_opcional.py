"""Al generar una liquidación, la factura de honorarios en ARCA es opcional:
solo se emite si se tilda «Emitir factura en ARCA»."""
from datetime import date

from app import db
from app.models import Persona, Inmueble, Contrato
import app.blueprints.liquidaciones as liqmod


def _armar_y_cobrar(app, cl, ids, tag):
    with app.app_context():
        prop = Persona(nombre=f"Prop Fact {tag}", dni=f"46{tag}",
                       cuit="20305903990", es_propietario=True)
        inq = Persona(nombre=f"Inq Fact {tag}", dni=f"47{tag}", es_inquilino=True)
        db.session.add_all([prop, inq]); db.session.commit()
        inm = Inmueble(direccion=f"Casa Fact {tag}", tipo="Casa",
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
    return pid


def _contar_facturados(monkeypatch):
    llam = {"n": 0}
    monkeypatch.setattr(liqmod, "_facturar_honorarios",
                        lambda *a, **k: (llam.__setitem__("n", llam["n"] + 1), "emitida")[1])
    return llam


def test_generar_sin_tildar_no_factura(client, monkeypatch):
    cl, app, ids = client
    llam = _contar_facturados(monkeypatch)
    pid = _armar_y_cobrar(app, cl, ids, "8001")
    hoy = date.today()
    cl.post("/liquidaciones/generar",
            data={"propietario_id": pid, "mes": hoy.month, "anio": hoy.year},
            follow_redirects=True)
    assert llam["n"] == 0


def test_generar_tildado_factura(client, monkeypatch):
    cl, app, ids = client
    llam = _contar_facturados(monkeypatch)
    pid = _armar_y_cobrar(app, cl, ids, "8002")
    hoy = date.today()
    cl.post("/liquidaciones/generar",
            data={"propietario_id": pid, "mes": hoy.month, "anio": hoy.year,
                  "facturar_arca": "1"},
            follow_redirects=True)
    assert llam["n"] == 1
