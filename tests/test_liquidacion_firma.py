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


def test_pdf_firmado_congelado(client):
    cl, app, ids = client
    lid = _liq_generada(app, cl, "7")
    _firmar(cl, lid)
    with app.app_context():
        f = db.session.get(Liquidacion, lid).firma
        assert f.pdf_firmado and len(f.pdf_firmado) > 1000
        assert len(f.pdf_sha256) == 64
    r = cl.get(f"/liquidaciones/{lid}/firmado.pdf")
    assert r.status_code == 200 and r.content_type == "application/pdf"
    assert r.data[:4] == b"%PDF"


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


def test_cadena_de_firmas_encadena_y_detecta_borrado(client):
    cl, app, ids = client
    l1 = _liq_generada(app, cl, "8a"); _firmar(cl, l1)
    l2 = _liq_generada(app, cl, "8b"); _firmar(cl, l2)
    with app.app_context():
        f1 = db.session.get(Liquidacion, l1).firma
        f2 = db.session.get(Liquidacion, l2).firma
        # (la base de los tests es compartida, así que f1 no es necesariamente la
        # génesis; lo que importa es que f2 encadene con f1)
        assert f1.hash_cadena and f2.hash_prev == f1.hash_cadena
    # la verificación de f2 muestra la cadena intacta
    assert "Cadena de firmas intacta" in cl.get(f"/liquidaciones/{l2}/firma/verificar").get_data(as_text=True)
    # si se borra la firma anterior, la cadena de f2 se detecta rota
    with app.app_context():
        liq1 = db.session.get(Liquidacion, l1)
        db.session.delete(liq1.firma); db.session.commit()
    assert "Cadena de firmas rota" in cl.get(f"/liquidaciones/{l2}/firma/verificar").get_data(as_text=True)


def test_email_al_propietario_con_pdf(client, monkeypatch):
    import app.emailer as em
    enviados = []
    monkeypatch.setattr(em, "enviar_email",
                        lambda destino, asunto, cuerpo, adjunto=None, html=None:
                        (enviados.append((destino, adjunto[0] if adjunto else None)), True)[1])
    cl, app, ids = client
    # propietario con email
    with app.app_context():
        prop = Persona(nombre="Prop Mail", dni="74001", cuit="20740010",
                       email="propmail@mail.com", es_propietario=True)
        inq = Persona(nombre="Inq Mail", dni="74002", es_inquilino=True)
        db.session.add_all([prop, inq]); db.session.commit()
        inm = Inmueble(direccion="Casa Mail", tipo="Casa", propietario_id=prop.id, comision_pct=8)
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
        lid = Liquidacion.query.filter_by(propietario_id=pid).first().id
    r = _firmar(cl, lid)
    assert r.get_json()["emailado"] is True
    assert enviados and enviados[0][0] == "propmail@mail.com"
    assert enviados[0][1].endswith(".pdf")   # con el PDF adjunto


def test_email_del_formulario_se_usa_y_se_completa(client, monkeypatch):
    """El propietario completa el mail en el panel al firmar: se le manda el PDF a ese
    mail, queda en la evidencia y, si no tenía mail cargado, se lo completamos."""
    import app.emailer as em
    enviados = []
    monkeypatch.setattr(em, "enviar_email",
                        lambda destino, asunto, cuerpo, adjunto=None, html=None:
                        (enviados.append(destino), True)[1])
    cl, app, ids = client
    lid = _liq_generada(app, cl, "mail1")   # el propietario se crea SIN email
    r = _firmar(cl, lid, firmante_email="nuevo@mail.com")
    assert r.get_json()["emailado"] is True
    assert enviados and enviados[0] == "nuevo@mail.com"
    with app.app_context():
        liq = db.session.get(Liquidacion, lid)
        assert liq.firma.firmante_email == "nuevo@mail.com"   # queda en la evidencia
        assert liq.propietario.email == "nuevo@mail.com"       # se completó para la próxima


def test_acuse_pixel_y_confirmacion_solo_por_post(client, monkeypatch):
    import app.emailer as em
    monkeypatch.setattr(em, "enviar_email", lambda *a, **k: True)  # el envío "funciona"
    cl, app, ids = client
    lid = _liq_generada(app, cl, "ac1")
    _firmar(cl, lid, firmante_email="dest@mail.com")
    with app.app_context():
        f = db.session.get(Liquidacion, lid).firma
        token = f.acuse_token
        assert token and f.email_enviado_at is not None
        assert f.email_abierto_at is None and f.email_confirmado_at is None
    # El píxel registra la apertura y devuelve un PNG.
    r = cl.get(f"/liquidaciones/firma/acuse/{token}/abierto.png")
    assert r.status_code == 200 and r.content_type == "image/png"
    # ABRIR el enlace (GET) NO confirma: solo muestra la página con el botón.
    g = cl.get(f"/liquidaciones/firma/acuse/{token}/confirmar")
    assert g.status_code == 200 and "Confirmá la recepción" in g.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Liquidacion, lid).firma.email_confirmado_at is None
    # Solo el POST (el clic real del botón) confirma la recepción.
    p = cl.post(f"/liquidaciones/firma/acuse/{token}/confirmar")
    assert p.status_code == 200 and "confirmada" in p.get_data(as_text=True).lower()
    with app.app_context():
        f = db.session.get(Liquidacion, lid).firma
        assert f.email_abierto_at is not None and f.email_confirmado_at is not None
        assert f.email_confirmado_ua is not None and (f.acuse_intentos or 0) >= 1
    # Token inexistente -> 404.
    assert cl.get("/liquidaciones/firma/acuse/noexiste/confirmar").status_code == 404
    # La verificación refleja el acuse confirmado.
    html = cl.get(f"/liquidaciones/{lid}/firma/verificar").get_data(as_text=True)
    assert "Acuse de recepción del mail" in html
    assert "todavía no confirmó" not in html


