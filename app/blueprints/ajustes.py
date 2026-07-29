"""Ajustes de la inmobiliaria y cambio de contraseña."""
from functools import wraps
from io import BytesIO
from datetime import date

from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, abort, make_response)
from flask_login import login_required, current_user

from .. import db
from ..models import Ajustes
from ..utils import parse_num

ajustes_bp = Blueprint("ajustes", __name__, url_prefix="/ajustes")


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper


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
        # Credenciales de Litoral Gas (por inmobiliaria). La clave solo se toca si
        # se escribió una nueva; el checkbox "borrar" limpia ambas.
        if request.form.get("gas_borrar"):
            a.gas_usuario = None
            a.gas_clave_enc = None
        else:
            a.gas_usuario = request.form.get("gas_usuario", "").strip() or None
            nueva_clave = request.form.get("gas_clave", "")
            if nueva_clave:
                a.set_gas_clave(nueva_clave)
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


@ajustes_bp.route("/respaldo")
@login_required
@admin_required
def respaldo():
    """Descarga un Excel con todos los datos del sistema (respaldo)."""
    import pandas as pd
    from flask_login import current_user
    from ..models import (Persona, Inmueble, Contrato, Fiador, Aumento, Pago,
                          GastoExtra, Liquidacion, ReciboManual,
                          IndiceValor, Usuario)

    def filas(query, campos):
        return pd.DataFrame([{c: getattr(o, c) for c in campos} for o in query])

    # Modelos con inmobiliaria_id: sus .query ya vienen filtrados por tenant.
    # Los "hijos" (Fiador, GastoExtra) se acotan por su contrato/pago (que sí
    # está filtrado). Usuarios se acota a la inmobiliaria del que exporta.
    usuarios_q = Usuario.query
    if getattr(current_user, "rol", None) != "superadmin":
        usuarios_q = usuarios_q.filter(
            Usuario.inmobiliaria_id == current_user.inmobiliaria_id)

    hojas = {
        "Personas": filas(Persona.query, ["id", "nombre", "dni", "cuit", "domicilio",
            "localidad", "telefono", "email", "cond_iva", "es_propietario",
            "es_inquilino", "observaciones"]),
        "Inmuebles": filas(Inmueble.query, ["id", "codigo", "tipo", "direccion", "localidad",
            "provincia", "barrio", "estado", "moneda", "precio_referencia",
            "comision_pct", "propietario_id", "observaciones"]),
        "Contratos": filas(Contrato.query, ["id", "numero", "inmueble_id", "inquilino_id",
            "propietario_id", "fecha_inicio", "fecha_fin", "duracion_meses",
            "precio_inicial", "precio_actual", "moneda", "dia_vencimiento",
            "mora_diaria_pct", "comision_pct", "metodo_ajuste", "indice_tipo",
            "ajuste_cada_meses", "porcentaje_ajuste", "estado"]),
        "Fiadores": filas(Fiador.query.join(Contrato), ["id", "contrato_id", "nombre",
            "dni", "domicilio", "telefono", "email", "solvencia"]),
        "Aumentos": filas(Aumento.query, ["id", "contrato_id", "fecha_vigencia",
            "precio_anterior", "precio_nuevo", "metodo", "indice_tipo", "porcentaje"]),
        "Pagos": filas(Pago.query, ["id", "contrato_id", "numero", "periodo_mes",
            "periodo_anio", "fecha_pago", "precio_alquiler", "mora", "total",
            "pagado", "saldo", "moneda", "forma_pago", "recibo_numero", "estado",
            "observaciones"]),
        "GastosExtra": filas(GastoExtra.query.join(Pago), ["id", "pago_id",
            "descripcion", "monto"]),
        "Liquidaciones": filas(Liquidacion.query, ["id", "numero", "fecha", "periodo_mes",
            "periodo_anio", "propietario_id", "contrato_id", "total_ingresos",
            "total_comision", "total_neto"]),
        "RecibosManuales": filas(ReciboManual.query, ["id", "numero", "fecha", "cliente",
            "concepto_general", "total", "forma_pago"]),
        "Indices": filas(IndiceValor.query, ["id", "tipo", "periodo", "valor", "fuente"]),
        "Usuarios": filas(usuarios_q, ["id", "username", "nombre", "email", "rol", "activo"]),
    }

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        for nombre, dfh in hojas.items():
            if dfh.empty:
                dfh = pd.DataFrame({"(sin datos)": []})
            dfh.to_excel(xl, sheet_name=nombre[:31], index=False)
    buf.seek(0)
    nombre = f"Respaldo_alquileres_{date.today().strftime('%Y-%m-%d')}.xlsx"
    resp = make_response(buf.read())
    resp.headers["Content-Type"] = ("application/vnd.openxmlformats-officedocument."
                                    "spreadsheetml.sheet")
    resp.headers["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return resp
