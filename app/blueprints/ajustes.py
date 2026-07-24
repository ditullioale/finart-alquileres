"""Ajustes de la inmobiliaria y cambio de contraseña."""
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user

from .. import db
from ..models import Ajustes
from ..utils import parse_num

ajustes_bp = Blueprint("ajustes", __name__, url_prefix="/ajustes")


@ajustes_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    a = Ajustes.get()
    if request.method == "POST":
        a.nombre = request.form.get("nombre", "").strip()
        a.cuit = request.form.get("cuit", "").strip()
        a.ing_brutos = request.form.get("ing_brutos", "").strip()
        a.inicio_actividades = request.form.get("inicio_actividades", "").strip()
        a.cond_iva = request.form.get("cond_iva", "").strip()
        a.direccion = request.form.get("direccion", "").strip()
        a.localidad = request.form.get("localidad", "").strip()
        a.telefono = request.form.get("telefono", "").strip()
        a.horario = request.form.get("horario", "").strip()
        a.logo_url = request.form.get("logo_url", "").strip()
        a.recibo_prefijo = request.form.get("recibo_prefijo", "0001").strip() or "0001"
        a.recibo_proximo = parse_num(request.form.get("recibo_proximo"), entero=True) or 1
        a.pagare_meses = parse_num(request.form.get("pagare_meses"), entero=True) or 10
        a.pagare_lugar = request.form.get("pagare_lugar", "").strip()
        db.session.commit()
        flash("Ajustes guardados.", "ok")
        return redirect(url_for("ajustes.index"))
    return render_template("ajustes/index.html", a=a)


@ajustes_bp.route("/clave", methods=["POST"])
@login_required
def cambiar_clave():
    actual = request.form.get("actual", "")
    nueva = request.form.get("nueva", "")
    repetir = request.form.get("repetir", "")
    if not current_user.check_password(actual):
        flash("La contraseña actual no es correcta.", "error")
    elif len(nueva) < 4:
        flash("La nueva contraseña es muy corta.", "error")
    elif nueva != repetir:
        flash("Las contraseñas nuevas no coinciden.", "error")
    else:
        current_user.set_password(nueva)
        db.session.commit()
        flash("Contraseña actualizada.", "ok")
    return redirect(url_for("ajustes.index"))
