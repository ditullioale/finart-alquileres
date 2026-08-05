"""Pantalla "Facturador": subir resumen bancario, revisar transferencias y facturar.

Reusa el servicio externo Facturador ARCA: esta pantalla es un proxy con login que
habla con su backend por detrás (el navegador nunca toca el facturador directo).
"""
from flask import (Blueprint, Response, jsonify, render_template, request)
from flask_login import login_required

from .. import facturador
from ..models import Ajustes

facturador_bp = Blueprint("facturador", __name__, url_prefix="/facturador")


def _no_configurado():
    return jsonify({"detail": "El facturador no está configurado (falta FACTURADOR_URL)."}), 503


def _autorizada() -> bool:
    return facturador.inmobiliaria_autorizada(Ajustes.get())


def _no_autorizada():
    return jsonify({"detail": "Tu inmobiliaria no tiene habilitado el facturador."}), 403


def _reenviar(resp):
    """Devuelve el JSON y el status code del facturador tal cual."""
    try:
        return jsonify(resp.json()), resp.status_code
    except ValueError:
        return jsonify({"detail": "Respuesta inesperada del facturador."}), 502


@facturador_bp.route("/")
@login_required
def index():
    return render_template("facturador/index.html", habilitado=facturador.habilitado(),
                           autorizada=_autorizada())


@facturador_bp.route("/subir", methods=["POST"])
@login_required
def subir():
    if not _autorizada():
        return _no_autorizada()
    if not facturador.habilitado():
        return _no_configurado()
    archivo = request.files.get("archivo")
    if archivo is None or not archivo.filename:
        return jsonify({"detail": "No se recibió ningún archivo."}), 400
    try:
        resp = facturador.subir_resumen(
            archivo.filename, archivo.read(), archivo.mimetype
        )
    except facturador.requests.RequestException as exc:
        return jsonify({"detail": f"No se pudo contactar al facturador: {exc}"}), 502
    return _reenviar(resp)


@facturador_bp.route("/transferencias")
@login_required
def transferencias():
    if not _autorizada() or not facturador.habilitado():
        return jsonify([]), 200
    try:
        return _reenviar(facturador.listar_transferencias())
    except facturador.requests.RequestException:
        return jsonify([]), 200


@facturador_bp.route("/transferencias/<int:tid>", methods=["POST"])
@login_required
def actualizar(tid):
    if not _autorizada():
        return _no_autorizada()
    if not facturador.habilitado():
        return _no_configurado()
    try:
        return _reenviar(facturador.actualizar_transferencia(tid, request.get_json() or {}))
    except facturador.requests.RequestException as exc:
        return jsonify({"detail": f"No se pudo contactar al facturador: {exc}"}), 502


@facturador_bp.route("/transferencias/<int:tid>/facturar", methods=["POST"])
@login_required
def facturar_una(tid):
    if not _autorizada():
        return _no_autorizada()
    if not facturador.habilitado():
        return _no_configurado()
    confirmar = (request.args.get("confirmar", "false").lower() in ("1", "true", "yes"))
    try:
        return _reenviar(facturador.facturar_transferencia(tid, confirmar))
    except facturador.requests.RequestException as exc:
        return jsonify({"detail": f"No se pudo contactar al facturador: {exc}"}), 502


@facturador_bp.route("/facturar", methods=["POST"])
@login_required
def facturar():
    if not _autorizada():
        return _no_autorizada()
    if not facturador.habilitado():
        return _no_configurado()
    datos = request.get_json() or {}
    ids = datos.get("transferencia_ids") or []
    confirmar = bool(datos.get("confirmar_bajo_minimo"))
    try:
        return _reenviar(facturador.facturar_transferencias(ids, confirmar))
    except facturador.requests.RequestException as exc:
        return jsonify({"detail": f"No se pudo contactar al facturador: {exc}"}), 502


@facturador_bp.route("/facturas")
@login_required
def facturas():
    if not _autorizada() or not facturador.habilitado():
        return jsonify([]), 200
    try:
        return _reenviar(facturador.listar_facturas())
    except facturador.requests.RequestException:
        return jsonify([]), 200


@facturador_bp.route("/factura/<int:fid>/pdf")
@login_required
def factura_pdf(fid):
    if not _autorizada():
        return _no_autorizada()
    if not facturador.habilitado():
        return _no_configurado()
    try:
        resp = facturador.factura_pdf(fid)
    except facturador.requests.RequestException as exc:
        return jsonify({"detail": f"No se pudo contactar al facturador: {exc}"}), 502
    if resp.status_code != 200:
        return _reenviar(resp)
    return Response(
        resp.content,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="factura-{fid}.pdf"'},
    )
