"""Pruebas de notificaciones al portal: alta desde la app (con mail) y
recepción del lado del portal (pop-up obligatorio + historial)."""
import re

import pytest

from app import db
from app.models import Persona, Notificacion, NotificacionDestinatario
import app.emailer as emailer_mod


def _capturar_email(monkeypatch):
    capt = {}

    def _fake(destino, asunto, cuerpo, adjunto=None, html=None):
        capt["to"] = destino
        capt["asunto"] = asunto
        capt["html"] = html
        return True

    monkeypatch.setattr(emailer_mod, "enviar_email", _fake)
    return capt


def _crear_persona(app, nombre, email, dni, es_inquilino=True):
    with app.app_context():
        p = Persona(nombre=nombre, email=email, dni=dni, es_inquilino=es_inquilino)
        db.session.add(p); db.session.commit()
        return p.id


def _crear_notificacion_directa(app, persona_id, tipo="Mora", mensaje="Tenés un pago pendiente."):
    with app.app_context():
        n = Notificacion(tipo=tipo, mensaje=mensaje, creada_por="admin")
        db.session.add(n); db.session.flush()
        d = NotificacionDestinatario(notificacion_id=n.id, persona_id=persona_id)
        db.session.add(d); db.session.commit()
        return n.id, d.id


# --- Alta desde la app (staff) -----------------------------------------------

