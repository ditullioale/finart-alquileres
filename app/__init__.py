"""Application factory del sistema de gestión de alquileres."""
import os

from flask import Flask, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_migrate import Migrate

from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Iniciá sesión para continuar."
csrf = CSRFProtect()
migrate = Migrate()

# Carpeta de migraciones de Alembic (en la raíz del proyecto, junto a app/).
_MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations")


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # En pruebas automáticas se desactiva la verificación CSRF (los tests no
    # mandan token). En producción queda activa.
    if os.environ.get("TESTING"):
        app.config["WTF_CSRF_ENABLED"] = False

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db, directory=_MIGRATIONS_DIR)

    from .models import Usuario

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(Usuario, int(user_id))

    # Blueprints
    from .blueprints.auth import auth_bp
    from .blueprints.main import main_bp
    from .blueprints.personas import personas_bp
    from .blueprints.inmuebles import inmuebles_bp
    from .blueprints.contratos import contratos_bp
    from .blueprints.cobros import cobros_bp
    from .blueprints.aumentos import aumentos_bp
    from .blueprints.recibos import recibos_bp
    from .blueprints.ajustes import ajustes_bp
    from .blueprints.liquidaciones import liquidaciones_bp
    from .blueprints.usuarios import usuarios_bp
    from .blueprints.gas import gas_bp
    from .blueprints.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(personas_bp)
    app.register_blueprint(inmuebles_bp)
    app.register_blueprint(contratos_bp)
    app.register_blueprint(cobros_bp)
    app.register_blueprint(aumentos_bp)
    app.register_blueprint(recibos_bp)
    app.register_blueprint(ajustes_bp)
    app.register_blueprint(liquidaciones_bp)
    app.register_blueprint(usuarios_bp)
    app.register_blueprint(gas_bp)
    app.register_blueprint(api_bp)

    # El buzón del robot de gas usa su propio token (X-Gas-Token), no CSRF.
    csrf.exempt(app.view_functions["gas.importar"])

    # Si el usuario debe cambiar su contraseña (p.ej. admin por defecto), se lo
    # obliga a hacerlo antes de usar el resto del sistema.
    @app.before_request
    def _forzar_cambio_clave():
        from flask_login import current_user
        if not getattr(current_user, "is_authenticated", False):
            return
        if not getattr(current_user, "must_change_password", False):
            return
        permitidos = {"usuarios.cambiar_clave", "auth.logout", "static",
                      "manifest", "service_worker", "assetlinks"}
        if request.endpoint in permitidos:
            return
        flash("Por seguridad, cambiá la contraseña por defecto antes de continuar.", "error")
        return redirect(url_for("usuarios.cambiar_clave"))

    # Aviso global: cantidad de aumentos vencidos (badge en el menú).
    @app.context_processor
    def _aumentos_pendientes():
        from flask_login import current_user
        if not getattr(current_user, "is_authenticated", False):
            return dict(aumentos_pendientes=0)
        try:
            from datetime import date
            from .models import Contrato
            from .utils import proximo_ajuste
            hoy = date.today()
            n = 0
            for c in Contrato.query.filter_by(estado="Vigente").all():
                if c.metodo_ajuste == "sin_ajuste" or not c.ajuste_cada_meses:
                    continue
                if c.aumento_pospuesto and c.aumento_pospuesto > hoy:
                    continue
                prox = proximo_ajuste(c.fecha_inicio, c.ajuste_cada_meses, len(c.aumentos))
                if prox and prox <= hoy:
                    n += 1
            return dict(aumentos_pendientes=n)
        except Exception:
            return dict(aumentos_pendientes=0)

    # Versión de la app disponible en todas las plantillas.
    @app.context_processor
    def _version():
        return dict(app_version=app.config.get("APP_VERSION", ""))

    # Filtro para mostrar montos con formato argentino
    @app.template_filter("money")
    def money(value):
        try:
            n = float(value or 0)
        except (TypeError, ValueError):
            return value
        return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # Función disponible en las plantillas para armar links de WhatsApp:
    # wa_link(telefono, mensaje) -> https://wa.me/... o None si no hay teléfono válido.
    from .utils import link_whatsapp
    app.jinja_env.globals["wa_link"] = link_whatsapp

    # Símbolo de moneda: "Pesos" -> "$", "Dólares"/"Dolares" -> "US$".
    @app.template_filter("simbolo")
    def simbolo(moneda):
        m = (moneda or "").strip().lower()
        if m.startswith("d"):   # Dólares / Dolares / USD
            return "US$"
        return "$"

    # PWA: manifest y service worker servidos desde la raíz (para instalar en Android).
    from flask import make_response

    @app.route("/manifest.webmanifest")
    def manifest():
        resp = make_response(app.send_static_file("manifest.webmanifest"))
        resp.headers["Content-Type"] = "application/manifest+json"
        return resp

    @app.route("/sw.js")
    def service_worker():
        resp = make_response(app.send_static_file("sw.js"))
        resp.headers["Content-Type"] = "application/javascript"
        resp.headers["Service-Worker-Allowed"] = "/"
        return resp

    @app.route("/.well-known/assetlinks.json")
    def assetlinks():
        # Vincula la app Android (TWA/APK) con este sitio para pantalla completa.
        resp = make_response(app.send_static_file("assetlinks.json"))
        resp.headers["Content-Type"] = "application/json"
        return resp

    # Arranque de la base. Se puede saltear con SKIP_STARTUP_DB=1 (se usa al
    # generar migraciones con Alembic, para no crear tablas antes de comparar).
    if not os.environ.get("SKIP_STARTUP_DB"):
        with app.app_context():
            _iniciar_base(app)

    return app


