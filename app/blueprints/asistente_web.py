"""Asistente de consulta (IA): una página global para preguntar en lenguaje natural
sobre los datos de la inmobiliaria (quién debe, vencimientos, cobros del mes, etc.).

Solo lectura y filtrado por inmobiliaria (ver app/asistente.py)."""
from flask import Blueprint, jsonify, request
from flask_login import login_required

from .. import asistente
from ..ui import render_ui

asistente_bp = Blueprint("asistente", __name__, url_prefix="/asistente")


@asistente_bp.route("/")
@login_required
def index():
    return render_ui("asistente/index.html", configurado=asistente.configurado())


@asistente_bp.route("/preguntar", methods=["POST"])
@login_required
def preguntar():
    pregunta = ((request.get_json(silent=True) or {}).get("pregunta") or "").strip()
    if not pregunta:
        return jsonify(ok=False, error="Escribí una pregunta."), 200
    return jsonify(asistente.preguntar(pregunta)), 200