def test_nueva_crea_notificacion_y_manda_mail(client, monkeypatch):
    cl, app, ids = client
    capt = _capturar_email(monkeypatch)
    pid = _crear_persona(app, "Notif Uno", "notifuno@mail.com", "30222111")

    r = cl.post("/notificaciones/nueva", data={
        "tipo": "Mora", "mensaje": "Tenés un pago atrasado de julio.",
        "persona_id": [str(pid)],
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "Notificación cargada" in r.data.decode("utf-8", "ignore")
    assert capt.get("to") == "notifuno@mail.com"
    assert "novedades en tu portal" in capt.get("asunto", "")
    assert "Tenés un pago atrasado de julio." in (capt.get("html") or "")

    with app.app_context():
        d = NotificacionDestinatario.query.filter_by(persona_id=pid).first()
        assert d is not None
        assert d.mail_enviado_at is not None
        assert d.notificacion.tipo == "Mora"


def test_nueva_sin_mensaje_muestra_error(client):
    cl, app, ids = client
    pid = _crear_persona(app, "Notif Dos", "notifdos@mail.com", "30222222")
    r = cl.post("/notificaciones/nueva", data={
        "tipo": "Aumento", "mensaje": "", "persona_id": [str(pid)],
    }, follow_redirects=True)
    assert "Escribí el contenido del aviso" in r.data.decode("utf-8", "ignore")
    with app.app_context():
        assert NotificacionDestinatario.query.filter_by(persona_id=pid).count() == 0


def test_nueva_sin_destinatarios_muestra_error(client):
    cl, app, ids = client
    r = cl.post("/notificaciones/nueva", data={
        "tipo": "Otro", "mensaje": "Aviso general",
    }, follow_redirects=True)
    assert "Elegí al menos un destinatario" in r.data.decode("utf-8", "ignore")


def test_nueva_persona_sin_email_no_manda_pero_queda_creada(client, monkeypatch):
    cl, app, ids = client
    capt = _capturar_email(monkeypatch)
    pid = _crear_persona(app, "Notif Sin Mail", None, "30222333")

    r = cl.post("/notificaciones/nueva", data={
        "tipo": "Arreglo", "mensaje": "Van a arreglar la caldera.", "persona_id": [str(pid)],
    }, follow_redirects=True)
    assert "no tiene(n) email cargado" in r.data.decode("utf-8", "ignore")
    assert "to" not in capt
    with app.app_context():
        d = NotificacionDestinatario.query.filter_by(persona_id=pid).first()
        assert d is not None
        assert d.mail_enviado_at is None


def test_nueva_a_varios_destinatarios_crea_un_solo_destinatario_por_persona(client, monkeypatch):
    cl, app, ids = client
    _capturar_email(monkeypatch)
    p1 = _crear_persona(app, "Notif Multi Uno", "multiuno@mail.com", "30333111")
    p2 = _crear_persona(app, "Notif Multi Dos", "multidos@mail.com", "30333222")

    cl.post("/notificaciones/nueva", data={
        "tipo": "Otro", "mensaje": "Aviso para ambos.",
        "persona_id": [str(p1), str(p2)],
    }, follow_redirects=True)

    with app.app_context():
        n = Notificacion.query.filter_by(mensaje="Aviso para ambos.").first()
        assert n is not None
        assert len(n.destinatarios) == 2


# --- Lado del portal ----------------------------------------------------------

def test_portal_muestra_popup_con_notificacion_pendiente(app_seeded):
    pid = _crear_persona(app_seeded, "Portal Notif Uno", "portalnotif1@mail.com", "30444111")
    _crear_notificacion_directa(app_seeded, pid, "Mora", "Tenés un pago pendiente de agosto.")

    cl = app_seeded.test_client()
    cl.post("/portal/acceder", data={"email": "portalnotif1@mail.com", "dni": "30444111"})
    r = cl.get("/portal/")
    body = r.data.decode("utf-8", "ignore")
    assert "Tenés un pago pendiente de agosto." in body
    assert "Aceptar" in body


def test_portal_sin_notificaciones_no_muestra_popup(app_seeded):
    pid = _crear_persona(app_seeded, "Portal Notif Vacio", "portalnotifvacio@mail.com", "30444222")
    cl = app_seeded.test_client()
    cl.post("/portal/acceder", data={"email": "portalnotifvacio@mail.com", "dni": "30444222"})
    r = cl.get("/portal/")
    assert "notif-pop" not in r.data.decode("utf-8", "ignore")


def test_portal_aceptar_marca_vista_y_deja_de_aparecer(app_seeded):
    pid = _crear_persona(app_seeded, "Portal Notif Dos", "portalnotif2@mail.com", "30444333")
    _, did = _crear_notificacion_directa(app_seeded, pid, "Aumento", "Tu alquiler va a aumentar.")

    cl = app_seeded.test_client()
    cl.post("/portal/acceder", data={"email": "portalnotif2@mail.com", "dni": "30444333"})

    r = cl.post(f"/portal/notificaciones/{did}/aceptar", follow_redirects=True)
    assert r.status_code == 200
    assert "notif-pop" not in r.data.decode("utf-8", "ignore")

    with app_seeded.app_context():
        d = db.session.get(NotificacionDestinatario, did)
        assert d.vista_at is not None


def test_portal_historial_muestra_vistas_y_pendientes(app_seeded):
    pid = _crear_persona(app_seeded, "Portal Notif Tres", "portalnotif3@mail.com", "30444444")
    _crear_notificacion_directa(app_seeded, pid, "Mora", "Aviso uno.")
    _crear_notificacion_directa(app_seeded, pid, "Otro", "Aviso dos.")

    cl = app_seeded.test_client()
    cl.post("/portal/acceder", data={"email": "portalnotif3@mail.com", "dni": "30444444"})
    r = cl.get("/portal/notificaciones")
    body = r.data.decode("utf-8", "ignore")
    assert "Aviso uno." in body
    assert "Aviso dos." in body
    assert "Pendiente" in body


def test_portal_no_ve_notificacion_de_otra_persona(app_seeded):
    ajeno = _crear_persona(app_seeded, "Portal Notif Ajeno", "portalnotifajeno@mail.com", "30444555")
    _crear_notificacion_directa(app_seeded, ajeno, "Mora", "Aviso que no es tuyo.")
    mio = _crear_persona(app_seeded, "Portal Notif Propio", "portalnotifpropio@mail.com", "30444666")

    cl = app_seeded.test_client()
    cl.post("/portal/acceder", data={"email": "portalnotifpropio@mail.com", "dni": "30444666"})
    r = cl.get("/portal/notificaciones")
    assert "Aviso que no es tuyo." not in r.data.decode("utf-8", "ignore")


def test_portal_aceptar_notificacion_ajena_da_404(app_seeded):
    ajeno = _crear_persona(app_seeded, "Portal Notif Ajeno2", "portalnotifajeno2@mail.com", "30444777")
    _, did = _crear_notificacion_directa(app_seeded, ajeno, "Mora", "Aviso ajeno.")
    _crear_persona(app_seeded, "Portal Notif Propio2", "portalnotifpropio2@mail.com", "30444888")

    cl = app_seeded.test_client()
    cl.post("/portal/acceder", data={"email": "portalnotifpropio2@mail.com", "dni": "30444888"})
    r = cl.post(f"/portal/notificaciones/{did}/aceptar")
    assert r.status_code == 404
