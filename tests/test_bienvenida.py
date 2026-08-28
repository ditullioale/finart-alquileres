"""Pruebas del mail de bienvenida al portal para inquilinos nuevos.

Nunca es automático: sale solo cuando se tilda el checkbox correspondiente al
dar de alta un CONTRATO -- tanto por el alta manual (/contratos/nuevo) como
por el generador (/contratos/desde-generador) -- y como mucho una vez por
persona (guardia por `bienvenida_enviada_at`)."""
import app.emailer as emailer_mod
from app import db
from app.bienvenida import enviar_bienvenida_inquilino
from app.models import Inmueble, Persona


def _capturar_email(monkeypatch):
    capt = {}

    def _fake(destino, asunto, cuerpo, adjunto=None, html=None):
        capt["to"] = destino
        capt["asunto"] = asunto
        capt["html"] = html
        return True

    monkeypatch.setattr(emailer_mod, "enviar_email", _fake)
    return capt


# --- Pruebas directas del helper -------------------------------------------

def test_no_manda_si_no_es_inquilino(app_seeded, monkeypatch):
    capt = _capturar_email(monkeypatch)
    with app_seeded.app_context():
        p = Persona(nombre="Test Uno", email="uno@mail.com", es_inquilino=False)
        db.session.add(p); db.session.commit()
        enviado, motivo = enviar_bienvenida_inquilino(p)
        assert not enviado
        assert "inquilino" in motivo
        assert "to" not in capt


def test_no_manda_si_no_tiene_email(app_seeded, monkeypatch):
    capt = _capturar_email(monkeypatch)
    with app_seeded.app_context():
        p = Persona(nombre="Test Dos", es_inquilino=True)
        db.session.add(p); db.session.commit()
        enviado, motivo = enviar_bienvenida_inquilino(p)
        assert not enviado
        assert "email" in motivo
        assert "to" not in capt


def test_no_manda_si_no_tiene_dni(app_seeded, monkeypatch):
    capt = _capturar_email(monkeypatch)
    with app_seeded.app_context():
        p = Persona(nombre="Test Dos B", email="dosb@mail.com", es_inquilino=True)
        db.session.add(p); db.session.commit()
        enviado, motivo = enviar_bienvenida_inquilino(p)
        assert not enviado
        assert "DNI" in motivo
        assert "to" not in capt


def test_manda_y_marca_timestamp(app_seeded, monkeypatch):
    capt = _capturar_email(monkeypatch)
    with app_seeded.test_request_context():
        p = Persona(nombre="Test Tres", email="tres@mail.com", dni="30111333",
                    es_inquilino=True)
        db.session.add(p); db.session.commit()
        enviado, motivo = enviar_bienvenida_inquilino(p)
        assert enviado
        assert motivo == "enviado"
        assert capt.get("to") == "tres@mail.com"
        assert capt.get("html") and "Test Tres" in capt["html"]
        assert p.bienvenida_enviada_at is not None


def test_no_reenvia_si_ya_se_mando(app_seeded, monkeypatch):
    capt = _capturar_email(monkeypatch)
    with app_seeded.test_request_context():
        p = Persona(nombre="Test Cuatro", email="cuatro@mail.com", dni="30111444",
                    es_inquilino=True)
        db.session.add(p); db.session.commit()
        enviar_bienvenida_inquilino(p)
        assert "to" in capt
        capt.clear()
        enviado, motivo = enviar_bienvenida_inquilino(p)
        assert not enviado
        assert "ya se le había mandado" in motivo
        assert "to" not in capt


# --- Integración: alta manual de contrato (/contratos/nuevo) ----------------
# app_seeded es de alcance de sesión: cada prueba usa su propia Persona/
# Inmueble nuevos (nunca ids["inq"] directo) para no ensuciar el estado de
# bienvenida_enviada_at entre pruebas.

def _crear_inquilino(app, nombre, email=None, dni="30222333"):
    with app.app_context():
        p = Persona(nombre=nombre, email=email, dni=dni, es_inquilino=True)
        db.session.add(p); db.session.commit()
        return p.id


def _crear_inmueble(app, direccion, propietario_id):
    with app.app_context():
        inm = Inmueble(direccion=direccion, tipo="Departamento",
                       propietario_id=propietario_id, moneda="Pesos")
        db.session.add(inm); db.session.commit()
        return inm.id


def _datos_contrato(inmueble_id, inquilino_id, **extra):
    d = dict(inmueble_id=inmueble_id, inquilino_id=inquilino_id,
             fecha_inicio="2026-01-01", precio_inicial="150000",
             metodo_ajuste="sin_ajuste", dia_vencimiento="10", moneda="Pesos")
    d.update(extra)
    return d


