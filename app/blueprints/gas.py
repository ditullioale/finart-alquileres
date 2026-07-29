"""Panel de control de gas (Litoral Gas).

Cruza el N° de cuenta de gas cargado en cada inmueble con el estado de deuda
que el robot deja en la tabla GasEstado, y muestra un tablero con quién debe.
"""
from flask import (Blueprint, render_template, request, jsonify, abort,
                   redirect, url_for, flash)
from flask_login import login_required

from .. import db
from ..models import Inmueble, GasEstado, Contrato, Ajustes, GasCredencial

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
                           ultima_actualizacion=ultima_actualizacion,
                           gas_configurado=GasCredencial.query.count() > 0)


@gas_bp.route("/react")
@login_required
def react():
    return render_template("gas/react.html")


@gas_bp.route("/importar", methods=["POST"])
def importar():
    """Buzón para el robot de Litoral Gas: recibe el estado de deuda de las
    cuentas y lo guarda. Protegido por un token secreto (no usa login)."""
    import os
    from datetime import date
    esperado = os.environ.get("GAS_IMPORT_TOKEN")
    recibido = request.headers.get("X-Gas-Token") or request.args.get("token")
    if not esperado or recibido != esperado:
        return jsonify(ok=False, error="Token inválido o no configurado."), 403

    datos = request.get_json(silent=True) or {}
    # El robot indica a qué inmobiliaria pertenece esta tanda de cuentas. Si no
    # lo manda (robot viejo), cae a la inmobiliaria principal (compatibilidad).
    from ..models import Inmobiliaria
    inmo_id = datos.get("inmobiliaria_id")
    try:
        inmo_id = int(inmo_id) if inmo_id is not None else None
    except (TypeError, ValueError):
        inmo_id = None
    if inmo_id is None:
        inmo = Inmobiliaria.principal()
        inmo_id = inmo.id if inmo else None
    guardadas = 0
    for c in datos.get("cuentas", []):
        cuenta = (c.get("cuenta") or "").strip()
        if not cuenta:
            continue
        venc = None
        if c.get("ultimo_vencimiento"):
            try:
                y, m, d = str(c["ultimo_vencimiento"]).split("-")
                venc = date(int(y), int(m), int(d))
            except Exception:
                venc = None
        g = GasEstado.upsert(cuenta, titular=c.get("titular"), direccion=c.get("direccion"),
                             contrato_vigente=bool(c.get("contrato_vigente", True)),
                             tiene_deuda=bool(c.get("tiene_deuda", False)),
                             deuda_total=c.get("deuda_total") or 0,
                             ultimo_vencimiento=venc, detalle=c.get("detalle"))
        # Asignar el suministro a la inmobiliaria de esta tanda.
        if inmo_id:
            g.inmobiliaria_id = inmo_id
        guardadas += 1
    db.session.commit()
    return jsonify(ok=True, guardadas=guardadas)


@gas_bp.route("/actualizar", methods=["POST"])
@login_required
def actualizar():
    """Actualiza el estado de gas AHORA, desde el servidor, usando las
    credenciales de Litoral Gas cargadas por esta inmobiliaria (sin robot)."""
    from datetime import date
    from flask_login import current_user
    from ..litoralgas import consultar_deuda, CredencialesError, GasError

    credenciales = GasCredencial.query.order_by(GasCredencial.id).all()
    if not credenciales:
        return jsonify(ok=False, error="Primero cargá tu usuario y contraseña "
                       "de Litoral Gas en Ajustes."), 400

    # Consultar todas las cuentas de la inmobiliaria y combinar (sin duplicar).
    por_cuenta, errores = {}, []
    for gc in credenciales:
        try:
            for r in consultar_deuda(gc.usuario, gc.get_clave()):
                por_cuenta[r["cuenta"]] = r
        except CredencialesError:
            errores.append(f"{gc.alias or gc.usuario}: usuario o contraseña incorrectos")
        except GasError as e:
            errores.append(f"{gc.alias or gc.usuario}: {e}")

    if not por_cuenta and errores:
        return jsonify(ok=False, error="; ".join(errores)), 400

    tid = getattr(current_user, "inmobiliaria_id", None)
    guardadas = con_deuda = 0
    for r in por_cuenta.values():
        venc = r["ultimo_vencimiento"]
        if venc and not isinstance(venc, date):
            venc = None
        g = GasEstado.upsert(r["cuenta"], titular=r["titular"], direccion=r["direccion"],
                             contrato_vigente=r["contrato_vigente"],
                             tiene_deuda=r["tiene_deuda"], deuda_total=r["deuda_total"],
                             ultimo_vencimiento=venc, detalle=r["detalle"])
        if tid:
            g.inmobiliaria_id = tid
        guardadas += 1
        con_deuda += 1 if r["tiene_deuda"] else 0
    db.session.commit()
    return jsonify(ok=True, guardadas=guardadas, con_deuda=con_deuda, errores=errores)


@gas_bp.route("/robot/credenciales", methods=["GET"])
def robot_credenciales():
    """Le da al robot la lista de inmobiliarias con credenciales de Litoral Gas
    (usuario + clave descifrada) para que consulte la deuda de cada una.
    Protegido por el mismo token del robot. Sin usuario => ve todos los Ajustes."""
    import os
    esperado = os.environ.get("GAS_IMPORT_TOKEN")
    recibido = request.headers.get("X-Gas-Token") or request.args.get("token")
    if not esperado or recibido != esperado:
        return jsonify(ok=False, error="Token inválido o no configurado."), 403
    cuentas = []
    for gc in GasCredencial.query.all():
        clave = gc.get_clave()
        if gc.usuario and clave:
            cuentas.append({"inmobiliaria_id": gc.inmobiliaria_id,
                            "usuario": gc.usuario, "clave": clave})
    return jsonify(ok=True, inmobiliarias=cuentas)


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


@gas_bp.route("/estado")
@login_required
def estado():
    """Devuelve el estado de gas de una cuenta (para la ventanita 'Ver gas')."""
    import json
    cuenta = (request.args.get("cuenta") or "").strip()
    g = GasEstado.query.filter_by(cuenta=cuenta).first()
    if not g:
        return jsonify(ok=False, cuenta=cuenta)
    facturas = []
    try:
        parsed = json.loads(g.detalle) if g.detalle else []
        if isinstance(parsed, list):
            facturas = parsed
    except Exception:
        facturas = []
    return jsonify(ok=True, cuenta=g.cuenta, titular=g.titular,
                   tiene_deuda=bool(g.tiene_deuda),
                   deuda_total=float(g.deuda_total or 0),
                   facturas=facturas,
                   ultimo_vencimiento=(g.ultimo_vencimiento.isoformat()
                                       if g.ultimo_vencimiento else None),
                   actualizado=(g.actualizado.strftime("%d/%m/%Y %H:%M")
                                if g.actualizado else None))


@gas_bp.route("/<int:gid>/eliminar", methods=["POST"])
@login_required
def eliminar(gid):
    """Elimina un suministro del panel de gas."""
    g = db.session.get(GasEstado, gid) or abort(404)
    from flask import flash, redirect
    db.session.delete(g)
    db.session.commit()
    flash("Suministro eliminado del panel.", "ok")
    return redirect(url_for("gas.index"))
