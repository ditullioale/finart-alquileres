"""Paridad Aurora ↔ clásico.

Garantiza que el diseño nuevo (Aurora, ``?ui=nueva``) no pierda funcionalidad
respecto del clásico (``?ui=clasica``):

  1. Cada pantalla operativa responde 200 en las DOS versiones (no hay plantilla
     Aurora rota ni ruta que se quede sin diseño).
  2. Aurora expone las mismas **acciones de mutación** (formularios POST:
     cobrar, editar, eliminar, rescindir, subir documento, nota de seguimiento,
     etc.) que la versión clásica.
  3. El botón/enlace de **WhatsApp** sigue estando donde el clásico lo tenía.

Los filtros por estado/rol en Aurora se implementan como pestañas (links con
``?estado=`` / ``?rol=``), no como ``<select>``; por eso la paridad se mide por
acciones POST y no por inputs de filtro.
"""
import re

import pytest


def _post_actions(html):
    """Endpoints de los formularios POST presentes en el HTML."""
    acciones = set()
    for tag in re.findall(r"<form\b[^>]*>", html, re.I):
        if re.search(r'method\s*=\s*["\']post["\']', tag, re.I):
            m = re.search(r'action\s*=\s*["\']([^"\'?]+)', tag)
            if m:
                acciones.add(m.group(1))
    return acciones


def _get(cl, url, ui):
    sep = "&" if "?" in url else "?"
    return cl.get(f"{url}{sep}ui={ui}")


def _pago_con_saldo(app, ids):
    """Asegura (y devuelve) un pago con saldo pendiente en el contrato sembrado."""
    from datetime import date
    from app import db
    from app.models import Pago
    with app.app_context():
        p = Pago.query.filter_by(contrato_id=ids["c"]).first()
        if p is None:
            p = Pago(contrato_id=ids["c"], numero=1, periodo_mes=1, periodo_anio=2024,
                     fecha_pago=date(2024, 1, 5), precio_alquiler=100000, moneda="Pesos",
                     total=100000, pagado=60000, saldo=40000, estado="Parcial")
            db.session.add(p)
            db.session.commit()
        return p.id


def _pantallas(ids, pid):
    c = ids["c"]
    return {
        "dashboard": "/",
        "cobranzas": "/cobros/",
        "detalle_pagos": f"/cobros/contrato/{c}",
        "registrar_pago": f"/cobros/contrato/{c}/nuevo",
        "editar_pago": f"/cobros/pago/{pid}/editar",
        "abonar": f"/cobros/pago/{pid}/abonar",
        "cargar_varios": f"/cobros/contrato/{c}/pagos-multiples",
        "historial_pagos": "/cobros/pagos",
        "recordatorios": "/cobros/recordatorios",
        "contratos_list": "/contratos/",
        "ficha_contrato": f"/contratos/{c}",
        "aumentos": "/aumentos/",
        "liquidaciones": "/liquidaciones/",
        "personas": "/personas/",
        "inmuebles": "/inmuebles/",
        "ajustes": "/ajustes/",
    }


def test_todas_las_pantallas_responden_en_ambos_disenos(client):
    cl, app, ids = client
    pid = _pago_con_saldo(app, ids)
    for nombre, url in _pantallas(ids, pid).items():
        rc = _get(cl, url, "clasica")
        ra = _get(cl, url, "nueva")
        assert rc.status_code == 200, f"{nombre} (clásico) devolvió {rc.status_code}"
        assert ra.status_code == 200, f"{nombre} (Aurora) devolvió {ra.status_code}"


def _acciones_ficha(cl, cid, ui):
    """La ficha de contrato Aurora reparte las acciones en pestañas: se unen todas."""
    acc = set()
    for t in ["resumen", "pagos", "aumentos", "liquidaciones", "docs", "seguimiento"]:
        acc |= _post_actions(_get(cl, f"/contratos/{cid}?t={t}", ui).get_data(as_text=True))
    return acc


def test_aurora_conserva_las_acciones_de_mutacion(client):
    cl, app, ids = client
    pid = _pago_con_saldo(app, ids)
    # Pantallas donde comparamos acciones POST directas (no dependen de pestañas).
    directas = {
        "detalle_pagos": f"/cobros/contrato/{ids['c']}",
        "abonar": f"/cobros/pago/{pid}/abonar",
        "registrar_pago": f"/cobros/contrato/{ids['c']}/nuevo",
        "contratos_list": "/contratos/",
    }
    for nombre, url in directas.items():
        clasicas = _post_actions(_get(cl, url, "clasica").get_data(as_text=True))
        aurora = _post_actions(_get(cl, url, "nueva").get_data(as_text=True))
        faltan = clasicas - aurora
        assert not faltan, f"{nombre}: Aurora perdió acciones POST {faltan}"

    # Ficha de contrato: la clásica es una sola página; Aurora usa pestañas.
    clasicas = _post_actions(_get(cl, f"/contratos/{ids['c']}", "clasica").get_data(as_text=True))
    aurora = _acciones_ficha(cl, ids["c"], "nueva")
    faltan = clasicas - aurora
    assert not faltan, f"ficha_contrato: Aurora perdió acciones POST {faltan}"


def test_whatsapp_presente_en_aurora(client):
    cl, app, ids = client
    # Pantallas donde el clásico ofrece WhatsApp: Aurora también debe ofrecerlo.
    urls = ["/cobros/", f"/cobros/contrato/{ids['c']}", "/cobros/recordatorios",
            "/contratos/", "/personas/", f"/contratos/{ids['c']}"]
    for url in urls:
        hc = _get(cl, url, "clasica").get_data(as_text=True)
        ha = _get(cl, url, "nueva").get_data(as_text=True)
        wa_clasico = ("wa.me" in hc) or ("api.whatsapp" in hc)
        if wa_clasico:
            assert ("wa.me" in ha) or ("api.whatsapp" in ha) or ("WhatsApp" in ha), \
                f"{url}: el clásico tiene WhatsApp y Aurora no"
