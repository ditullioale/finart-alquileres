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

    # Cabeceras de seguridad (CSP, HSTS, anti-clickjacking, etc.) en cada respuesta.
    from .seguridad import aplicar_headers_seguridad
    aplicar_headers_seguridad(app)

    # Observabilidad: logging estructurado con id de correlación + Sentry (opcional).
    from .observabilidad import init_logging, init_sentry
    init_logging(app)
    init_sentry(app)

    # Multiempresa: asignar inmobiliaria al crear + filtro de aislamiento.
    from .tenant import registrar_eventos
    registrar_eventos()
    # Auditoría automática de altas/cambios/eliminaciones.
    from .auditoria import registrar_auditoria
    registrar_auditoria()

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
    from .blueprints.facturador_web import facturador_bp
    from .blueprints.plataforma import plataforma_bp
    from .blueprints.health import health_bp
    from .blueprints.asistente_web import asistente_bp

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
    app.register_blueprint(facturador_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(asistente_bp)

    @app.context_processor
    def _inject_facturador():
        from flask_login import current_user
        try:
            if not current_user.is_authenticated:
                return {"facturador_disponible": False}
            from . import facturador
            from .models import Ajustes
            disponible = facturador.habilitado() and facturador.inmobiliaria_autorizada(Ajustes.get())
            return {"facturador_disponible": disponible}
        except Exception:
            return {"facturador_disponible": False}

    @app.context_processor
    def _inject_asistente():
        from flask_login import current_user
        try:
            if not current_user.is_authenticated:
                return {"asistente_disponible": False}
            from . import asistente
            return {"asistente_disponible": asistente.configurado()}
        except Exception:
            return {"asistente_disponible": False}
    app.register_blueprint(plataforma_bp)

    # El buzón del robot de gas usa su propio token (X-Gas-Token), no CSRF.
    csrf.exempt(app.view_functions["gas.importar"])
    # El cron de reconciliación se autentica por token (X-Reconciliar-Token), no CSRF.
    csrf.exempt(app.view_functions["liquidaciones.reconciliar_cron"])

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

    # Roles de solo lectura (lectura / contador): pueden ver y exportar, pero no
    # hacer cambios. Se bloquean las operaciones que modifican datos (POST/etc.).
    @app.before_request
    def _guardia_solo_lectura():
        from flask_login import current_user
        if not getattr(current_user, "is_authenticated", False):
            return
        if getattr(current_user, "rol", None) not in ("lectura", "contador"):
            return
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return
        permitidos = {"auth.logout", "usuarios.cambiar_clave"}
        if request.endpoint in permitidos:
            return
        if request.path.startswith("/api") or request.is_json:
            from flask import jsonify
            return jsonify(ok=False, error="Tu usuario es de solo lectura."), 403
        flash("Tu usuario es de solo lectura: no podés hacer cambios.", "error")
        return redirect(request.referrer or url_for("main.index"))

    # Aislamiento del superadmin de PLATAFORMA. El dueño de la plataforma solo
    # administra cuentas (crear/aprobar/suspender inmobiliarias): NO puede entrar
    # a los datos operativos de ninguna inmobiliaria (cobros, contratos, personas,
    # documentación, API...). Así, aunque el operador también tenga su propia
    # inmobiliaria, con la cuenta de plataforma no puede leer datos ajenos.
    @app.before_request
    def _guardia_superadmin():
        from flask_login import current_user
        if not getattr(current_user, "is_authenticated", False):
            return
        if getattr(current_user, "rol", None) != "superadmin":
            return
        ep = request.endpoint or ""
        if ep.startswith("plataforma."):
            return
        permitidos = {"auth.logout", "auth.login", "auth.recuperar",
                      "auth.restablecer", "usuarios.cambiar_clave", "static",
                      "manifest", "service_worker", "assetlinks"}
        if ep in permitidos:
            return
        if request.path.startswith("/api") or request.is_json:
            from flask import jsonify
            return jsonify(ok=False, error="El administrador de plataforma no "
                           "accede a datos de las inmobiliarias."), 403
        flash("Como administrador de la plataforma no accedés a los datos de las "
              "inmobiliarias. Para trabajar tu propia inmobiliaria, ingresá con tu "
              "usuario administrador.", "error")
        return redirect(url_for("plataforma.index"))

    # Páginas de error amigables (en vez de la pantalla técnica por defecto).
    from flask import render_template as _rt

    @app.errorhandler(403)
    def _e403(e):
        return _rt("error.html", codigo=403, emoji="🔒",
                   titulo="No tenés permiso para ver esto",
                   mensaje="Tu usuario no puede acceder a esta sección. Si creés que "
                           "es un error, pedile acceso a un administrador."), 403

    @app.errorhandler(404)
    def _e404(e):
        return _rt("error.html", codigo=404, emoji="🔎",
                   titulo="No encontramos lo que buscabas",
                   mensaje="Puede que se haya eliminado o que el enlace esté mal. "
                           "Volvé al inicio e intentá de nuevo."), 404

    @app.errorhandler(500)
    def _e500(e):
        db.session.rollback()
        return _rt("error.html", codigo=500, emoji="⚠️",
                   titulo="Tuvimos un problema",
                   mensaje="No pudimos completar tu pedido. Probá de nuevo en un "
                           "momento; si sigue pasando, avisanos."), 500

    # Aviso global: cantidad de aumentos vencidos (badge en el menú).
    @app.context_processor
    def _aumentos_pendientes():
        from flask_login import current_user
        if not getattr(current_user, "is_authenticated", False):
            return dict(aumentos_pendientes=0)
        try:
            from datetime import date
            from sqlalchemy.orm import joinedload
            from .models import Contrato
            from .calculos import proximo_aumento
            hoy = date.today()
            contratos = (Contrato.query.filter_by(estado="Vigente")
                         .options(joinedload(Contrato.aumentos)).all())
            n = 0
            for c in contratos:
                if c.metodo_ajuste == "sin_ajuste" or not c.ajuste_cada_meses:
                    continue
                if c.aumento_pospuesto and c.aumento_pospuesto > hoy:
                    continue
                prox = proximo_aumento(c)
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


# Revisión base de Alembic (esquema anterior a multiempresa). Se usa para
# "estampar" bases que ya existían antes de adoptar Alembic.
BASELINE_REVISION = "ba72a5e5c3ea"


def _iniciar_base(app):
    """Prepara la base en el arranque. El esquema lo maneja **Alembic**:

    - Base vacía (instalación nueva): `upgrade()` crea todo desde las migraciones.
    - Base pre-Alembic (con datos): se asegura que tenga las columnas base, se
      estampa en la revisión inicial y luego `upgrade()` aplica las migraciones
      nuevas (p. ej. multiempresa).
    - Base al día: `upgrade()` aplica lo que falte (no-op si no hay nada).

    Después siembra el admin y la inmobiliaria inicial y asigna los datos
    existentes a esa inmobiliaria (backfill de multiempresa).

    Si el esquema no se puede preparar, la app **no arranca**: seguir con un
    esquema viejo o a medias rompe todo más adelante y de forma confusa. Con
    IGNORAR_ERROR_ESQUEMA=1 el arranque continúa igual (solo para diagnosticar:
    lo que dependa del esquema que faltó va a seguir fallando)."""
    from sqlalchemy import text, inspect
    migrar_on_boot = os.environ.get("MIGRATE_ON_BOOT", "1").lower() not in ("0", "false", "no")
    if os.environ.get("TESTING") or not os.path.isdir(_MIGRATIONS_DIR):
        # En pruebas se usa create_all() directo (más simple y sin Alembic).
        _preparar_esquema(app, db.create_all)
    elif not migrar_on_boot:
        # Las migraciones se corren aparte (release command: flask db upgrade).
        app.logger.info("MIGRATE_ON_BOOT=0: no se migra en el arranque.")
    else:
        def _migrar():
            from flask_migrate import stamp as _stamp, upgrade as _upgrade
            tablas = inspect(db.engine).get_table_names()
            if not tablas:
                _upgrade(directory=_MIGRATIONS_DIR)                 # base nueva
            elif "alembic_version" not in tablas:
                # Base pre-Alembic: garantizar columnas base antes de estampar.
                for _sql in [
                    "ALTER TABLE fiadores ADD COLUMN IF NOT EXISTS solvencia VARCHAR(250)",
                    "ALTER TABLE inmuebles ADD COLUMN IF NOT EXISTS cuenta_gas VARCHAR(30)",
                    "ALTER TABLE contratos ADD COLUMN IF NOT EXISTS aumento_pospuesto DATE",
                    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE",
                ]:
                    try:
                        db.session.execute(text(_sql)); db.session.commit()
                    except Exception:
                        db.session.rollback()
                        app.logger.warning("No pude aplicar %s", _sql, exc_info=True)
                _stamp(directory=_MIGRATIONS_DIR, revision=BASELINE_REVISION)
                _upgrade(directory=_MIGRATIONS_DIR)                 # aplica multiempresa, etc.
            else:
                _upgrade(directory=_MIGRATIONS_DIR)                 # al día / pendientes

        _preparar_esquema(app, lambda: _con_lock_migracion(app, _migrar))

    # Siembra: inmobiliaria #1 primero (para que el admin pueda asignarse a ella
    # cuando inmobiliaria_id es obligatorio), luego admin + backfill.
    try:
        from .models import Usuario, Inmobiliaria
        inmo = Inmobiliaria.crear_inicial()
        Usuario.crear_admin_inicial()
        _backfill_inmobiliaria(inmo)
        _asegurar_superadmin()
        _migrar_gas_credenciales()
    except Exception:
        db.session.rollback()
        app.logger.exception("Falló la siembra inicial de la base")

    # Limpieza única: teléfonos importados como decimales ("3402539090.0").
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
        app.logger.exception("Falló la limpieza de teléfonos importados")


def _con_lock_migracion(app, fn):
    """Corre las migraciones tomando un lock de aplicación en PostgreSQL, para
    que con varios workers de gunicorn no intenten migrar a la vez (carrera).
    En SQLite u otros motores, corre directo. El lock es un simple mutex: el
    segundo worker espera y, cuando entra, upgrade() ya no tiene nada que hacer."""
    try:
        if db.engine.dialect.name != "postgresql":
            return fn()
    except Exception:
        return fn()
    from sqlalchemy import text
    LOCK = 918273645
    conn = db.engine.connect()
    try:
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": LOCK})
        try:
            conn.commit()
        except Exception:
            pass
        return fn()
    finally:
        try:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK})
            conn.close()
        except Exception:
            pass


