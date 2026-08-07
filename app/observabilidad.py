"""Observabilidad (Fase 12): logging estructurado con id de correlación y captura
de errores con Sentry (opcional).

- Cada request lleva un `request_id` (id de correlación) que se loguea y se devuelve
  en el header `X-Request-Id`, para poder seguir una operación punta a punta.
- Se registra una línea por request con método, ruta, estado, duración, inmobiliaria
  y usuario (menos health checks y estáticos, para no hacer ruido).
- Si está la variable `SENTRY_DSN`, se activa Sentry para avisarte de los errores en
  producción. Sin esa variable, no hace nada (no requiere la librería).
"""
import logging
import os
import time
import uuid

from flask import g, request

_SKIP_LOG = {"static", "health.app_health", "health.database_health",
             "health.facturador_health"}


def init_logging(app):
    """Logging estructurado + id de correlación por request."""
    if not os.environ.get("TESTING"):
        nivel = os.environ.get("LOG_LEVEL", "INFO").upper()
        logging.basicConfig(
            level=nivel,
            format="%(asctime)s %(levelname)s %(name)s %(message)s")
        app.logger.setLevel(nivel)

    @app.before_request
    def _abrir():
        g._t0 = time.monotonic()
        g.request_id = (request.headers.get("X-Request-Id")
                        or uuid.uuid4().hex[:12])

    @app.after_request
    def _cerrar(resp):
        # El id de correlación viaja en la respuesta (para seguir la operación).
        resp.headers.setdefault("X-Request-Id", getattr(g, "request_id", ""))
        if os.environ.get("TESTING") or request.endpoint in _SKIP_LOG:
            return resp
        try:
            dur_ms = int((time.monotonic() - getattr(g, "_t0", time.monotonic())) * 1000)
            from flask_login import current_user
            auten = getattr(current_user, "is_authenticated", False)
            tenant = getattr(current_user, "inmobiliaria_id", None) if auten else None
            user = getattr(current_user, "username", "-") if auten else "-"
            app.logger.info(
                "req id=%s %s %s status=%s dur_ms=%s tenant=%s user=%s",
                getattr(g, "request_id", "-"), request.method, request.path,
                resp.status_code, dur_ms, tenant, user)
        except Exception:
            pass
        return resp


def init_sentry(app):
    """Captura de errores con Sentry, solo si se configuró SENTRY_DSN."""
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
    except Exception:
        app.logger.warning("SENTRY_DSN está configurado pero falta 'sentry-sdk'; "
                           "no se activa el monitoreo de errores.")
        return
    try:
        tasa = float(os.environ.get("SENTRY_TRACES", "0") or 0)
    except (TypeError, ValueError):
        tasa = 0.0
    sentry_sdk.init(
        dsn=dsn,
        integrations=[FlaskIntegration()],
        traces_sample_rate=tasa,
        environment=(os.environ.get("RAILWAY_ENVIRONMENT_NAME")
                     or os.environ.get("ENV", "production")),
        send_default_pii=False,
    )

    @app.before_request
    def _etiquetar():
        # Cada error queda etiquetado con la inmobiliaria y el usuario, para ubicarlo.
        try:
            from flask_login import current_user
            if getattr(current_user, "is_authenticated", False):
                sentry_sdk.set_user({"username": getattr(current_user, "username", None)})
                sentry_sdk.set_tag("inmobiliaria_id",
                                   getattr(current_user, "inmobiliaria_id", None))
        except Exception:
            pass

    app.logger.info("Sentry activado para monitoreo de errores.")
