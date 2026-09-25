"""Un contrato que empieza en el futuro (ej.: octubre) no debe generar deuda ni
permitir cobros de meses anteriores (septiembre)."""
from datetime import date

from app import db
from app.models import Persona, Inmueble, Contrato
from app.calculos import estado_periodo, periodo_antes_del_inicio, deuda_real


def _prox_mes(d):
    return (1, d.year + 1) if d.month == 12 else (d.month + 1, d.year)


def _contrato_que_empieza_el_mes_que_viene(app, tag):
    mes_sig, anio_sig = _prox_mes(date.today())
    with app.app_context():
        prop = Persona(nombre=f"Prop Ini {tag}", dni=f"70{tag}", es_propietario=True)
        inq = Persona(nombre=f"Inq Ini {tag}", dni=f"71{tag}", es_inquilino=True)
        db.session.add_all([prop, inq]); db.session.commit()
        inm = Inmueble(direccion=f"Casa Ini {tag}", tipo="Casa",
                       propietario_id=prop.id, moneda="Pesos")
        db.session.add(inm); db.session.commit()
        c = Contrato(inmueble_id=inm.id, inquilino_id=inq.id, propietario_id=prop.id,
                     fecha_inicio=date(anio_sig, mes_sig, 1), precio_inicial=600000,
                     precio_actual=600000, estado="Vigente", metodo_ajuste="sin_ajuste",
                     dia_vencimiento=10)
        db.session.add(c); db.session.commit()
        return c.id


def test_mes_previo_no_es_deuda(client):
    cl, app, ids = client
    cid = _contrato_que_empieza_el_mes_que_viene(app, "6001")
    hoy = date.today()
    with app.app_context():
        c = db.session.get(Contrato, cid)
        info = estado_periodo(c, hoy.month, hoy.year, hoy=hoy)
        assert info["estado"] == "Fuera de vigencia"
        assert info["saldo"] == 0.0
        assert deuda_real(c, hoy) == 0.0
        assert periodo_antes_del_inicio(c, hoy.month, hoy.year) is True


def test_cobro_rapido_rechaza_mes_previo(client):
    cl, app, ids = client
    cid = _contrato_que_empieza_el_mes_que_viene(app, "6002")
    hoy = date.today()
    # Intentar cobrar el mes actual (anterior al inicio) -> rechazado.
    r = cl.post("/cobros/rapido", json={"cid": cid, "mes": hoy.month, "anio": hoy.year,
                                        "precio": 600000, "pagado": 600000})
    assert r.status_code == 400
    assert "mes anterior" in (r.get_json() or {}).get("error", "")
