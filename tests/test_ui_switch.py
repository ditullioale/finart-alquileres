"""Interruptor de diseño (UI=nueva|clasica).

El diseño clásico tiene que seguir siendo el default y poder recuperarse en
cualquier momento, sin redeploy: es la red de seguridad del rediseño.
"""


def test_default_es_el_diseno_clasico(client):
    cl, _app, _ = client
    html = cl.get("/").get_data(as_text=True)
    assert 'class="sidebar"' in html
    assert "aurora.css" not in html


def test_con_ui_nueva_se_sirve_aurora(client):
    cl, app, _ = client
    app.config["UI"] = "nueva"
    try:
        html = cl.get("/").get_data(as_text=True)
        assert "aurora.css" in html
        assert 'class="side"' in html
    finally:
        app.config["UI"] = "clasica"


def test_el_parametro_gana_y_queda_recordado(client):
    cl, _app, _ = client
    r = cl.get("/?ui=nueva")
    assert "aurora.css" in r.get_data(as_text=True)
    assert "ui=nueva" in r.headers.get("Set-Cookie", "")
    # La cookie sola alcanza para seguir viendo el diseño nuevo.
    assert "aurora.css" in cl.get("/").get_data(as_text=True)
    # Y se vuelve al clásico sin tocar el entorno.
    assert "aurora.css" not in cl.get("/?ui=clasica").get_data(as_text=True)


def test_valor_invalido_cae_al_clasico(client):
    cl, app, _ = client
    app.config["UI"] = "cualquier-cosa"
    try:
        assert "aurora.css" not in cl.get("/").get_data(as_text=True)
    finally:
        app.config["UI"] = "clasica"


def test_pantalla_sin_migrar_sigue_usando_el_clasico(client):
    """Sólo se rediseña de a una pantalla: el resto no cambia."""
    cl, _app, _ = client
    html = cl.get("/personas/?ui=nueva").get_data(as_text=True)
    assert 'class="sidebar"' in html
    assert "aurora.css" not in html
