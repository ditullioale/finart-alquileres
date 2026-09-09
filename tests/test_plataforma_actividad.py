"""El panel de plataforma (superadmin) muestra la actividad por inmobiliaria:
última actividad, movimientos recientes y cantidad de contratos/pagos."""
from app import db
from app.models import Usuario


def _login_super(app):
    with app.app_context():
        if not Usuario.query.filter_by(username="superx").first():
            u = Usuario(username="superx", nombre="Super X", rol="superadmin")
            u.set_password("superx12345")
            db.session.add(u); db.session.commit()
    c = app.test_client()
    c.post("/login", data={"username": "superx", "password": "superx12345"})
    return c


def test_panel_actividad_abre(app_seeded):
    c = _login_super(app_seeded)
    r = c.get("/plataforma/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Inmobiliarias y actividad" in html
    assert "Movim. 7d" in html


def test_panel_actividad_solo_superadmin(client):
    # Un admin normal no accede al panel de plataforma.
    cl, app, ids = client
    r = cl.get("/plataforma/", follow_redirects=False)
    assert r.status_code in (302, 403)
