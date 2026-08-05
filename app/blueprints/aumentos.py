"""Aumentos: aplicación por porcentaje o índice, historial y gestión de índices."""
from datetime import date
from decimal import Decimal

from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, abort, jsonify)
from flask_login import login_required, current_user

from .. import db
from ..models import Contrato, Aumento, IndiceValor
from ..utils import (parse_num, parse_fecha, parse_periodo, periodo_date,
                     proximo_ajuste, add_months, INDICE_NOMBRE, MESES_ES, q2)
from ..indices_oficiales import traer_icl_bcra

aumentos_bp = Blueprint("aumentos", __name__, url_prefix="/aumentos")

TIPOS_INDICE = ["ICL", "IPC", "CasaPropia"]
ARQUILER_URL = "https://arquiler.com/"   # calculadora externa para IPC / Casa Propia


def _asegurar_icl(periodos):
    """Trae del BCRA los valores de ICL que falten para esos períodos (best-effort).
    Devuelve True si, tras intentarlo, están todos disponibles."""
    faltan = [p for p in periodos if p and _valor_indice("ICL", p) is None]
    if not faltan:
        return True
    valores, error = traer_icl_bcra()
    if not error and valores:
        for v in valores:
            _guardar_valor("ICL", v["periodo"], v["valor"], "BCRA")
        db.session.commit()
    return all(p and _valor_indice("ICL", p) is not None for p in periodos)


# --------------------------------------------------------------------------- #
#  Panel de aumentos
# --------------------------------------------------------------------------- #
@aumentos_bp.route("/")
@login_required
def index():
    hoy = date.today()
    contratos = Contrato.query.filter_by(estado="Vigente").all()
    pendientes, proximos = [], []
    for c in contratos:
        if c.metodo_ajuste == "sin_ajuste" or not c.ajuste_cada_meses:
            continue
        n = len(c.aumentos)
        prox = proximo_ajuste(c.fecha_inicio, c.ajuste_cada_meses, n)
        if not prox:
            continue
        # Si el aumento fue pospuesto y la fecha aún no llegó, no molestar.
        pospuesto = c.aumento_pospuesto and c.aumento_pospuesto > hoy
        item = {"c": c, "fecha": prox, "n": n, "pospuesto": c.aumento_pospuesto}
        if prox <= hoy:
            if not pospuesto:
                pendientes.append(item)
        elif (prox - hoy).days <= 45:
            proximos.append(item)
    pendientes.sort(key=lambda x: x["fecha"])
    proximos.sort(key=lambda x: x["fecha"])
    ultimos = Aumento.query.order_by(Aumento.creado.desc()).limit(30).all()
    return render_template("aumentos/index.html", pendientes=pendientes,
                           proximos=proximos, ultimos=ultimos,
                           indice_nombre=INDICE_NOMBRE, meses=MESES_ES)


# --------------------------------------------------------------------------- #
#  Aplicar aumento a un contrato
# --------------------------------------------------------------------------- #
def _sugerencia(contrato):
    """Períodos base/destino y factor sugeridos para el próximo ajuste por índice."""
    n = len(contrato.aumentos)
    interval = contrato.ajuste_cada_meses or 0
    fi = contrato.fecha_inicio
    base = add_months(fi, n * interval) if fi and interval else fi
    dest = add_months(fi, (n + 1) * interval) if fi and interval else None
    return periodo_date(base.year, base.month) if base else None, \
        periodo_date(dest.year, dest.month) if dest else None


def _valor_indice(tipo, periodo):
    if not (tipo and periodo):
        return None
    iv = IndiceValor.query.filter_by(tipo=tipo, periodo=periodo).first()
    return float(iv.valor) if iv else None