def test_no_se_firma_ni_se_envia_liquidacion_anulada(client):
    cl, app, ids = client
    lid = _liq_generada(app, cl, "an1")
    # Anulamos una liquidación SIN firma previa (vía POST directo).
    cl.post(f"/liquidaciones/{lid}/anular", data={"motivo": "prueba"}, follow_redirects=True)
    with app.app_context():
        assert db.session.get(Liquidacion, lid).anulada is True
    # No se puede enviar a firmar ni firmar.
    assert cl.post(f"/liquidaciones/{lid}/enviar-firma").status_code == 409
    assert _firmar(cl, lid).status_code == 409
    # La pantalla de firma avisa que está anulada.
    g = cl.get(f"/liquidaciones/{lid}/firmar")
    assert "anulada" in g.get_data(as_text=True).lower()
    with app.app_context():
        assert db.session.get(Liquidacion, lid).firma is None


def test_liquidacion_firmada_no_se_puede_borrar(client):
    """Una liquidación firmada NO se borra nunca (ni con confirmación): destruiría la
    evidencia. El camino correcto es anular."""
    cl, app, ids = client
    lid = _liq_generada(app, cl, "6")
    _firmar(cl, lid)
    cl.post(f"/liquidaciones/{lid}/eliminar", follow_redirects=True)
    with app.app_context():
        assert db.session.get(Liquidacion, lid) is not None   # bloqueada
    # Incluso forzando el viejo flag, sigue sin borrarse.
    cl.post(f"/liquidaciones/{lid}/eliminar", data={"confirmar_firmada": "1"},
            follow_redirects=True)
    with app.app_context():
        liq = db.session.get(Liquidacion, lid)
        assert liq is not None and liq.firma is not None       # firma intacta


def test_anular_conserva_evidencia_y_libera_cobros(client):
    cl, app, ids = client
    lid = _liq_generada(app, cl, "6b")
    _firmar(cl, lid)
    with app.app_context():
        f = db.session.get(Liquidacion, lid).firma
        sha_antes, pdf_antes = f.sha256, bool(f.pdf_firmado)
    # Sin motivo no anula.
    cl.post(f"/liquidaciones/{lid}/anular", data={}, follow_redirects=True)
    with app.app_context():
        assert db.session.get(Liquidacion, lid).anulada is False
    # Con motivo: anula conservando TODA la evidencia.
    cl.post(f"/liquidaciones/{lid}/anular",
            data={"motivo": "Monto mal cargado"}, follow_redirects=True)
    with app.app_context():
        liq = db.session.get(Liquidacion, lid)
        assert liq.anulada is True
        assert liq.anulacion_motivo == "Monto mal cargado"
        assert liq.anulada_en is not None
        # La firma, el PDF y el hash siguen ahí (constancia intacta).
        assert liq.firma is not None and liq.firma.sha256 == sha_antes
        assert bool(liq.firma.pdf_firmado) == pdf_antes
        # Los cobros volvieron a pendientes de liquidar (pagado_al_propietario = None).
        pend = _pagos_periodo_pendientes(liq)
        assert pend and all(p.pagado_al_propietario is None for p in pend)
    # El PDF firmado de la anulada sigue siendo descargable (evidencia accesible).
    assert cl.get(f"/liquidaciones/{lid}/firmado.pdf").status_code == 200


def _pagos_periodo_pendientes(liq):
    from app.blueprints.liquidaciones import _pagos_periodo
    return _pagos_periodo(liq.propietario_id, liq.periodo_mes, liq.periodo_anio,
                          contrato_id=liq.contrato_id)


def test_pdf_entra_en_el_hash_y_se_verifica(client):
    """El hash principal cubre el PDF congelado: alterar el PDF rompe la verificación
    del PDF, y el hash guardado se recomputa incluyendo pdf_sha256."""
    cl, app, ids = client
    lid = _liq_generada(app, cl, "9z")
    _firmar(cl, lid)
    with app.app_context():
        f = db.session.get(Liquidacion, lid).firma
        import hashlib
        base = (f.snapshot or "").encode() + (f.trazos or "").encode() + (f.firma_png or b"")
        esperado = hashlib.sha256(base + (f.pdf_sha256 or "").encode()).hexdigest()
        assert f.sha256 == esperado            # el hash incluye el PDF
        assert f.pdf_sha256 and len(f.pdf_sha256) == 64
    html = cl.get(f"/liquidaciones/{lid}/firma/verificar").get_data(as_text=True)
    assert "Evidencia íntegra" in html
    assert "PDF congelado íntegro" in html
