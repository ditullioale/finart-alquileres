"""Application factory del sistema de gestión de alquileres."""
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Iniciá sesión para continuar."


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

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
                prox = proximo_ajuste(c.fecha_inicio, c.ajuste_cada_meses, len(c.aumentos))
                if prox and prox <= hoy:
                    n += 1
            return dict(aumentos_pendientes=n)
        except Exception:
            return dict(aumentos_pendientes=0)

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

    # Crear tablas y usuario admin al arrancar (útil en el primer deploy en la nube).
    with app.app_context():
        try:
            from .models import Usuario
            db.create_all()
            Usuario.crear_admin_inicial()
        except Exception:
            pass
        # Migraciones no destructivas: agregan columnas nuevas si faltan (autocura
        # la base en cada deploy sin borrar datos).
        from sqlalchemy import text
        for _sql in [
            "ALTER TABLE fiadores ADD COLUMN IF NOT EXISTS solvencia VARCHAR(250)",
        ]:
            try:
                db.session.execute(text(_sql))
                db.session.commit()
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

    return app
