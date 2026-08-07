"""Fase 3.4 — Test E2E del circuito completo.

Recorre el circuito de negocio de punta a punta a través de las rutas reales:
contrato → cobrar el alquiler → liquidar al propietario → facturar la comisión
(Facturador mockeado, sin ARCA real) → el CAE queda guardado en la liquidación y
la liquidación NO figura como pendiente de facturar.
"""
from datetime import date


def test_circuito_completo(client, monkeypatch):
    cl, app, ids = client

    # 1) El admin está adentro (login OK del fixture).
    assert cl.get("/").status_code == 200

    # 2) Cobrar el alquiler del mes en curso.
    hoy = date.today()
    r = cl.post("/cobros/rapido", json={
        "cid": ids["c"], "mes": hoy.month, "anio": hoy.year,
        "precio": 180000, "pagado": 180000})
    assert r.status_code == 200 and r.get_json()["ok"] is True

    # 3) Mockear el Facturador: emite con CAE (sin tocar ARCA ni la red).
    import app.facturador as fact

    def _emitir(liq, propietario, ajustes, confirmar_bajo_minimo=False):
        return {"estado": "emitida", "factura": {
            "id": 77, "punto_venta": 1, "numero": 1, "tipo_comprobante": 11,
            "cae": "71234567890123", "cae_vencimiento": "2026-12-31",
            "fecha_comprobante": hoy.isoformat(), "estado": "emitida",
            "referencia_externa": "gestor:1:" + str(liq.numero)}}

    monkeypatch.setattr(fact, "facturar_liquidacion", _emitir)
    # Que la inmobiliaria esté autorizada a facturar en el test.
    monkeypatch.setattr(fact, "inmobiliaria_autorizada", lambda ajustes: True)

    # 4) Generar la liquidación (dispara la facturación de honorarios).
    g = cl.post("/liquidaciones/generar", data={
        "propietario_id": ids["prop"], "mes": hoy.month, "anio": hoy.year},
        follow_redirects=True)
    assert g.status_code == 200

    # 5) Verificar en la base: la liquidación quedó con el CAE guardado.
    from app.models import Liquidacion
    with app.app_context():
        liq = (Liquidacion.query.filter_by(propietario_id=ids["prop"],
                                            periodo_mes=hoy.month, periodo_anio=hoy.year)
               .order_by(Liquidacion.id.desc()).first())
        assert liq is not None, "no se generó la liquidación"
        assert liq.factura_estado == "emitida"
        assert liq.factura_cae == "71234567890123"
        assert float(liq.total_comision or 0) > 0
        liq_id = liq.id

    # 6) La liquidación emitida NO figura como pendiente de facturar.
    from app.blueprints.liquidaciones import _pendientes_facturar_query
    with app.app_context():
        pendientes_ids = [l.id for l in _pendientes_facturar_query().all()]
        assert liq_id not in pendientes_ids
    assert cl.get("/liquidaciones/pendientes-facturar").status_code == 200

    # 7) El comprobante se puede ver desde el gestor (página de la liquidación).
    ver = cl.get(f"/liquidaciones/imprimir/{ids['prop']}?mes={hoy.month}&anio={hoy.year}")
    assert ver.status_code == 200
    assert b"71234567890123" in ver.data   # el CAE emitido se ve en la liquidación