def _iniciar_base(app):
    """Prepara la base en el arranque, de forma segura para deploys en curso.

    Transición a Alembic: por ahora db.create_all() sigue asegurando el esquema
    base (para instalaciones nuevas) y los ALTER idempotentes cubren columnas ya
    agregadas antes de adoptar Alembic. Además se "estampa" la base con la
    migración inicial para que, de acá en adelante, los cambios de esquema
    (p. ej. multiempresa) se apliquen con `flask db upgrade`."""
    from sqlalchemy import text, inspect
    try:
        from .models import Usuario
        db.create_all()
        Usuario.crear_admin_inicial()
    except Exception:
        pass
    # Columnas agregadas antes de Alembic (idempotentes, no destructivas).
    for _sql in [
        "ALTER TABLE fiadores ADD COLUMN IF NOT EXISTS solvencia VARCHAR(250)",
        "ALTER TABLE inmuebles ADD COLUMN IF NOT EXISTS cuenta_gas VARCHAR(30)",
        "ALTER TABLE contratos ADD COLUMN IF NOT EXISTS aumento_pospuesto DATE",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE",
    ]:
        try:
            db.session.execute(text(_sql))
            db.session.commit()
        except Exception:
            db.session.rollback()
    # Alembic: la primera vez estampa la base al día con la migración inicial;
    # en los deploys siguientes aplica las migraciones nuevas que haya.
    if not os.environ.get("TESTING") and os.path.isdir(_MIGRATIONS_DIR):
        try:
            from flask_migrate import stamp as _stamp, upgrade as _upgrade
            tablas = inspect(db.engine).get_table_names()
            if "alembic_version" in tablas:
                _upgrade(directory=_MIGRATIONS_DIR)
            else:
                _stamp(directory=_MIGRATIONS_DIR)
        except Exception:
            db.session.rollback()

    # Limpieza única: teléfonos importados como decimales ("3402539090.0").
    # Quitar el ".0" final devuelve el número correcto. Es idempotente.
    try:
        import re as _re
        from .models import Persona
        cambiados = 0
        for _p in Persona.query.filter(Persona.telefono.like("%.0")).all():
            nuevo = _re.sub(r"\.0+$", "", (_p.telefono or "").strip())
            if nuevo != _p.telefono:
                _p.telefono = nuevo
                cambiados += 1
        if cambiados:
            db.session.commit()
    except Exception:
        db.session.rollback()
