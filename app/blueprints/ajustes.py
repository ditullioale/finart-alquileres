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
        db.session.commit()
        flash("Ajustes guardados.", "ok")
        return redirect(url_for("ajustes.index"))
    from ..models import GasCredencial
    credenciales_gas = GasCredencial.query.order_by(GasCredencial.id).all()
    from .. import facturador
    return render_template("ajustes/index.html", a=a, credenciales_gas=credenciales_gas,
                           facturador_habilitado=facturador.habilitado())


@ajustes_bp.route("/facturador", methods=["POST"])
@login_required
@admin_required
def facturador_config():
    """Configura el emisor de ARCA de esta inmobiliaria (multiempresa)."""
    from .. import facturador
    a = Ajustes.get()
    if not (a.cuit and len("".join(c for c in a.cuit if c.isdigit())) == 11):
        flash("Cargá primero el CUIT de la inmobiliaria (arriba) antes de configurar ARCA.", "error")
        return redirect(url_for("ajustes.index"))
    modo = request.form.get("arca_mode", "homologacion")
    pv = parse_num(request.form.get("punto_venta"), entero=True) or 1
    tipo = parse_num(request.form.get("tipo_comprobante"), entero=True) or 11
    cert = request.files.get("cert")
    clave = request.files.get("clave")
    cert_bytes = cert.read() if cert and cert.filename else None
    key_bytes = clave.read() if clave and clave.filename else None
    if modo != "mock" and not a.facturador_configurado and not (cert_bytes and key_bytes):
        flash("Subí el certificado (.crt/.pem) y la clave privada (.key) de ARCA.", "error")
        return redirect(url_for("ajustes.index"))
    res = facturador.registrar_emisor(
        a, cert_bytes=cert_bytes, key_bytes=key_bytes,
        punto_venta=pv, tipo_comprobante=tipo, arca_mode=modo,
    )
    if res.get("ok"):
        a.set_facturador_token(res["token"])
        a.facturador_modo = modo
        a.facturador_pv = pv
        db.session.commit()
        flash("Facturación electrónica configurada.", "ok")
    else:
        flash(f"No se pudo configurar la facturación: {res.get('error')}", "error")
    return redirect(url_for("ajustes.index"))


@ajustes_bp.route("/gas/agregar", methods=["POST"])
@login_required
def gas_agregar():
    """Agrega una cuenta de Litoral Gas a la inmobiliaria actual."""
    from ..models import GasCredencial
    usuario = request.form.get("gas_usuario", "").strip()
    clave = request.form.get("gas_clave", "")
    alias = request.form.get("gas_alias", "").strip() or "Cuenta"
    if not usuario or not clave:
        flash("Cargá el usuario y la contraseña de Litoral Gas.", "error")
    else:
        gc = GasCredencial(alias=alias, usuario=usuario)   # inmobiliaria_id: auto
        gc.set_clave(clave)
        db.session.add(gc)
        db.session.commit()
        flash("Cuenta de Litoral Gas agregada.", "ok")
    return redirect(url_for("ajustes.index") + "#gas")


@ajustes_bp.route("/gas/<int:cid>/eliminar", methods=["POST"])
@login_required
def gas_eliminar(cid):
    from ..models import GasCredencial
    from ..tenant import get_or_404_tenant
    gc = get_or_404_tenant(GasCredencial, cid)
    db.session.delete(gc)
    db.session.commit()
    flash("Cuenta de Litoral Gas eliminada.", "ok")
    return redirect(url_for("ajustes.index") + "#gas")


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
