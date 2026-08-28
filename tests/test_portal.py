"""Pruebas del portal de autoservicio (inquilinos/propietarios).

Dos formas de entrar, ambas abren la misma sesión de portal:
- Login principal con email + DNI (/portal/acceder).
- Enlace de un solo uso por email (/portal/enlace + /portal/verificar/<token>),
  para quien no tenga el DNI a mano.
"""
import re

import pytest

from app import db
from app.models import Persona, Pago, Inmobiliaria
import app.emailer as emailer_mod


EMAIL_INQ = "guido@mail.com"  # sembrado por tests_qa.sembrar() como inq (inquilino)


def _capturar_email(monkeypatch):
    """Reemplaza enviar_email por una captura, igual que hace tests_qa.py para 2FA."""
    capt = {}

    def _fake(destino, asunto, cuerpo, adjunto=None, html=None):
        m = re.search(r"(https?://\S+/portal/verificar/\S+)", cuerpo or "")
        capt["to"] = destino
        capt["asunto"] = asunto
        capt["link"] = m.group(1) if m else None
        return True

    monkeypatch.setattr(emailer_mod, "enviar_email", _fake)
    return capt


def _token_de(link):
    """Extrae el token de un link completo de verificación."""
    return link.rstrip("/").rsplit("/", 1)[-1]


def _crear_persona(app, nombre, email, dni, es_inquilino=True):
    with app.app_context():
        p = Persona(nombre=nombre, email=email, dni=dni, es_inquilino=es_inquilino)
        db.session.add(p); db.session.commit()
        return p.id


# --- Login principal: email + DNI -------------------------------------------

def test_login_dni_correcto_entra_al_panel(app_seeded):
    _crear_persona(app_seeded, "Persona Dni Uno", "dniuno@mail.com", "30111555")
    cl = app_seeded.test_client()
    r = cl.post("/portal/acceder", data={"email": "dniuno@mail.com", "dni": "30111555"},
                follow_redirects=True)
    assert r.status_code == 200
    body = r.data.decode("utf-8", "ignore")
    assert "Persona Dni Uno" in body or "dniuno@mail.com" in body


def test_login_dni_acepta_puntos_y_espacios(app_seeded):
    _crear_persona(app_seeded, "Persona Dni Dos", "dnidos@mail.com", "30.111.666")
    cl = app_seeded.test_client()
    r = cl.post("/portal/acceder", data={"email": "dnidos@mail.com", "dni": "30 111 666"},
                follow_redirects=True)
    assert r.status_code == 200
    assert "Persona Dni Dos" in r.data.decode("utf-8", "ignore")


def test_login_dni_incorrecto_error_generico(app_seeded):
    _crear_persona(app_seeded, "Persona Dni Tres", "dnitres@mail.com", "30111777")
    cl = app_seeded.test_client()
    r = cl.post("/portal/acceder", data={"email": "dnitres@mail.com", "dni": "11111111"},
                follow_redirects=True)
    assert r.status_code == 200
    assert "no coinciden" in r.data.decode("utf-8", "ignore")


def test_login_email_desconocido_mismo_error_generico(app_seeded):
    cl = app_seeded.test_client()
    r = cl.post("/portal/acceder", data={"email": "nadie@noexiste.com", "dni": "12345678"},
                follow_redirects=True)
    assert r.status_code == 200
    assert "no coinciden" in r.data.decode("utf-8", "ignore")


def test_panel_sin_sesion_redirige_a_acceder(app_seeded):
    cl = app_seeded.test_client()
    r = cl.get("/portal/", follow_redirects=True)
    assert r.status_code == 200
    assert "email y tu DNI" in r.data.decode("utf-8", "ignore")


# --- Enlace de un solo uso (respaldo sin DNI) --------------------------------

