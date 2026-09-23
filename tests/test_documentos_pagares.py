"""Contrato y pagarés son documentos separados al imprimir.

Antes se guardaban pegados en `documento_html` con un salto de página: al
imprimir doble faz el pagaré caía en el dorso de la última hoja del contrato.
"""
from datetime import date

from app import db
from app.blueprints.contratos import SEP_PAGARES
from app.models import Contrato, PagareManual


def _guardar_doc(app, cid, html):
    with app.app_context():
        c = db.session.get(Contrato, cid)
        c.documento_html = html
        db.session.commit()


def test_documento_y_pagares_se_sirven_por_separado(client):
    cl, app, ids = client
    _guardar_doc(app, ids["c"],
                 "<h2>CONTRATO</h2><p>cuerpo del contrato</p>" + SEP_PAGARES
                 + '<h2>PAGARÉS EN GARANTÍA</h2><div class="pagare">firma del fiador</div>')

    r = cl.get(f"/contratos/{ids['c']}/documento")
    cuerpo = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "cuerpo del contrato" in cuerpo
    assert "firma del fiador" not in cuerpo
    assert f"/contratos/{ids['c']}/documento/pagares" in cuerpo

    r = cl.get(f"/contratos/{ids['c']}/documento/pagares")
    cuerpo = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "firma del fiador" in cuerpo
    assert "cuerpo del contrato" not in cuerpo
    # Cada pagaré termina su hoja: no comparte papel con el siguiente.
    assert "page-break-after:always" in cuerpo


def test_documento_viejo_con_pagares_pegados_tambien_se_separa(client):
    """Los contratos guardados antes usaban el salto de página como separador."""
    cl, app, ids = client
    _guardar_doc(app, ids["c"],
                 "<h2>CONTRATO</h2><p>contrato viejo</p>"
                 '<div style="page-break-before:always"></div>'
                 '<div class="pagare">pagaré viejo</div>')

    cuerpo = cl.get(f"/contratos/{ids['c']}/documento").get_data(as_text=True)
    assert "contrato viejo" in cuerpo and "pagaré viejo" not in cuerpo
    cuerpo = cl.get(f"/contratos/{ids['c']}/documento/pagares").get_data(as_text=True)
    assert "pagaré viejo" in cuerpo


def test_documento_sin_pagares_no_ofrece_el_link(client):
    cl, app, ids = client
    _guardar_doc(app, ids["c"], "<h2>CONTRATO</h2><p>solo contrato</p>")
    cuerpo = cl.get(f"/contratos/{ids['c']}/documento").get_data(as_text=True)
    assert "solo contrato" in cuerpo
    assert "/documento/pagares" not in cuerpo
    assert cl.get(f"/contratos/{ids['c']}/documento/pagares").status_code == 302


def test_generador_guarda_contrato_y_pagares_separados(client):
    cl, app, ids = client
    r = cl.post("/contratos/desde-generador", json={
        "loc": {"nombre": "Propietario Sep"},
        "lat": {"nombre": "Inquilino Sep"},
        "inm": {"dir": "Calle Separada 1"},
        "econ": {"canon": "150000", "plazo": "24"},
        "fiadores": [], "coLoc": [], "coLat": [],
        "documento": "<h2>CONTRATO</h2>", "pagares": '<div class="pagare">P</div>',
    })
    assert r.status_code == 200 and r.get_json()["ok"] is True
    with app.app_context():
        c = db.session.get(Contrato, r.get_json()["contrato_id"])
        assert SEP_PAGARES in c.documento_html


def test_pagares_del_contrato_usan_la_moneda_del_contrato(client):
    cl, app, ids = client
    with app.app_context():
        c = db.session.get(Contrato, ids["c"])
        c.moneda = "Dólares"
        c.precio_actual = 1000
        db.session.commit()
    cuerpo = cl.get(f"/recibos/pagares/contrato/{ids['c']}?meses=10").get_data(as_text=True)
    assert "US$ 10.000,00" in cuerpo
    assert "dólares estadounidenses" in cuerpo.lower()
    with app.app_context():
        c = db.session.get(Contrato, ids["c"])
        c.moneda = "Pesos"
        db.session.commit()


def test_pagares_del_contrato_avisan_datos_faltantes(client):
    cl, app, ids = client
    with app.app_context():
        from app.models import Fiador
        c = db.session.get(Contrato, ids["c"])
        c.fiadores.append(Fiador(nombre="Fiador Sin Datos"))
        db.session.commit()
    cuerpo = cl.get(f"/recibos/pagares/contrato/{ids['c']}").get_data(as_text=True)
    assert "Fiador Sin Datos: falta el D.N.I." in cuerpo
    assert "Fiador Sin Datos: falta el domicilio" in cuerpo


def test_pagare_manual_numera_las_cuotas_y_corta_por_hoja(client):
    cl, app, ids = client
    with app.app_context():
        pm = PagareManual(fecha=date(2026, 3, 12), lugar="Rosario",
                          beneficiario="Inmobiliaria", deudor="Juan Deudor",
                          deudor_dni="20123456", deudor_domicilio="Mitre 500",
                          monto=50000, moneda="Pesos", cantidad=3,
                          primer_venc=date(2026, 4, 10), cada_dias=30)
        db.session.add(pm)
        db.session.commit()
        pmid = pm.id
    cuerpo = cl.get(f"/recibos/pagares-manuales/{pmid}").get_data(as_text=True)
    assert "cuota 1 de 3" in cuerpo and "cuota 3 de 3" in cuerpo
    assert "page-break-after:always" in cuerpo
    assert "$ 50.000,00" in cuerpo