@aumentos_bp.route("/contrato/<int:cid>/aplicar", methods=["GET", "POST"])
@login_required
def aplicar(cid):
    c = db.session.get(Contrato, cid) or abort(404)
    precio_actual = float(c.precio_actual or c.precio_inicial or 0)

    if request.method == "POST":
        metodo = request.form.get("metodo", "manual")
        fecha_vig = parse_fecha(request.form.get("fecha_vigencia")) or date.today()
        aum = Aumento(contrato_id=c.id, fecha_vigencia=fecha_vig,
                      precio_anterior=precio_actual, metodo=metodo)

        if metodo == "manual":
            # El usuario escribe directamente el nuevo precio (sin % ni índice).
            nuevo = parse_num(request.form.get("precio_nuevo"))
            if not nuevo or nuevo <= 0:
                flash("Ingresá el nuevo precio (mayor a 0).", "error")
                return redirect(url_for("aumentos.aplicar", cid=c.id))
            nuevo = float(q2(nuevo))
        elif metodo == "porcentaje":
            pct = parse_num(request.form.get("porcentaje"))
            if not pct:
                flash("Indicá el porcentaje del aumento.", "error")
                return redirect(url_for("aumentos.aplicar", cid=c.id))
            nuevo = float(q2(q2(precio_actual) * (Decimal(1) + q2(pct) / Decimal(100))))
            aum.porcentaje = pct
        else:  # indice
            tipo = request.form.get("indice_tipo") or c.indice_tipo or "ICL"
            per_base = parse_periodo(request.form.get("periodo_base"))
            per_dest = parse_periodo(request.form.get("periodo_destino"))
            if tipo == "ICL":
                _asegurar_icl([per_base, per_dest])   # trae del BCRA lo que falte
            v_base = _valor_indice(tipo, per_base)
            v_dest = _valor_indice(tipo, per_dest)
            if v_base is None or v_dest is None:
                flash("No encontré los valores del índice para esos meses. Para IPC o "
                      "Casa Propia, usá “Calcular en ARquiler” y cargá el resultado con "
                      "“Precio nuevo directo”.", "error")
                return redirect(url_for("aumentos.aplicar", cid=c.id))
            factor = v_dest / v_base
            nuevo = float(q2(precio_actual * factor))
            aum.indice_tipo = tipo
            aum.indice_inicio = v_base
            aum.indice_fin = v_dest

        aum.precio_nuevo = nuevo
        aum.observaciones = request.form.get("observaciones", "").strip()
        c.precio_actual = nuevo
        c.aumento_pospuesto = None   # al aplicar, se limpia cualquier posposición
        db.session.add(aum)
        db.session.commit()
        flash(f"Aumento aplicado: {c.moneda} {precio_actual:,.2f} → {nuevo:,.2f}.", "ok")
        return redirect(url_for("contratos.ver", cid=c.id))

    per_base, per_dest = _sugerencia(c)
    tipo = c.indice_tipo or "ICL"
    # Método inicial sugerido según el contrato (el usuario puede cambiarlo).
    metodo_ini = {"indice": "indice", "porcentaje": "porcentaje"}.get(c.metodo_ajuste, "manual")
    contexto = dict(
        c=c, precio_actual=precio_actual,
        per_base=per_base, per_dest=per_dest,
        v_base=_valor_indice(tipo, per_base), v_dest=_valor_indice(tipo, per_dest),
        tipos=TIPOS_INDICE, indice_nombre=INDICE_NOMBRE,
        pct_sugerido=float(c.porcentaje_ajuste) if c.porcentaje_ajuste else "",
        hoy=date.today(), metodo_ini=metodo_ini, arquiler_url=ARQUILER_URL,
    )
    return render_template("aumentos/aplicar.html", **contexto)


@aumentos_bp.route("/contrato/<int:cid>/calcular-indice")
@login_required
def calcular_indice(cid):
    """Previsualiza el precio nuevo por índice. Para ICL trae del BCRA lo que falte."""
    c = db.session.get(Contrato, cid) or abort(404)
    tipo = request.args.get("tipo", "ICL")
    per_base = parse_periodo(request.args.get("base"))
    per_dest = parse_periodo(request.args.get("dest"))
    if not per_base or not per_dest:
        return jsonify(ok=False, error="Elegí el mes base y el mes destino.")
    fuente = "cargado"
    if tipo == "ICL" and _asegurar_icl([per_base, per_dest]):
        fuente = "BCRA"
    v_base = _valor_indice(tipo, per_base)
    v_dest = _valor_indice(tipo, per_dest)
    if v_base is None or v_dest is None:
        return jsonify(ok=False, error=f"No encontré valores de {tipo} para esos meses. "
                       "Calculalo en ARquiler y usá “Precio nuevo directo”.")
    factor = v_dest / v_base
    precio_actual = float(c.precio_actual or c.precio_inicial or 0)
    return jsonify(ok=True, v_base=v_base, v_dest=v_dest, factor=round(factor, 4),
                   nuevo=float(q2(precio_actual * factor)), fuente=fuente)


