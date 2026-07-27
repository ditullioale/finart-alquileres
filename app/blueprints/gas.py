"""Panel de control de gas (Litoral Gas).

Cruza el N° de cuenta de gas cargado en cada inmueble con el estado de deuda
que el robot deja en la tabla GasEstado, y muestra un tablero con quién debe.
"""
from flask import Blueprint, render_template, request, jsonify, abort
from flask_login import login_required

from .. import db
from ..models import Inmueble, GasEstado, Contrato

gas_bp = Blueprint("gas", __name__, url_prefix="/gas")


@gas_bp.route("/")
@login_required
def index():
    inmuebles = Inmueble.query.filter(Inmueble.cuenta_gas.isnot(None),
                                      Inmueble.cuenta_gas != "").all()
    estados = {g.cuenta: g for g in GasEstado.query.all()}

    filas = []
    con_deuda = 0
    deuda_total = 0.0
    ultima_actualizacion = None
    for inm in inmuebles:
        g = estados.get((inm.cuenta_gas or "").strip())
        inquilino = None
        cont = Contrato.query.filter_by(inmueble_id=inm.id, estado="Vigente").first()
        if cont and cont.inquilino:
            inquilino = cont.inquilino.nombre
        if g:
            if g.tiene_deuda:
                con_deuda += 1
                deuda_total += float(g.deuda_total or 0)
            if g.actualizado and (ultima_actualizacion is None or g.actualizado > ultima_actualizacion):
                ultima_actualizacion = g.actualizado
        filas.append(dict(inm=inm, g=g, inquilino=inquilino))

    # Ordenar: primero los que deben, después el resto.
    filas.sort(key=lambda f: (0 if (f["g"] and f["g"].tiene_deuda) else 1,
                              f["inm"].direccion or ""))

    # Cuentas que trajo el robot pero no están asignadas a ningún inmueble.
    asignadas = {(i.cuenta_gas or "").strip() for i in inmuebles}
    sin_asignar = [g for g in estados.values() if g.cuenta not in asignadas]

    # Inmuebles sin cuenta de gas, para el selector de asignación rápida.
    disponibles = (Inmueble.query
                   .filter(db.or_(Inmueble.cuenta_gas.is_(None), Inmueble.cuenta_gas == ""))
                   .order_by(Inmueble.direccion).all())

    return render_template("gas/index.html", filas=filas, con_deuda=con_deuda,
                           deuda_total=deuda_total, total=len(inmuebles),
                           sin_asignar=sin_asignar, disponibles=disponibles,
                           ultima_actualizacion=ultima_actualizacion)


@gas_bp.route("/asignar", methods=["POST"])
@login_required
def asignar():
    """Vincula una cuenta de gas a un inmueble (asignación rápida desde el panel)."""
    d = request.get_json(silent=True) or {}
    cuenta = (d.get("cuenta") or "").strip()
    inm = db.session.get(Inmueble, int(d.get("inmueble_id") or 0))
    if not cuenta or not inm:
        return jsonify(ok=False, error="Faltan datos."), 400
    inm.cuenta_gas = cuenta
    db.session.commit()
    return jsonify(ok=True, inmueble=inm.direccion)
