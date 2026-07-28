"""Panel principal (dashboard)."""
from datetime import date, timedelta

from flask import Blueprint, render_template
from flask_login import login_required

from ..models import Persona, Inmueble, Contrato, Pago
from ..utils import proximo_ajuste

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def index():
    stats = {
        "personas": Persona.query.count(),
        "propietarios": Persona.query.filter_by(es_propietario=True).count(),
        "inquilinos": Persona.query.filter_by(es_inquilino=True).count(),
        "inmuebles": Inmueble.query.count(),
        "alquilados": Inmueble.query.filter_by(estado="Alquilado").count(),
        "contratos_vigentes": Contrato.query.filter_by(estado="Vigente").count(),
    }

    # Pendientes: deuda total y aumentos por aplicar.
    deuda = sum(float(p.saldo or 0) for p in Pago.query.all())
    hoy = date.today()
    aumentos_pend = 0
    for c in Contrato.query.filter_by(estado="Vigente").all():
        if c.metodo_ajuste == "sin_ajuste" or not c.ajuste_cada_meses:
            continue
        prox = proximo_ajuste(c.fecha_inicio, c.ajuste_cada_meses, len(c.aumentos))
        if prox and prox <= hoy:
            aumentos_pend += 1

    # Contratos que vencen en los próximos 60 días.
    limite = hoy + timedelta(days=60)
    por_vencer = (Contrato.query
                  .filter(Contrato.estado == "Vigente",
                          Contrato.fecha_fin != None,  # noqa: E711
                          Contrato.fecha_fin >= hoy,
                          Contrato.fecha_fin <= limite)
                  .order_by(Contrato.fecha_fin).all())

    pendientes = {"deuda": deuda, "aumentos": aumentos_pend,
                  "vencen": len(por_vencer)}
    return render_template("main/index.html", stats=stats, pendientes=pendientes,
                           por_vencer=por_vencer, hoy=hoy)


@main_bp.route("/acerca")
@login_required
def acerca():
    return render_template("main/acerca.html")
