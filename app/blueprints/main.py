"""Panel principal (dashboard)."""
from datetime import date, timedelta

from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required
from sqlalchemy.exc import SQLAlchemyError

from .. import db
from ..models import Persona, Inmueble, Contrato, Pago, GasEstado
from ..utils import MESES_ES, calcular_mora, link_whatsapp
from ..calculos import estado_periodo, etiqueta_operativa
from ..ui import render_ui

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
    from sqlalchemy import func
    from sqlalchemy.orm import joinedload
    from ..models import Aumento
    deuda = float(db.session.query(func.coalesce(func.sum(Pago.saldo), 0)).scalar() or 0)
    hoy = date.today()
    from ..calculos import proximo_aumento
    aumentos_pend = 0
    for c in (Contrato.query.filter_by(estado="Vigente")
              .options(joinedload(Contrato.aumentos)).all()):
        if c.metodo_ajuste == "sin_ajuste" or not c.ajuste_cada_meses:
            continue
        prox = proximo_aumento(c)
        if prox and prox <= hoy:
            aumentos_pend += 1

    # Contratos que vencen en los próximos 60 días.
    limite = hoy + timedelta(days=60)
    por_vencer = (Contrato.query
                  .filter(Contrato.estado == "Vigente",
                          Contrato.fecha_fin != None,  # noqa: E711
                          Contrato.fecha_fin >= hoy,
                          Contrato.fecha_fin <= limite)
                  .options(joinedload(Contrato.inquilino),
                           joinedload(Contrato.inmueble))
                  .order_by(Contrato.fecha_fin).all())

    pendientes = {"deuda": deuda, "aumentos": aumentos_pend,
                  "vencen": len(por_vencer)}

    # Cobranzas del mes en curso: quién todavía no pagó (lo que la inmobiliaria
    # mira todos los días). Compacto, para el panel de inicio.
    contratos_vig = (Contrato.query.filter_by(estado="Vigente")
                     .options(joinedload(Contrato.inquilino),
                              joinedload(Contrato.inmueble),
                              joinedload(Contrato.pagos))
                     .all())
    morosos, cobrados, monto_pend, vencen_hoy = [], 0, 0.0, 0
    for c in contratos_vig:
        info = estado_periodo(c, hoy.month, hoy.year, hoy=hoy)
        if info["estado"] == "Pagado":
            cobrados += 1
            continue
        monto_pend += info["saldo"]
        if info["venc"] == hoy:
            vencen_hoy += 1
        msj = None
        if c.inquilino:
            msj = link_whatsapp(c.inquilino.telefono,
                                f"Hola {c.inquilino.nombre}! Te escribo por el alquiler de "
                                f"{c.inmueble.direccion if c.inmueble else ''}. "
                                f"¿Podés confirmarme cuándo abonás {MESES_ES[hoy.month]}? ¡Gracias!")
        # Mora estimada para mostrar en el panel de cobro; el valor definitivo
        # lo calcula el servidor al registrar el pago.
        mora = float(calcular_mora(info["esperado"], c.mora_diaria_pct,
                                   info["venc"], hoy) or 0)
        morosos.append({
            "cid": c.id,
            "inquilino": c.inquilino.nombre if c.inquilino else "—",
            "inmueble": (c.inmueble.direccion if c.inmueble else "—"),
            "saldo": info["saldo"], "vto": info["venc"],
            "vencido": info["vencido"], "dias": info["dias_atraso"],
            "etiqueta": etiqueta_operativa(info), "wa": msj,
            "esperado": info["esperado"], "mora": mora,
            "telefono": (c.inquilino.telefono if c.inquilino else None),
            "registrable": info["pago"] is None,
        })
    # Orden por urgencia: primero lo vencido, más atrasado y más grande arriba.
    morosos.sort(key=lambda m: (m["vencido"], m["dias"], m["saldo"]), reverse=True)

    # Gas con deuda (para la bandeja).
    gas_deuda = (GasEstado.query.filter_by(tiene_deuda=True)
                 .order_by(GasEstado.deuda_total.desc()).limit(6).all())

    cobranzas = {
        "mes_nombre": MESES_ES[hoy.month], "anio": hoy.year,
        "mes": hoy.month, "total": len(contratos_vig), "cobrados": cobrados,
        "pendientes_n": len(morosos), "monto_pend": monto_pend,
        "vencen_hoy": vencen_hoy,
        "morosos": morosos[:8], "hay_mas": max(0, len(morosos) - 8),
    }

    # Liquidaciones cuya factura de honorarios no salió: la bandeja las muestra
    # para reintentar, en vez de que queden en el olvido.
    from .liquidaciones import _pendientes_facturar_query
    try:
        sin_facturar = _pendientes_facturar_query().limit(5).all()
    except SQLAlchemyError:
        sin_facturar = []

    return render_ui("main/index.html", stats=stats, pendientes=pendientes,
                     por_vencer=por_vencer, hoy=hoy, cobranzas=cobranzas,
                     gas_deuda=gas_deuda, sin_facturar=sin_facturar)


@main_bp.route("/acerca")
@login_required
def acerca():
    return render_template("main/acerca.html")


@main_bp.route("/react-test")
@login_required
def react_test():
    """Página de prueba del pipeline React (Sprint 0)."""
    return render_template("main/react_test.html")


@main_bp.route("/inicio/react")
@login_required
def inicio_react():
    """Isla React desactivada: se conserva el código/plantilla. Redirige al panel."""
    return redirect(url_for("main.index"))
