"""Configuración de pytest (Fase 3.1).

Organiza el testing con pytest SIN tirar las suites que ya andan: las envolvemos
como pruebas de pytest (ver test_legacy_suites.py) y agregamos pruebas nativas nuevas
(como el E2E). Este conftest prepara una base temporal aislada para las pruebas
in-process.
"""
import os
import pathlib
import sys
import tempfile

# La app se importa desde la raíz del repo.
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Modo pruebas (desactiva CSRF y usa create_all en vez de migraciones).
os.environ["TESTING"] = "1"
# Base SQLite temporal, aislada de la de desarrollo.
if not os.environ.get("DATABASE_URL"):
    _tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    _tmp.close()
    os.environ["DATABASE_URL"] = "sqlite:///" + _tmp.name

import pytest  # noqa: E402

from app import create_app, db  # noqa: E402
import tests_qa  # noqa: E402


@pytest.fixture(scope="session")
def app_seeded():
    """App lista, con datos sembrados una vez (inmobiliaria, admin, propietario con
    CUIT, inquilino, inmueble y contrato)."""
    app = create_app()
    with app.app_context():
        db.create_all()
        ids = tests_qa.sembrar()
        from app.models import Persona, Contrato
        prop = db.session.get(Persona, ids["prop"])
        prop.cuit = "20305903990"          # el propietario factura: necesita CUIT
        c = db.session.get(Contrato, ids["c"])
        c.comision_pct = 5                 # 5% de comisión para que haya honorarios
        db.session.commit()
    app._ids = ids
    return app


@pytest.fixture
def client(app_seeded):
    """Cliente HTTP logueado como admin, junto con los ids sembrados."""
    c = app_seeded.test_client()
    c.post("/login", data={"username": "admin", "password": "admin123"})
    return c, app_seeded, app_seeded._ids