@aumentos_bp.route("/config-masiva", methods=["POST"])
@login_required
def config_masiva():
    """Configura de una sola vez el método de ajuste de TODOS los contratos
    vigentes de la inmobiliaria actual (útil tras importar de Inmosoft, que no
    trae el método). Solo admin. Es tenant-scoped: no toca a otras inmobiliarias."""
    if getattr(current_user, "rol", None) != "admin":
        abort(403)
    cada = parse_num(request.form.get("cada_meses"), entero=True) or 4
    tipo = request.form.get("indice_tipo") or "ICL"
    if tipo not in TIPOS_INDICE:
        tipo = "ICL"
    solo_sin = bool(request.form.get("solo_sin_ajuste"))
    n = 0
    for c in Contrato.query.filter_by(estado="Vigente").all():
        if solo_sin and c.metodo_ajuste not in (None, "", "sin_ajuste"):
            continue
        c.metodo_ajuste = "indice"
        c.indice_tipo = tipo
        c.ajuste_cada_meses = cada
        n += 1
    db.session.commit()
    flash(f"Listo: {n} contrato(s) vigente(s) quedaron con ajuste por índice "
          f"{INDICE_NOMBRE.get(tipo, tipo)} cada {cada} meses.", "ok")
    return redirect(url_for("aumentos.index"))


@aumentos_bp.route("/contrato/<int:cid>/posponer", methods=["POST"])
@login_required
def posponer(cid):
    """Pospone el recordatorio de aumento hasta una fecha (cargarlo más tarde)."""
    c = db.session.get(Contrato, cid) or abort(404)
    hasta = parse_fecha(request.form.get("hasta"))
    if not hasta:
        hasta = add_months(date.today(), 1)
    c.aumento_pospuesto = hasta
    db.session.commit()
    flash(f"Aumento pospuesto hasta el {hasta.strftime('%d/%m/%Y')}. No va a aparecer como pendiente hasta esa fecha.", "ok")
    return redirect(url_for("aumentos.index"))


@aumentos_bp.route("/<int:aid>/editar", methods=["GET", "POST"])
@login_required
def editar(aid):
    """Edita un aumento ya aplicado. Si es el último, actualiza el precio actual."""
    aum = db.session.get(Aumento, aid) or abort(404)
    c = aum.contrato
    ultimo = max(c.aumentos, key=lambda a: (a.fecha_vigencia or date.min, a.id))
    es_ultimo = aum.id == ultimo.id
    if request.method == "POST":
        aum.fecha_vigencia = parse_fecha(request.form.get("fecha_vigencia")) or aum.fecha_vigencia
        anterior = parse_num(request.form.get("precio_anterior"))
        nuevo = parse_num(request.form.get("precio_nuevo"))
        if anterior is not None:
            aum.precio_anterior = anterior
        if nuevo is not None:
            aum.precio_nuevo = nuevo
        if aum.metodo == "porcentaje":
            pct = parse_num(request.form.get("porcentaje"))
            if pct is not None:
                aum.porcentaje = pct
        aum.observaciones = request.form.get("observaciones", "").strip()
        if es_ultimo and aum.precio_nuevo is not None:
            c.precio_actual = aum.precio_nuevo
        db.session.commit()
        flash("Aumento actualizado." + (" El precio actual del contrato se ajustó." if es_ultimo else ""), "ok")
        return redirect(url_for("contratos.ver", cid=c.id))
    return render_template("aumentos/editar.html", a=aum, c=c, es_ultimo=es_ultimo,
                           indice_nombre=INDICE_NOMBRE)