def test_enlace_con_email_conocido_envia_link(app_seeded, monkeypatch):
    capt = _capturar_email(monkeypatch)
    cl = app_seeded.test_client()
    r = cl.post("/portal/enlace", data={"email": EMAIL_INQ}, follow_redirects=True)
    assert r.status_code == 200
    assert capt.get("to") == EMAIL_INQ
    assert capt.get("link"), "el mail debería incluir el enlace de verificación"
    body = r.data.decode("utf-8", "ignore")
    assert "enviamos un enlace de acceso" in body


def test_enlace_con_email_desconocido_mismo_mensaje_sin_enviar(app_seeded, monkeypatch):
    capt = _capturar_email(monkeypatch)
    cl = app_seeded.test_client()
    r = cl.post("/portal/enlace", data={"email": "nadie@noexiste.com"},
                follow_redirects=True)
    assert r.status_code == 200
    assert "to" not in capt, "no debe enviarse ningún email para un email no registrado"
    body = r.data.decode("utf-8", "ignore")
    assert "enviamos un enlace de acceso" in body  # mismo mensaje: no hay enumeración


def test_enlace_con_email_invalido_muestra_error(app_seeded, monkeypatch):
    capt = _capturar_email(monkeypatch)
    cl = app_seeded.test_client()
    r = cl.post("/portal/enlace", data={"email": "no-es-un-email"},
                follow_redirects=True)
    assert r.status_code == 200
    assert "to" not in capt
    assert "email válido" in r.data.decode("utf-8", "ignore")


def test_verificar_token_valido_entra_al_panel(app_seeded, monkeypatch):
    capt = _capturar_email(monkeypatch)
    cl = app_seeded.test_client()
    cl.post("/portal/enlace", data={"email": EMAIL_INQ})
    token = _token_de(capt["link"])

    r = cl.get(f"/portal/verificar/{token}", follow_redirects=True)
    assert r.status_code == 200
    body = r.data.decode("utf-8", "ignore")
    assert "Santamaria Guido" in body or EMAIL_INQ in body
    assert "Local San Martin 830" in body  # dirección del inmueble del contrato sembrado


def test_verificar_token_invalido_rebota_con_error(app_seeded):
    cl = app_seeded.test_client()
    r = cl.get("/portal/verificar/esto-no-es-un-token-valido", follow_redirects=True)
    assert r.status_code == 200
    assert "no es válido" in r.data.decode("utf-8", "ignore")


def test_verificar_token_expirado_rebota_con_error(app_seeded, monkeypatch):
    import app.blueprints.portal as portal_mod
    capt = _capturar_email(monkeypatch)
    cl = app_seeded.test_client()
    cl.post("/portal/enlace", data={"email": EMAIL_INQ})
    token = _token_de(capt["link"])

    monkeypatch.setattr(portal_mod, "_MAX_AGE", -1)  # cualquier token ya "vencido"
    r = cl.get(f"/portal/verificar/{token}", follow_redirects=True)
    assert r.status_code == 200
    assert "venció" in r.data.decode("utf-8", "ignore")


def test_recibo_pdf_ajeno_da_404(app_seeded, monkeypatch):
    """Un pago que pertenece al contrato de otra persona (inq2) no debe poder
    descargarse desde la sesión de portal de EMAIL_INQ (inq)."""
    with app_seeded.app_context():
        ids = app_seeded._ids
        inmo = Inmobiliaria.principal()
        pago_ajeno = Pago(inmobiliaria_id=inmo.id, contrato_id=ids["c2"],
                          numero=1, periodo_mes=1, periodo_anio=2026,
                          total=200000, saldo=0, moneda="Pesos", estado="Pagado")
        db.session.add(pago_ajeno)
        db.session.commit()
        pago_id = pago_ajeno.id

    capt = _capturar_email(monkeypatch)
    cl = app_seeded.test_client()
    cl.post("/portal/enlace", data={"email": EMAIL_INQ})
    token = _token_de(capt["link"])
    cl.get(f"/portal/verificar/{token}")

    r = cl.get(f"/portal/recibo/{pago_id}/pdf")
    assert r.status_code == 404