def _preparar_esquema(app, preparar):
    """Corre la preparación del esquema y corta el arranque si falla.

    Se atrapa también SystemExit porque flask_migrate no propaga los errores de
    Alembic: los loguea y termina el proceso con sys.exit(1)."""
    try:
        preparar()
    except (Exception, SystemExit):
        db.session.rollback()
        app.logger.critical("No pude preparar el esquema de la base", exc_info=True)
        if not os.environ.get("IGNORAR_ERROR_ESQUEMA"):
            raise


def _asegurar_superadmin():
    """Crea el superadmin de plataforma si se definen SUPERADMIN_USER/PASS en el
    entorno. No tiene inmobiliaria (ve todas) y sirve para el onboarding."""
    su_user = (os.environ.get("SUPERADMIN_USER") or "").strip().lower()
    su_pass = os.environ.get("SUPERADMIN_PASS")
    if not su_user or not su_pass:
        return
    from .models import Usuario
    if Usuario.query.filter_by(username=su_user).first():
        return
    su = Usuario(username=su_user, nombre="Superadmin", rol="superadmin",
                 activo=True, inmobiliaria_id=None, must_change_password=False)
    su.set_password(su_pass)
    db.session.add(su)
    db.session.commit()


def _migrar_gas_credenciales():
    """Mueve la credencial única de Litoral Gas que estaba en Ajustes a la tabla
    gas_credenciales (que soporta varias por inmobiliaria). Idempotente."""
    try:
        from .models import Ajustes, GasCredencial
        for a in Ajustes.query.all():
            if a.gas_usuario and a.gas_clave_enc and a.inmobiliaria_id:
                ya = GasCredencial.query.filter_by(
                    inmobiliaria_id=a.inmobiliaria_id, usuario=a.gas_usuario).first()
                if not ya:
                    gc = GasCredencial(inmobiliaria_id=a.inmobiliaria_id,
                                       alias="Cuenta 1", usuario=a.gas_usuario,
                                       clave_enc=a.gas_clave_enc)
                    db.session.add(gc)
        db.session.commit()
    except Exception:
        db.session.rollback()


def _backfill_inmobiliaria(inmo):
    """Asigna a la inmobiliaria dada todos los registros que todavía no tengan
    inmobiliaria_id. Idempotente: en cada arranque 'cura' lo que falte."""
    if not inmo:
        return
    from sqlalchemy import text
    tid = inmo.id
    tablas = ["usuarios", "personas", "inmuebles", "contratos", "aumentos",
              "pagos", "gas_estado", "recibos_manuales", "liquidaciones",
              "ajustes"]
    for t in tablas:
        try:
            db.session.execute(
                text(f"UPDATE {t} SET inmobiliaria_id = :tid "
                     f"WHERE inmobiliaria_id IS NULL"), {"tid": tid})
            db.session.commit()
        except Exception:
            db.session.rollback()
