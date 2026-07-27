"""Importador de datos exportados de Inmosoft (archivos .xlsx).

Lee personas, inmuebles y alquileres (con todo el historial de pagos) y los
carga en la base de datos del sistema. Las liquidaciones NO se importan porque
el sistema las regenera a partir de los pagos.

Uso:
    python importar_inmosoft.py [CARPETA_CON_LOS_XLSX]

Si no se indica carpeta, usa ../DatosInmosoft_23Julio2026 (junto al proyecto).
El script es re-ejecutable: no duplica contratos ya importados (usa el idAlquiler).
"""
import sys
import re
from pathlib import Path
from datetime import datetime, date

import pandas as pd

from app import create_app, db
from app.models import Persona, Inmueble, Contrato, Pago, Fiador

MESES = {m: i for i, m in enumerate(
    ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
     "agosto", "septiembre", "octubre", "noviembre", "diciembre"])}


# --------------------------- helpers de parseo ----------------------------- #
def txt(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


def tel(v):
    """Teléfono desde Excel: los números vienen como decimales (3402539090.0).
    Devuelve el entero como texto ('3402539090'), sin el '.0' que agregaba un
    dígito de más."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, float):
        return str(int(v))
    return re.sub(r"\.0+$", "", str(v).strip())


def num(v):
    s = txt(v)
    if s == "":
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def entero(v):
    n = num(v)
    return int(n) if n is not None else None


def a_fecha(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (datetime, pd.Timestamp)):
        return v.date()
    s = txt(v)
    if not s:
        return None
    s = s.split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def estado_inmueble(s):
    s = txt(s).lower()
    if "alquil" in s:
        return "Alquilado"
    if "reserv" in s:
        return "Reservado"
    return "Disponible"


def estado_contrato(s):
    s = txt(s).lower()
    if "vigen" in s:
        return "Vigente"
    if "finaliz" in s or "termin" in s:
        return "Finalizado"
    if "rescind" in s:
        return "Rescindido"
    return "Vigente"


# --------------------------- caché de personas ----------------------------- #
_cache_persona = {}


def buscar_o_crear_persona(nombre, *, propietario=False, inquilino=False):
    nombre = txt(nombre)
    if not nombre:
        return None
    clave = nombre.lower()
    p = _cache_persona.get(clave)
    if not p:
        p = Persona.query.filter(db.func.lower(Persona.nombre) == clave).first()
    if not p:
        p = Persona(nombre=nombre)
        db.session.add(p)
        _cache_persona[clave] = p
    if propietario:
        p.es_propietario = True
    if inquilino:
        p.es_inquilino = True
    return p


# ------------------------------ importadores ------------------------------- #
def importar_personas(carpeta):
    df = pd.read_excel(carpeta / "personas.xlsx", sheet_name="Personas")
    n = 0
    for _, r in df.iterrows():
        nombre = txt(r.get("Nombre"))
        if not nombre:
            continue
        clave = nombre.lower()
        p = Persona.query.filter(db.func.lower(Persona.nombre) == clave).first()
        if not p:
            p = Persona(nombre=nombre)
            db.session.add(p)
            n += 1
        p.telefono = tel(r.get("Telefonos")) or tel(r.get("Celular"))
        p.domicilio = txt(r.get("Direccion"))
        p.email = txt(r.get("Email"))
        p.localidad = txt(r.get("Localidad"))
        p.dni = txt(r.get("DNI"))
        p.cuit = txt(r.get("CUIT"))
        p.cond_iva = txt(r.get("Condicion IVA")) or "Consumidor Final"
        p.observaciones = txt(r.get("Observaciones"))
        _cache_persona[clave] = p
    db.session.commit()
    return n


def importar_inmuebles(carpeta):
    df = pd.read_excel(carpeta / "inmuebles.xlsx", sheet_name="Inmuebles")
    n = 0
    for _, r in df.iterrows():
        codigo = txt(r.get("Código"))
        direccion = txt(r.get("Dirección")) or txt(r.get("Detalle"))
        if not (codigo or direccion):
            continue
        inm = None
        if codigo:
            inm = Inmueble.query.filter_by(codigo=codigo).first()
        if not inm:
            inm = Inmueble(codigo=codigo or None, direccion=direccion or "s/d")
            db.session.add(inm)
            n += 1
        inm.tipo = txt(r.get("Tipo inmueble"))
        inm.direccion = direccion or inm.direccion
        inm.localidad = txt(r.get("Localidad"))
        inm.provincia = txt(r.get("Provincia"))
        inm.barrio = txt(r.get("Barrio"))
        inm.estado = estado_inmueble(r.get("Estado"))
        inm.moneda = txt(r.get("Moneda")) or "Pesos"
        inm.precio_referencia = num(r.get("Precio"))
        inm.dormitorios = entero(r.get("Dormitorios"))
        prop = txt(r.get("Propietario"))
        if prop:
            inm.propietario = buscar_o_crear_persona(prop, propietario=True)
    db.session.commit()
    return n


def _kv_y_pagos(hoja):
    """Extrae datos clave-valor y la tabla de pagos de una hoja de detalle."""
    filas = hoja.values.tolist()
    kv, pagos, pago_hdr = {}, [], None
    for i, r in enumerate(filas):
        c0 = txt(r[0]) if len(r) > 0 else ""
        c1 = r[1] if len(r) > 1 else None
        if c0 == "Fecha" and txt(c1) == "Nro Pago":
            pago_hdr = i
            break
        if c0 and c1 is not None and not (isinstance(c1, float) and pd.isna(c1)):
            kv[c0] = r[1]
    if pago_hdr is not None:
        for r in filas[pago_hdr + 1:]:
            if len(r) < 5 or txt(r[0]) == "" and txt(r[1]) == "":
                break
            if txt(r[0]) == "":
                break
            pagos.append(r)
    # Garantes
    garantes = []
    for i, r in enumerate(filas):
        if txt(r[0]) == "idAlquiler" and len(r) > 2 and txt(r[2]) == "garante":
            for g in filas[i + 1:]:
                if txt(g[0]) in ("", "Sin registros") and txt(g[2]) == "":
                    break
                if txt(g[2]):
                    garantes.append(g)
            break
    return kv, pagos, garantes


def importar_alquileres(carpeta):
    xl = pd.ExcelFile(carpeta / "alquileres.xlsx")
    resumen = xl.parse(xl.sheet_names[0])
    fin_por_id = {}
    for _, r in resumen.iterrows():
        idalq = txt(r.get("idAlquiler"))
        if idalq:
            fin_por_id[idalq] = a_fecha(r.get("Fecha fin contrato"))

    n_contr = n_pagos = 0
    for hoja_nombre in xl.sheet_names[1:]:
        try:
            nc, npg = _importar_una_hoja(xl.parse(hoja_nombre, header=None), fin_por_id)
            n_contr += nc
            n_pagos += npg
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            print(f"  ⚠ Ficha '{hoja_nombre}' salteada por un dato inválido: {e}")
    return n_contr, n_pagos


def _importar_una_hoja(hoja, fin_por_id):
    kv, pagos, garantes = _kv_y_pagos(hoja)
    idalq = txt(kv.get("idAlquiler"))
    if not idalq:
        return 0, 0
    if Contrato.query.filter_by(numero=idalq).first():
        return 0, 0  # ya importado

    if True:
        codigo = txt(kv.get("codigoInmueble"))
        inm = Inmueble.query.filter_by(codigo=codigo).first() if codigo else None
        if not inm:
            inm = Inmueble(codigo=codigo or None,
                           direccion=txt(kv.get("inmueble")) or "s/d",
                           estado="Alquilado")
            db.session.add(inm)
        inquilino = buscar_o_crear_persona(kv.get("inquilino"), inquilino=True)
        propietario = buscar_o_crear_persona(kv.get("propietario"), propietario=True)
        if propietario and not inm.propietario:
            inm.propietario = propietario
        db.session.flush()

        fi = a_fecha(kv.get("fechaInicio"))
        dur = entero(kv.get("duracionContrato"))
        precio_ini = num(kv.get("montoAlquiler"))

        c = Contrato(
            numero=idalq,
            inmueble_id=inm.id,
            inquilino_id=inquilino.id if inquilino else None,
            propietario_id=propietario.id if propietario else None,
            fecha_inicio=fi,
            fecha_fin=fin_por_id.get(idalq),
            duracion_meses=dur,
            precio_inicial=precio_ini,
            precio_actual=precio_ini,
            moneda=txt(kv.get("moneda")) or "Pesos",
            dia_vencimiento=entero(kv.get("diaVtoInquilino")) or 10,
            mora_diaria_pct=num(kv.get("moraDiaria")) or 0,
            metodo_ajuste="sin_ajuste",   # se reconfigura por contrato si se quiere
            estado=estado_contrato(kv.get("estado")),
            origen="importado",
            observaciones=txt(kv.get("notas")) or txt(kv.get("observaciones")),
        )
        # comisión al inmueble (solo si es un porcentaje razonable 0-100)
        pc = num(kv.get("porcComisionInmo"))
        if pc is not None and 0 <= pc <= 100 and inm.comision_pct is None:
            inm.comision_pct = pc
        db.session.add(c)
        db.session.flush()

        # Pagos (fila: 0 Fecha,1 Nro,2 De,3 Mes,4 Año,5 Total,6 Saldo,7 Moneda,
        #        8 PagadoProp,...,12 ReciboXInq)
        n_pagos = 0
        max_nro, precio_actual = 0, precio_ini
        for r in pagos:
            mes = MESES.get(txt(r[3]).lower()) if len(r) > 3 else None
            anio = entero(r[4]) if len(r) > 4 else None
            total = num(r[5]) if len(r) > 5 else None
            if not (mes and anio):
                continue
            saldo = num(r[6]) if len(r) > 6 else 0
            saldo = saldo or 0
            pagado = round((total or 0) - saldo, 2)
            nro = entero(r[1]) if len(r) > 1 else None
            prop_pago = txt(r[8]) if len(r) > 8 else ""
            fprop = a_fecha(prop_pago.replace("Pagado el:", "")) if "Pagado el" in prop_pago else None
            p = Pago(
                contrato_id=c.id, numero=nro, periodo_mes=mes, periodo_anio=anio,
                fecha_pago=a_fecha(r[0]) if len(r) > 0 else None,
                precio_alquiler=total, total=total, saldo=saldo, pagado=pagado,
                moneda=txt(r[7]) if len(r) > 7 else "Pesos",
                pagado_al_propietario=fprop,
                recibo_numero=txt(r[12]) if len(r) > 12 else "",
                estado="Pagado" if saldo <= 0.005 else ("Parcial" if pagado > 0 else "Pendiente"),
            )
            db.session.add(p)
            n_pagos += 1
            if nro and nro >= max_nro:
                max_nro, precio_actual = nro, total
        c.precio_actual = precio_actual or precio_ini

        for g in garantes:
            c.fiadores.append(Fiador(
                nombre=txt(g[2]), telefono=tel(g[3]) or tel(g[4]),
                domicilio=txt(g[5]), email=txt(g[6])))

        db.session.commit()
        return 1, n_pagos
    return n_contr, n_pagos


def main():
    reset = "--reset" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    carpeta = Path(args[0]) if args else \
        Path(__file__).resolve().parent.parent / "DatosInmosoft_23Julio2026"
    if not carpeta.exists():
        print(f"No encuentro la carpeta: {carpeta}")
        sys.exit(1)

    app = create_app()
    with app.app_context():
        if reset:
            print("Reiniciando la base (borrando tablas y recreándolas)…")
            db.drop_all()
        db.create_all()
        print("Importando personas…")
        np = importar_personas(carpeta)
        print(f"  personas nuevas: {np}")
        print("Importando inmuebles…")
        ni = importar_inmuebles(carpeta)
        print(f"  inmuebles nuevos: {ni}")
        print("Importando alquileres y pagos…")
        nc, npg = importar_alquileres(carpeta)
        print(f"  contratos nuevos: {nc} | pagos importados: {npg}")
        print("\nListo. Totales en la base:")
        print(f"  Personas:  {Persona.query.count()}")
        print(f"  Inmuebles: {Inmueble.query.count()}")
        print(f"  Contratos: {Contrato.query.count()}")
        print(f"  Pagos:     {Pago.query.count()}")


if __name__ == "__main__":
    main()
