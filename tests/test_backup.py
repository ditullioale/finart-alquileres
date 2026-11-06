"""Respaldo lógico de la base: solo el superadmin puede bajarlo; un admin normal no."""
import io
import zipfile

from werkzeug.security import generate_password_hash

from app import db
from app.models import Usuario


def _crear_superadmin(app):
    with app.app_context():
        u = Usuario(username="superbk", rol="superadmin", inmobiliaria_id=None)
        if hasattr(u, "set_password"):
            u.set_password("superbk123")
        else:
            u.password_hash = generate_password_hash("superbk123")
        db.session.add(u); db.session.commit()


def test_backup_superadmin_descarga_zip(client):
    cl, app, ids = client
    _crear_superadmin(app)
    s = app.test_client()
    s.post("/login", data={"username": "superbk", "password": "superbk123"})
    r = s.get("/plataforma/backup")
    assert r.status_code == 200
    assert r.content_type == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.data))
    nombres = z.namelist()
    assert "_backup.json" in nombres
    assert "liquidaciones_firmas.json" in nombres   # las firmas entran en el respaldo


def test_backup_admin_normal_prohibido(client):
    cl, app, ids = client   # 'client' ya está logueado como admin normal
    assert cl.get("/plataforma/backup").status_code == 403