@aumentos_bp.route("/<int:aid>/eliminar", methods=["POST"])
@login_required
def eliminar(aid):
    aum = db.session.get(Aumento, aid) or abort(404)
    c = aum.contrato
    ultimo = max(c.aumentos, key=lambda a: (a.fecha_vigencia or date.min, a.id))
    if aum.id != ultimo.id:
        flash("Solo se puede deshacer el último aumento del contrato.", "error")
        return redirect(url_for("contratos.ver", cid=c.id))
    c.precio_actual = aum.precio_anterior
    db.session.delete(aum)
    db.session.commit()
    flash("Aumento deshecho: se restauró el precio anterior.", "ok")
    return redirect(url_for("contratos.ver", cid=c.id))


# --------------------------------------------------------------------------- #
#  Gestión de índices
# --------------------------------------------------------------------------- #
@aumentos_bp.route("/indices")
@login_required
def indices():
    tipo = request.args.get("tipo", "ICL")
    valores = (IndiceValor.query.filter_by(tipo=tipo)
               .order_by(IndiceValor.periodo.desc()).all())
    return render_template("aumentos/indices.html", valores=valores, tipo=tipo,
                           tipos=TIPOS_INDICE, indice_nombre=INDICE_NOMBRE, meses=MESES_ES)


def _guardar_valor(tipo, periodo, valor, fuente):
    if not (tipo and periodo and valor is not None):
        return False
    iv = IndiceValor.query.filter_by(tipo=tipo, periodo=periodo).first()
    if iv:
        iv.valor = valor
        iv.fuente = fuente
    else:
        db.session.add(IndiceValor(tipo=tipo, periodo=periodo, valor=valor, fuente=fuente))
    return True


@aumentos_bp.route("/indices/nuevo", methods=["POST"])
@login_required
def indice_nuevo():
    tipo = request.form.get("tipo", "ICL")
    periodo = parse_periodo(request.form.get("periodo"))
    valor = parse_num(request.form.get("valor"))
    if _guardar_valor(tipo, periodo, valor, "manual"):
        db.session.commit()
        flash("Valor de índice guardado.", "ok")
    else:
        flash("Completá período y valor.", "error")
    return redirect(url_for("aumentos.indices", tipo=tipo))


@aumentos_bp.route("/indices/importar", methods=["POST"])
@login_required
def indice_importar():
    """Importación masiva: una línea por valor, formato 'YYYY-MM  valor'."""
    tipo = request.form.get("tipo", "ICL")
    texto = request.form.get("datos", "")
    n = 0
    for linea in texto.splitlines():
        linea = linea.strip().replace("\t", " ")
        if not linea:
            continue
        partes = linea.replace(";", " ").replace(",", " ").split()
        if len(partes) < 2:
            # puede venir como "2024-05 123.45" -> ya cubierto; o valor con coma decimal
            partes = linea.split()
        if len(partes) < 2:
            continue
        periodo = parse_periodo(partes[0])
        valor = parse_num(partes[-1])
        if _guardar_valor(tipo, periodo, valor, "importado"):
            n += 1
    db.session.commit()
    flash(f"Se importaron/actualizaron {n} valores de {tipo}.", "ok" if n else "error")
    return redirect(url_for("aumentos.indices", tipo=tipo))


@aumentos_bp.route("/indices/<int:vid>/eliminar", methods=["POST"])
@login_required
def indice_eliminar(vid):
    iv = db.session.get(IndiceValor, vid) or abort(404)
    tipo = iv.tipo
    db.session.delete(iv)
    db.session.commit()
    flash("Valor eliminado.", "ok")
    return redirect(url_for("aumentos.indices", tipo=tipo))


@aumentos_bp.route("/indices/bcra", methods=["POST"])
@login_required
def indice_bcra():
    """Intenta traer el ICL del BCRA (best-effort)."""
    valores, error = traer_icl_bcra()
    if error:
        flash(error, "error")
        return redirect(url_for("aumentos.indices", tipo="ICL"))
    n = 0
    for v in valores:
        if _guardar_valor("ICL", v["periodo"], v["valor"], "BCRA"):
            n += 1
    db.session.commit()
    flash(f"Se actualizaron {n} valores de ICL desde el BCRA.", "ok")
    return redirect(url_for("aumentos.indices", tipo="ICL"))
