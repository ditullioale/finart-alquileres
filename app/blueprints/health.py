"""Health checks para monitoreo (Fase 12 del roadmap).

Endpoints públicos y livianos, pensados para que Railway / un monitor externo
verifiquen que la app está viva y que la base responde. No exponen datos sensibles
y no requieren login.

- GET /app-health       → la app está en pie (no toca la base).
- GET /database-health  → la base responde (SELECT 1). 200 ok / 503 si falla.
- GET /facturador-health→ estado de la integración con el Facturador (configurado o no).
"""
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from .. import db

health_bp = Blueprint("health", __name__)


def _ahora():
    return datetime.now(timezone.utc).isoformat()


@health_bp.route("/app-health")
def app_health():
    return jsonify(status="ok", service="finart",
                   version=current_app.config.get("APP_VERSION", ""),
                   time=_ahora()), 200


@health_bp.route("/database-health")
def database_health():
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify(status="ok", database="ok", time=_ahora()), 200
    except Exception:
        # No filtramos el detalle del error hacia afuera; queda en los logs.
        current_app.logger.exception("database-health: la base no respondió")
        return jsonify(status="error", database="unreachable", time=_ahora()), 503


@health_bp.route("/facturador-health")
def facturador_health():
    """Estado de la integración, sin llamar al servicio externo (para no encadenar
    caídas ni demorar el chequeo). Informa si está configurada."""
    try:
        from .. import facturador
        configurado = facturador.habilitado()
    except Exception:
        configurado = False
    return jsonify(status="ok", facturador="configurado" if configurado else "no_configurado",
                   time=_ahora()), 200
