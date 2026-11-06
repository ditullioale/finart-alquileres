"""Firma manuscrita digital del propietario sobre la liquidación (flujo PC -> celular)."""
import base64
import io
from datetime import date

import pytest
from app import db
from app.models import (Persona, Inmueble, Contrato, Pago, Liquidacion,
                        LiquidacionFirma, FirmaSesion)

pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402


def _png_firma():
    img = Image.new("RGBA", (300, 150), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    d.line([(10, 120), (120, 30), (200, 110), (280, 40)], fill=(0, 0, 0, 255), width=3)
    buf = io.BytesIO(); img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _liq_generada(app, cl, tag):
    with app.app_context():
        prop = Persona(nombre=f"Prop Firma {tag}", dni=f"62{tag}", cuit="20630990", es_propietario=True)
        inq = Persona(nombre=f"Inq Firma {tag}", dni=f"63{tag}", es_inquilino=True)
        db.session.add_all([prop, inq]); db.session.commit()
        inm = Inmueble(direccion=f"Casa Firma {tag}", tipo="Casa", propietario_id=prop.id, comision_pct=8)
        db.session.add(inm); db.session.commit()
        c = Contrato(inmueble_id=inm.id, inquilino_id=inq.id, propietario_id=prop.id,
                     fecha_inicio=date(2026, 1, 1), precio_inicial=500000, precio_actual=500000,
                     estado="Vigente", metodo_ajuste="sin_ajuste", comision_pct=8)
        db.session.add(c); db.session.commit()
        pid, cid = prop.id, c.id
    hoy = date.today()
    cl.post("/cobros/rapido", json={"cid": cid, "mes": hoy.month, "anio": hoy.year,
                                    "precio": 500000, "pagado": 500000})
    cl.post("/liquidaciones/generar", data={"propietario_id": pid, "mes": hoy.month,
                                            "anio": hoy.year}, follow_redirects=True)
    with app.app_context():
        return Liquidacion.query.filter_by(propietario_id=pid).first().id


def _firmar(cl, lid, **extra):
    body = {"firma": _png_firma(), "conforme": True, "consentimiento": "Declaro recibir...",
            "firmante": "Propietario X", "firmante_dni": "20630990",
            "trazos": [[{"x": 1, "y": 2, "t": 0}, {"x": 5, "y": 9, "t": 120}]],
            "puntero": "touch", "pantalla": "412x915", "duracion_ms": 1800,
            "puntos": 2, "trazos_n": 1}
    body.update(extra)
    return cl.post(f"/liquidaciones/{lid}/firmar", json=body)


def test_flujo_pc_a_celular(client):
    cl, app, ids = client
    lid = _liq_generada(app, cl, "1")
    # PC envía al celular
    assert cl.post(f"/liquidaciones/{lid}/enviar-firma").get_json()["ok"] is True
    # el celular ve el pendiente
    pend = cl.get("/liquidaciones/firmar/pendiente").get_json()
    assert pend["hay"] is True and pend["liq_id"] == lid
    # firma
    assert _firmar(cl, lid).get_json()["ok"] is True
    # queda firmada, con toda la evidencia, y el pendiente se limpió
    with app.app_context():
        f = db.session.get(Liquidacion, lid).firma
        assert f is not None
        assert len(f.sha256) == 64 and f.trazos and f.ip is not None
        assert f.firma_png and len(f.firma_png) > 800
        assert FirmaSesion.query.first().pendiente_liq_id is None
    assert cl.get(f"/liquidaciones/{lid}/firma-estado").get_json()["firmada"] is True
    assert cl.get(f"/liquidaciones/{lid}/firma.png").status_code == 200


def test_no_se_firma_dos_veces(client):
    cl, app, ids = client
    lid = _liq_generada(app, cl, "2")
    assert _firmar(cl, lid).get_json()["ok"] is True
    assert _firmar(cl, lid).status_code == 409


def test_firma_en_blanco_rechazada(client):
    cl, app, ids = client
    lid = _liq_generada(app, cl, "3")
    r = _firmar(cl, lid, firma="data:image/png;base64,iVBORw0KGgo=")  # PNG minúsculo
    assert r.get_json()["ok"] is False


def test_sin_conformidad_no_firma(client):
    cl, app, ids = client
    lid = _liq_generada(app, cl, "4")
    assert _firmar(cl, lid, conforme=False).get_json()["ok"] is False


def test_verificacion_detecta_integridad(client):
    cl, app, ids = client
    lid = _liq_generada(app, cl, "5")
    _firmar(cl, lid)
    html = cl.get(f"/liquidaciones/{lid}/firma/verificar").get_data(as_text=True)
    assert "Evidencia íntegra" in html
    # si alguien altera el snapshot guardado, la verificación lo detecta
    with app.app_context():
        f = db.session.get(Liquidacion, lid).firma
        f.snapshot = (f.snapshot or "") + " ALTERADO"
        db.session.commit()
    html2 = cl.get(f"/liquidaciones/{lid}/firma/verificar").get_data(as_text=True)
    assert "NO coincide" in html2


def test_liquidacion_firmada_no_se_borra_sin_confirmar(client):
    cl, app, ids = client
    lid = _liq_generada(app, cl, "6")
    _firmar(cl, lid)
    cl.post(f"/liquidaciones/{lid}/eliminar", follow_redirects=True)
    with app.app_context():
        assert db.session.get(Liquidacion, lid) is not None   # bloqueada
    cl.post(f"/liquidaciones/{lid}/eliminar", data={"confirmar_firmada": "1"}, follow_redirects=True)
    with app.app_context():
        assert db.session.get(Liquidacion, lid) is None        # con confirmación, se borra