def test_alta_contrato_con_checkbox_manda_mail(client, monkeypatch):
    cl, app, ids = client
    capt = _capturar_email(monkeypatch)
    inq_id = _crear_inquilino(app, "Inquilino Alta 1", "alta1@mail.com")
    inm_id = _crear_inmueble(app, "Contrato Bienvenida 1", ids["prop"])
    r = cl.post("/contratos/nuevo",
                data=_datos_contrato(inm_id, inq_id, enviar_bienvenida="on"),
                follow_redirects=True)
    assert r.status_code == 200
    assert capt.get("to") == "alta1@mail.com"
    with app.app_context():
        p = db.session.get(Persona, inq_id)
        assert p.bienvenida_enviada_at is not None


def test_alta_contrato_sin_checkbox_no_manda_mail(client, monkeypatch):
    cl, app, ids = client
    capt = _capturar_email(monkeypatch)
    inq_id = _crear_inquilino(app, "Inquilino Alta 2", "alta2@mail.com")
    inm_id = _crear_inmueble(app, "Contrato Bienvenida 2", ids["prop"])
    r = cl.post("/contratos/nuevo", data=_datos_contrato(inm_id, inq_id),
                follow_redirects=True)
    assert r.status_code == 200
    assert "to" not in capt


def test_alta_contrato_inquilino_sin_email_no_manda_mail(client, monkeypatch):
    cl, app, ids = client
    capt = _capturar_email(monkeypatch)
    inq_id = _crear_inquilino(app, "Inquilino Alta 3")  # sin email
    inm_id = _crear_inmueble(app, "Contrato Bienvenida 3", ids["prop"])
    r = cl.post("/contratos/nuevo",
                data=_datos_contrato(inm_id, inq_id, enviar_bienvenida="on"),
                follow_redirects=True)
    assert r.status_code == 200
    assert "to" not in capt


def test_alta_contrato_no_reenvia_segunda_vez(client, monkeypatch):
    cl, app, ids = client
    capt = _capturar_email(monkeypatch)
    inq_id = _crear_inquilino(app, "Inquilino Alta 4", "alta4@mail.com")
    inm_a = _crear_inmueble(app, "Contrato Bienvenida 4a", ids["prop"])
    inm_b = _crear_inmueble(app, "Contrato Bienvenida 4b", ids["prop"])

    cl.post("/contratos/nuevo",
            data=_datos_contrato(inm_a, inq_id, enviar_bienvenida="on"),
            follow_redirects=True)
    assert capt.get("to") == "alta4@mail.com"
    capt.clear()

    # Mismo inquilino en un contrato nuevo (otro inmueble): no se reenvía
    # aunque el checkbox venga tildado de nuevo.
    cl.post("/contratos/nuevo",
            data=_datos_contrato(inm_b, inq_id, enviar_bienvenida="on"),
            follow_redirects=True)
    assert "to" not in capt


# --- Integración: generador de contratos ------------------------------------

def test_generador_con_enviar_bienvenida_manda_mail(client, monkeypatch):
    cl, app, ids = client
    capt = _capturar_email(monkeypatch)
    payload = {
        "loc": {"nombre": "Propietario Gen"},
        "lat": {"nombre": "Inquilino Generador", "email": "gen.inq@mail.com", "dni": "30333444"},
        "inm": {"dir": "Calle Generador 123"},
        "econ": {"canon": "150000", "plazo": "24"},
        "fiadores": [], "coLoc": [], "coLat": [],
        "documento": "", "pagares": "",
        "enviarBienvenida": True,
    }
    r = cl.post("/contratos/desde-generador", json=payload)
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True
    assert capt.get("to") == "gen.inq@mail.com"
    with app.app_context():
        p = Persona.query.filter_by(email="gen.inq@mail.com").first()
        assert p is not None and p.bienvenida_enviada_at is not None


def test_generador_sin_enviar_bienvenida_no_manda_mail(client, monkeypatch):
    cl, app, ids = client
    capt = _capturar_email(monkeypatch)
    payload = {
        "loc": {"nombre": "Propietario Gen2"},
        "lat": {"nombre": "Inquilino Generador2", "email": "gen2.inq@mail.com"},
        "inm": {"dir": "Calle Generador 456"},
        "econ": {"canon": "150000", "plazo": "24"},
        "fiadores": [], "coLoc": [], "coLat": [],
        "documento": "", "pagares": "",
        "enviarBienvenida": False,
    }
    r = cl.post("/contratos/desde-generador", json=payload)
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    assert "to" not in capt
