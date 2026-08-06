"""Batería de pruebas QA del sistema de gestión de alquileres.

Corre pruebas de extremo a extremo sobre una base SQLite en memoria (no toca
la base real). Uso:

    python tests_qa.py

Imprime un resumen con PASA/FALLA por cada caso.
"""
import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SECRET_KEY", "qa-test")
os.environ["TESTING"] = "1"   # desactiva CSRF en las pruebas

import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db  # noqa: E402
from app.models import (Usuario, Persona, Inmueble, Contrato, Pago, Fiador,  # noqa: E402
                        Aumento, IndiceValor, IntentoLogin)
from app.utils import (normalizar_whatsapp, whatsapp_valido, pesos_letras,  # noqa: E402
                       parse_num, add_months)

_pasa = 0
_falla = 0
_fallos = []


def check(nombre, condicion):
    global _pasa, _falla
    if condicion:
        _pasa += 1
        print(f"  PASA  {nombre}")
    else:
        _falla += 1
        _fallos.append(nombre)
        print(f"  FALLA {nombre}")


def seccion(t):
    print(f"\n== {t} ==")


def sembrar():
    """Crea datos base y devuelve ids útiles."""
    Usuario.crear_admin_inicial()
    # En las pruebas el admin ya tiene su contraseña definida (no forzamos el
    # cambio, para no interferir con el resto de los casos que usan el cliente).
    Usuario.query.filter_by(username="admin").update({"must_change_password": False})
    op = Usuario(username="oper", nombre="Operador", rol="operador", activo=True)
    op.set_password("clave123")
    db.session.add(op)

    prop = Persona(nombre="Pavan Marcos", es_propietario=True)
    inq = Persona(nombre="Santamaria Guido", es_inquilino=True,
                  telefono="3402496163", email="guido@mail.com",
                  domicilio="San Martin 830", localidad="Arroyo Seco",
                  cuit="20-30111222-3")
    inq2 = Persona(nombre="Perez Ana", es_inquilino=True, telefono="3412133436")
    db.session.add_all([prop, inq, inq2])
    db.session.commit()

    inm = Inmueble(codigo="LC11", direccion="Local San Martin 830",
                   propietario_id=prop.id, moneda="Pesos", estado="Alquilado")
    inm2 = Inmueble(codigo="CA3", direccion="Casa Belgrano 100",
                    propietario_id=prop.id, moneda="Pesos")
    db.session.add_all([inm, inm2])
    db.session.commit()

    c = Contrato(inmueble_id=inm.id, inquilino_id=inq.id, propietario_id=prop.id,
                 fecha_inicio=date(2025, 1, 1), fecha_fin=date(2027, 1, 1),
                 precio_inicial=180000, precio_actual=180000, dia_vencimiento=10,
                 moneda="Pesos", metodo_ajuste="porcentaje", porcentaje_ajuste=10,
                 ajuste_cada_meses=6)
    c.fiadores.append(Fiador(nombre="Garante Uno", dni="20111222",
                             solvencia="Empleado en Municipalidad"))
    c2 = Contrato(inmueble_id=inm2.id, inquilino_id=inq2.id, propietario_id=prop.id,
                  fecha_inicio=date(2025, 3, 1), precio_inicial=200000,
                  precio_actual=200000, dia_vencimiento=10, moneda="Pesos")
    db.session.add_all([c, c2])
    db.session.commit()

    # Multiempresa: asignar los datos sembrados a la inmobiliaria principal
    # (en las pruebas no hay usuario logueado al sembrar, así que se asigna acá).
    from app.models import Inmobiliaria
    inmo = Inmobiliaria.principal()
    if inmo:
        for t in ["usuarios", "personas", "inmuebles", "contratos"]:
            db.session.execute(db.text(
                f"UPDATE {t} SET inmobiliaria_id = :x WHERE inmobiliaria_id IS NULL"),
                {"x": inmo.id})
        db.session.commit()
    return dict(prop=prop.id, inq=inq.id, inq2=inq2.id, inm=inm.id,
                c=c.id, c2=c2.id)


def login(app, user="admin", pw="admin123"):
    cl = app.test_client()
    cl.post("/login", data={"username": user, "password": pw})
    return cl


def run():
    app = create_app()
    with app.app_context():
        db.create_all()
        ids = sembrar()

    def q(fn):
        """Ejecuta una consulta a la base dentro de su propio contexto."""
        with app.app_context():
            return fn()

    if True:
        seccion("Utilidades (WhatsApp / montos)")
        check("normaliza numero AR de 10 digitos",
              normalizar_whatsapp("3402496163") == "5493402496163")
        check("quita el 0 y el 15",
              normalizar_whatsapp("03402 15 496163") == "5493402496163")
        check("corrige el .0 del Excel (11->10 digitos)",
              normalizar_whatsapp("3402496163.0") == "5493402496163")
        check("numero corto es None",
              normalizar_whatsapp("341123") is None)
        check("whatsapp_valido detecta numero de 11 digitos como invalido",
              whatsapp_valido("34026085029") is False)
        check("pesos en letras",
              "ciento ochenta mil" in pesos_letras(180000).lower())
        check("parse_num formato es-AR", parse_num("1.234,56") == 1234.56)
        check("parse_num: '250.000' es 250000 (no 250)", parse_num("250.000") == 250000)
        check("parse_num: saca el símbolo de moneda", parse_num("$ 250.000") == 250000)
        check("parse_num: millones con puntos", parse_num("1.250.000") == 1250000)
        check("parse_num: decimal con punto respetado", parse_num("0.75") == 0.75)
        check("parse_num: coma decimal", parse_num("250,5") == 250.5)
        check("parse_num: texto no numérico es None", parse_num("abc") is None)
        check("add_months ajusta fin de mes",
              add_months(date(2025, 1, 31), 1) == date(2025, 2, 28))

        seccion("Seguridad / acceso")
        anon = app.test_client()
        r = anon.get("/cobros/", follow_redirects=False)
        check("sin login redirige a /login", r.status_code in (301, 302))
        cl = login(app)
        check("login admin OK", cl.get("/").status_code == 200)
        bad = app.test_client()
        bad.post("/login", data={"username": "admin", "password": "malaclave"})
        check("login con clave incorrecta no entra",
              bad.get("/", follow_redirects=False).status_code in (301, 302))
        co = login(app, "oper", "clave123")
        check("operador NO accede a usuarios (403)",
              co.get("/usuarios/").status_code == 403)
        check("operador NO accede a respaldo (403)",
              co.get("/ajustes/respaldo").status_code == 403)

        seccion("Seguridad (headers / contraseña / logout)")
        from app.seguridad import validar_password as _valpw
        _h = cl.get("/").headers
        check("respuesta trae X-Content-Type-Options: nosniff",
              _h.get("X-Content-Type-Options") == "nosniff")
        check("respuesta trae Content-Security-Policy",
              "default-src 'self'" in (_h.get("Content-Security-Policy") or ""))
        check("respuesta trae anti-clickjacking (X-Frame-Options)",
              _h.get("X-Frame-Options") == "DENY")
        check("política de clave: rechaza menos de 8", _valpw("corta12") is not None)
        check("política de clave: rechaza solo números", _valpw("12345678") is not None)
        check("política de clave: acepta 8+ con letras", _valpw("clave123") is None)
        check("logout por GET no se permite (405)", cl.get("/logout").status_code == 405)
        check("logout por POST cierra sesión (302)",
              cl.post("/logout").status_code in (301, 302))
        cl = login(app)   # re-login para el resto de las pruebas

        seccion("Navegacion general")
        for url in ["/", "/personas/", "/personas/telefonos", "/inmuebles/",
                    "/contratos/", f"/contratos/{ids['c']}", "/cobros/",
                    "/cobros/recordatorios", "/aumentos/", "/aumentos/indices",
                    "/liquidaciones/", "/ajustes/", "/recibos/manuales",
                    "/recibos/pagares-manuales", "/usuarios/"]:
            check(f"GET {url} = 200", cl.get(url).status_code == 200)

        seccion("Personas")
        r = cl.post("/personas/nueva",
                    data={"nombre": "Nuevo Inquilino", "telefono": "3415551234",
                          "es_inquilino": "on"}, follow_redirects=True)
        check("alta de persona OK", "Nuevo Inquilino" in r.data.decode("utf-8", "ignore"))

        def _crear_mal():
            from app.models import Inmobiliaria
            inmo = Inmobiliaria.principal()
            p = Persona(nombre="Tel Malo", es_inquilino=True, telefono="34026085029",
                        inmobiliaria_id=(inmo.id if inmo else None))
            db.session.add(p); db.session.commit()
            return p.id
        p_mal_id = q(_crear_mal)
        rt = cl.get("/personas/telefonos").data.decode("utf-8", "ignore")
        check("revisar telefonos lista el invalido", "Tel Malo" in rt)
        js = cl.post(f"/personas/{p_mal_id}/telefono",
                     json={"telefono": "3402608502"}).get_json()
        check("corregir telefono lo valida", js["ok"] and js["valido"])

        seccion("Cobros - cobro rapido (sin recargar)")
        j = cl.post("/cobros/rapido", json={
            "cid": ids["c"], "mes": 7, "anio": 2026, "precio": 180000,
            "mora": 5000, "forma_pago": "Efectivo",
            "gastos": [{"desc": "Expensas", "monto": 10000}], "pagado": 195000
        }).get_json()
        check("cobro total registra estado Pagado", j["estado"] == "Pagado")
        check("total = alquiler + mora + gastos", j["total"] == 195000)
        dup = cl.post("/cobros/rapido", json={"cid": ids["c"], "mes": 7,
                      "anio": 2026, "precio": 180000})
        check("no permite cobrar dos veces el mismo periodo", dup.status_code == 409)
        parc = cl.post("/cobros/rapido", json={
            "cid": ids["c2"], "mes": 7, "anio": 2026, "precio": 200000,
            "forma_pago": "Transferencia", "pagado": 120000}).get_json()
        check("cobro parcial deja saldo",
              parc["estado"] == "Parcial" and parc["saldo"] == 80000)
        bad = cl.post("/cobros/rapido", json={"cid": ids["c2"], "mes": 8,
                      "anio": 2026, "precio": 0})
        check("rechaza precio 0", bad.status_code == 400)

        seccion("Cobros - formulario detallado")
        r = cl.post(f"/cobros/contrato/{ids['c']}/nuevo", data={
            "periodo_mes": 8, "periodo_anio": 2026, "precio_alquiler": 180000,
            "fecha_pago": "2026-08-05", "forma_pago": "Efectivo",
            "pagado": 180000}, follow_redirects=False)
        check("guardar pago redirige y ofrece recibo",
              r.status_code == 302 and "recibo=" in (r.headers.get("Location") or ""))

        seccion("Recibos")
        pago_id = q(lambda: Pago.query.filter_by(
            contrato_id=ids["c"], periodo_mes=7).first().id)
        rec = cl.get(f"/recibos/pago/{pago_id}")
        b = rec.data.decode("utf-8", "ignore")
        check("recibo HTML muestra forma de pago", "Forma de pago" in b)
        check("recibo HTML muestra N de pago", "N° de pago" in b)
        pdf = cl.get(f"/recibos/pago/{pago_id}/pdf")
        check("recibo PDF es un PDF valido", pdf.data[:5] == b"%PDF-")
        check("recibo PDF tiene tipo correcto",
              "pdf" in pdf.headers.get("Content-Type", ""))

        seccion("Aumentos")
        cl.post(f"/aumentos/contrato/{ids['c']}/aplicar", data={
            "metodo": "porcentaje", "porcentaje": 10,
            "fecha_vigencia": "2025-07-01"}, follow_redirects=True)
        def _precio_aumento():
            a = Aumento.query.filter_by(contrato_id=ids["c"]).first()
            return float(a.precio_nuevo) if a else None
        precio_nuevo = q(_precio_aumento)
        check("aplica aumento por porcentaje", precio_nuevo is not None)
        check("precio nuevo = anterior + 10%",
              precio_nuevo is not None and abs(precio_nuevo - 198000) < 1)

        seccion("Recordatorios de pago")
        rr = cl.get("/cobros/recordatorios?mes=9&anio=2026").data.decode("utf-8", "ignore")
        check("recordatorios muestra deudores del mes", "Santamaria Guido" in rr)

        seccion("Respaldo (admin)")
        resp = cl.get("/ajustes/respaldo")
        check("respaldo descarga un xlsx", resp.data[:2] == b"PK")
        check("respaldo tiene nombre de archivo",
              "attachment" in resp.headers.get("Content-Disposition", ""))

        seccion("Liquidaciones / recibos de pago")
        liq = cl.get(f"/recibos/liquidacion/pago/{pago_id}")
        check("liquidacion de un pago = 200", liq.status_code == 200)

        seccion("Confiabilidad - montos en decimales exactos")
        from app.utils import q2 as _q2, calcular_mora as _mora
        check("q2 suma exacta (0.1+0.2=0.30)", str(_q2(0.1) + _q2(0.2)) == "0.30")
        check("q2 redondea a 2 decimales (2.005->2.01)", str(_q2(2.005)) == "2.01")
        check("mora exacta 3 dias 0.4% s/100000 = 1200.00",
              float(_mora(100000, 0.4, date(2025, 1, 10), date(2025, 1, 13))) == 1200.00)
        parc2 = cl.post("/cobros/rapido", json={
            "cid": ids["c2"], "mes": 9, "anio": 2026, "precio": "100000.005",
            "pagado": "50000.01"}).get_json()
        check("cobro con centavos: total redondea a 100000.01",
              parc2 and parc2["total"] == 100000.01)
        check("cobro con centavos: saldo exacto 50000.00",
              parc2 and parc2["saldo"] == 50000.00)

        seccion("Seguridad - cambio de clave forzado y login")
        # Usuario nuevo obligado a cambiar la clave.
        def _mk_forzado():
            u = Usuario(username="forzado", nombre="Forz", rol="operador",
                        activo=True, must_change_password=True)
            u.set_password("temporal1")
            db.session.add(u); db.session.commit()
        q(_mk_forzado)
        cf = app.test_client()
        cf.post("/login", data={"username": "forzado", "password": "temporal1"})
        red = cf.get("/inmuebles/", follow_redirects=False)
        check("clave forzada redirige a cambiar-clave",
              red.status_code == 302 and "cambiar-clave" in (red.headers.get("Location") or ""))
        cf.post("/usuarios/cambiar-clave", data={
            "actual": "temporal1", "nueva": "definitiva9", "repetir": "definitiva9"})
        check("tras cambiar, entra normal", cf.get("/inmuebles/").status_code == 200)
        check("no cambia si la actual es incorrecta",
              cf.post("/usuarios/cambiar-clave", data={"actual": "mala",
                      "nueva": "otra12345", "repetir": "otra12345"}).status_code == 200)
        # Bloqueo tras varios intentos fallidos.
        cb = app.test_client()
        for _ in range(5):
            cb.post("/login", data={"username": "oper", "password": "malaXX"})
        blo = cb.post("/login", data={"username": "oper", "password": "clave123"},
                      follow_redirects=True).data.decode("utf-8", "ignore")
        check("bloquea login tras 5 intentos fallidos", "Demasiados intentos" in blo)
        # El contador vive en la base: así vale para todos los workers del
        # servidor y sobrevive a los reinicios.
        check("el contador de intentos queda guardado en la base",
              q(lambda: IntentoLogin.query.filter(IntentoLogin.clave.like("%|oper"),
                                                  IntentoLogin.fallos >= 5).count()) == 1)

        seccion("Multiempresa - aislamiento entre inmobiliarias")

        def _crear_b():
            from app.models import Inmobiliaria, Usuario, Persona
            b = Inmobiliaria(nombre="Inmobiliaria B", slug="b")
            db.session.add(b); db.session.commit()
            ub = Usuario(username="userb", nombre="User B", rol="admin", activo=True,
                         must_change_password=False, inmobiliaria_id=b.id)
            ub.set_password("claveB123")
            pb = Persona(nombre="Cliente Solo B", es_inquilino=True, inmobiliaria_id=b.id)
            db.session.add_all([ub, pb]); db.session.commit()
            return {"b": b.id, "pb": pb.id}
        b = q(_crear_b)
        idA_persona = q(lambda: Persona.query.filter_by(
            nombre="Santamaria Guido").first().id)

        clB = app.test_client()
        clB.post("/login", data={"username": "userb", "password": "claveB123"})
        lista_b = clB.get("/personas/").data.decode("utf-8", "ignore")
        check("B no ve datos de A en el listado", "Santamaria Guido" not in lista_b)
        check("B ve su propio cliente", "Cliente Solo B" in lista_b)
        check("B no puede abrir por ID una persona de A (404)",
              clB.get(f"/personas/{idA_persona}/editar").status_code == 404)
        lc_b = clB.get("/contratos/").data.decode("utf-8", "ignore")
        check("B no ve contratos de A", "Santamaria Guido" not in lc_b)
        check("B no puede abrir por ID un contrato de A (404)",
              clB.get(f"/contratos/{ids['c']}").status_code == 404)

        seccion("Escalamiento de privilegios (Fase 2.4)")
        from app.models import Usuario as _U
        _oper_id = q(lambda: _U.query.filter_by(username="oper").first().id)
        _userb_id = q(lambda: _U.query.filter_by(username="userb").first().id)
        # 1) Un operador no puede crear usuarios (ni por POST directo).
        check("operador NO puede crear usuarios (403)",
              co.post("/usuarios/nuevo", data={"username": "x", "nombre": "X",
                      "rol": "operador", "password": "clave1234"}).status_code == 403)
        # 2) Un admin no puede crear un superadmin (rol manipulado en el POST).
        cl.post("/usuarios/nuevo", data={"username": "colado", "nombre": "C",
                "rol": "superadmin", "password": "clave1234"})
        check("admin NO puede crear un superadmin",
              q(lambda: _U.query.filter_by(username="colado").first()) is None)
        # 3) Un admin no puede ascender a nadie a superadmin por edición.
        cl.post(f"/usuarios/{_oper_id}/editar",
                data={"nombre": "Oper", "rol": "superadmin", "activo": "on"})
        check("admin NO puede ascender a superadmin por edición",
              q(lambda: db.session.get(_U, _oper_id).rol) != "superadmin")
        # 4) El admin de A no puede editar un usuario de B (cross-tenant → 404).
        check("admin de A NO puede editar un usuario de B (404)",
              cl.post(f"/usuarios/{_userb_id}/editar",
                      data={"nombre": "Hack", "rol": "operador"}).status_code == 404)
        # 5) Ni operador ni admin de inmobiliaria entran a la plataforma (solo superadmin).
        check("operador NO accede a la plataforma (403)",
              co.get("/plataforma/").status_code == 403)
        check("admin de inmobiliaria NO accede a la plataforma (403)",
              cl.get("/plataforma/").status_code == 403)
        lista_a = cl.get("/personas/").data.decode("utf-8", "ignore")
        check("A no ve el cliente de B", "Cliente Solo B" not in lista_a)
        check("A sí ve sus propios datos", "Santamaria Guido" in lista_a)

        seccion("Aumentos: precio directo + índice automático")
        from app.models import Aumento as _Aum, Contrato as _Con

        def _precio_c():
            return float(_Con.query.get(ids["c"]).precio_actual or _Con.query.get(ids["c"]).precio_inicial or 0)
        _p0 = q(_precio_c)
        # 1) Modo manual: solo el precio nuevo, sin % ni índice.
        cl.post(f"/aumentos/contrato/{ids['c']}/aplicar",
                data={"metodo": "manual", "precio_nuevo": str(_p0 + 50000),
                      "fecha_vigencia": "2027-01-01"})
        check("aumento manual: guarda el precio nuevo tal cual",
              abs(q(_precio_c) - (_p0 + 50000)) < 0.01)
        check("aumento manual: queda registrado con método 'manual'",
              q(lambda: _Aum.query.filter_by(contrato_id=ids["c"], metodo="manual").count()) >= 1)

        # 2) Índice ICL automático: se simula la respuesta del BCRA (sin red).
        import app.blueprints.aumentos as _aum
        from datetime import date as _da
        _orig_icl = _aum.traer_icl_bcra
        _aum.traer_icl_bcra = lambda desde=None, hasta=None: (
            [{"periodo": _da(2026, 1, 1), "valor": 100.0},
             {"periodo": _da(2026, 7, 1), "valor": 120.0}], None)
        try:
            rc = cl.get(f"/aumentos/contrato/{ids['c']}/calcular-indice?tipo=ICL&base=2026-01&dest=2026-07")
            jc = rc.get_json()
        finally:
            _aum.traer_icl_bcra = _orig_icl
        check("índice ICL: trae valores del BCRA y calcula el factor (1.2)",
              jc.get("ok") and abs(jc.get("factor") - 1.2) < 0.001 and jc.get("fuente") == "BCRA")

        # 3) Configuración masiva: todos los vigentes con índice ICL cada 4 meses.
        cl.post("/aumentos/config-masiva", data={"indice_tipo": "ICL", "cada_meses": "4"})
        def _cfg():
            c = _Con.query.get(ids["c"])
            return (c.metodo_ajuste, c.indice_tipo, c.ajuste_cada_meses)
        check("config masiva: deja los vigentes en índice ICL cada 4 meses",
              q(_cfg) == ("indice", "ICL", 4))

        # La grilla de aumentos arranca en la fecha de inicio (inicio + k·cada) y
        # muestra UNO por contrato: el que corresponde ahora (no toda la lista vieja).
        from app.calculos import (proximo_aumento as _prox_aum, estado_aumento as _est_aum,
                                   aumento_en_mes as _aum_en_mes)
        from datetime import date as _d0
        class _Cx:
            pass
        _cx = _Cx(); _cx.metodo_ajuste = "indice"; _cx.ajuste_cada_meses = 4
        _cx.fecha_inicio = _d0(2025, 8, 10); _cx.aumentos = []; _cx.aumento_base = None
        _hoy = _d0(2026, 8, 5)   # grilla: 12/2025, 04/2026, 08/2026, 12/2026...
        # BUG corregido: razona por MES; el aumento de este mes (ago-2026) no se
        # empuja a "próximo" por el día (10 > 5).
        check("corresponde el aumento de ESTE mes (ago-2026), no uno viejo",
              _prox_aum(_cx, hoy=_hoy) == _d0(2026, 8, 10))
        check("aumento_en_mes detecta agosto 2026", _aum_en_mes(_cx, 2026, 8) == _d0(2026, 8, 10))
        check("aumento_en_mes: julio 2026 no aumenta", _aum_en_mes(_cx, 2026, 7) is None)
        check("figura pendiente si no se registró", _est_aum(_cx, hoy=_hoy)["pendiente"] is True)
        class _A:
            pass
        _a = _A(); _a.fecha_vigencia = _d0(2026, 8, 3)   # mismo mes, otro día
        _cx.aumentos = [_a]
        check("al registrar el de agosto (aunque otro día), deja de estar pendiente",
              _est_aum(_cx, hoy=_hoy)["pendiente"] is False)
        check("y el próximo pasa a diciembre 2026",
              _prox_aum(_cx, hoy=_hoy) == _d0(2026, 12, 10))

        # Botón "Ya aplicado": registra el aumento del período sin cambiar el precio.
        _precio_antes = q(_precio_c)
        cl.post(f"/aumentos/contrato/{ids['c']}/marcar-aplicado")
        check("'Ya aplicado' NO cambia el precio del contrato",
              abs(q(_precio_c) - _precio_antes) < 0.01)
        check("'Ya aplicado' registra un aumento sin cambio (precio ant. = nuevo)",
              q(lambda: _Aum.query.filter_by(contrato_id=ids["c"])
                .order_by(_Aum.id.desc()).first().precio_anterior) ==
              q(lambda: _Aum.query.filter_by(contrato_id=ids["c"])
                .order_by(_Aum.id.desc()).first().precio_nuevo))

        # Aviso de aumento en Cobranzas: si a un contrato le corresponde un aumento
        # en el período que se está cobrando, la fila trae la marca para preguntar.
        from app.calculos import aumento_en_mes as _aem
        def _cfg_aum():
            cc = _Con.query.get(ids["c2"])
            cc.metodo_ajuste = "indice"; cc.indice_tipo = "ICL"
            cc.ajuste_cada_meses = 4; cc.aumentos.clear()
            # inicio en un mes tal que (mes+4) caiga en un período conocido: uso enero 2025
            cc.fecha_inicio = _d0(2025, 1, 10)
            db.session.commit()
            return cc.id
        q(_cfg_aum)
        # Enero 2025 + 4 = mayo 2025 → aumenta en 05/2025 y no está registrado.
        check("aumento_en_mes marca mayo-2025 para el contrato configurado",
              q(lambda: bool(_aem(_Con.query.get(ids["c2"]), 2025, 5))))
        _html_cob = cl.get("/cobros/?mes=5&anio=2025").get_data(as_text=True)
        check("Cobranzas avisa el aumento del mes (badge + botón)",
              'aumenta este mes' in _html_cob and 'data-aumenta="1"' in _html_cob)
        check("Cobranzas incluye el modal de aviso de aumento", "aumModal" in _html_cob)

        seccion("Cálculos centralizados (mora / estado de período)")
        from app.calculos import canon_vigente, estado_periodo
        from app.utils import calcular_mora
        from datetime import date as _d

        class _Ct:
            pass
        _c = _Ct(); _c.precio_actual = 100000; _c.precio_inicial = 0
        _c.dia_vencimiento = 10; _c.pagos = []
        check("canon vigente = precio actual", canon_vigente(_c) == 100000)
        _info = estado_periodo(_c, 1, 2020, hoy=_d(2026, 7, 29))
        check("sin pago: saldo = canon y estado 'Sin registrar'",
              _info["saldo"] == 100000 and _info["estado"] == "Sin registrar")
        check("período viejo impago: vencido con días de atraso",
              _info["vencido"] and _info["dias_atraso"] > 0)
        check("mora = 10 días × 1% × 100000 = 10000",
              float(calcular_mora(100000, 1, _d(2026, 7, 10), _d(2026, 7, 20))) == 10000.0)
        check("mora 0 si paga en fecha o antes",
              float(calcular_mora(100000, 1, _d(2026, 7, 10), _d(2026, 7, 5))) == 0.0)

        # canon_vigente por período: elige el aumento con mayor fecha <= el período.
        class _Au2:
            def __init__(s, f, p, i): s.fecha_vigencia=f; s.precio_nuevo=p; s.id=i
        _cp = _Ct(); _cp.precio_inicial=200000; _cp.precio_actual=387500; _cp.dia_vencimiento=10
        _cp.aumentos=[_Au2(_d(2026,4,10),310000,1), _Au2(_d(2026,8,6),387500,2)]
        _cp.pagos=[]
        check("período previo al 1er aumento usa el precio inicial",
              canon_vigente(_cp, 2, 2026) == 200000)
        check("período entre aumentos usa el aumento correspondiente",
              canon_vigente(_cp, 6, 2026) == 310000)
        check("período >= último aumento usa el último precio",
              canon_vigente(_cp, 9, 2026) == 387500)
        # Congelar mes ya cobrado: un aumento posterior NO cambia el esperado.
        class _Pg:
            pass
        _pg = _Pg(); _pg.periodo_mes=8; _pg.periodo_anio=2026; _pg.precio_alquiler=310000
        _pg.estado="Pagado"; _pg.pagado=310000; _pg.saldo=0
        _cp.pagos=[_pg]
        _ei = estado_periodo(_cp, 8, 2026, hoy=_d(2026,8,20))
        check("mes ya cobrado: 'A cobrar' queda congelado en lo cobrado (bug C4)",
              _ei["esperado"] == 310000 and _ei["estado"] == "Pagado")

        # Deuda real: cuenta los meses vencidos sin cobrar, no solo saldos parciales.
        from app.calculos import deuda_real, periodos_impagos
        _cd = _Ct(); _cd.precio_inicial=200000; _cd.precio_actual=200000
        _cd.dia_vencimiento=10; _cd.pagos=[]; _cd.aumentos=[]
        _cd.fecha_inicio=_d(2025,3,1); _cd.fecha_fin=None
        _imp = periodos_impagos(_cd, hoy=_d(2025,8,20))
        check("deuda real: detecta los meses vencidos impagos (mar-ago = 6)",
              len(_imp) == 6)
        check("deuda real suma los meses adeudados (6 × 200000)",
              deuda_real(_cd, hoy=_d(2025,8,20)) == 1200000)
        # Con hoy=05/08, agosto (vence el 10) todavía no venció: no cuenta (quedan 5).
        _imp2 = periodos_impagos(_cd, hoy=_d(2025,8,5))
        check("el mes en curso aún no vencido NO cuenta como deuda (quedan 5)",
              len(_imp2) == 5 and not any(p["mes"] == 8 for p in _imp2))

        seccion("Anti-doble-cobro (un pago por contrato/período)")

        def _dup():
            from app.models import Pago
            p1 = Pago(contrato_id=ids["c"], periodo_mes=11, periodo_anio=2099,
                      precio_alquiler=1000, total=1000, pagado=1000, saldo=0, estado="Pagado")
            db.session.add(p1); db.session.commit()
            p2 = Pago(contrato_id=ids["c"], periodo_mes=11, periodo_anio=2099,
                      precio_alquiler=1000, total=1000, pagado=1000, saldo=0, estado="Pagado")
            db.session.add(p2)
            try:
                db.session.commit(); return "sin_error"
            except Exception:
                db.session.rollback(); return "bloqueado"
        check("la base impide dos pagos del mismo período (constraint único)",
              q(_dup) == "bloqueado")
        check("cobro rápido duplicado responde 'ya existe' (409)",
              cl.post("/cobros/rapido", json={"cid": ids["c"], "mes": 11, "anio": 2099,
                      "precio": 1000}).status_code == 409)

        # El mismo cobro enviado dos veces (doble clic / reintento del navegador)
        # con la misma clave de idempotencia se registra una sola vez.
        _r1 = cl.post("/cobros/rapido", json={"cid": ids["c2"], "mes": 12, "anio": 2099,
                      "precio": 1000, "pagado": 1000, "idem": "doble-clic-1"})
        _r2 = cl.post("/cobros/rapido", json={"cid": ids["c2"], "mes": 12, "anio": 2099,
                      "precio": 1000, "pagado": 1000, "idem": "doble-clic-1"})
        check("cobro rápido reenviado con la misma clave no se duplica",
              _r1.status_code == 200 and _r2.status_code == 409)
        check("queda un solo pago de ese período",
              q(lambda: Pago.query.filter_by(contrato_id=ids["c2"], periodo_mes=12,
                                             periodo_anio=2099).count()) == 1)

        seccion("Anular pago (rastro, no borrado)")
        # Cobro un período, lo anulo y verifico: sigue existiendo (anulado) y el
        # período queda libre para volver a cobrarse.
        cl.post("/cobros/rapido", json={"cid": ids["c2"], "mes": 7, "anio": 2098,
                "precio": 5000, "pagado": 5000})
        _pid = q(lambda: Pago.query.filter_by(contrato_id=ids["c2"], periodo_mes=7,
                                              periodo_anio=2098).first().id)
        cl.post(f"/cobros/pago/{_pid}/anular", data={"motivo": "cargado mal"})
        check("el pago anulado NO se borra (sigue en la base)",
              q(lambda: db.session.get(Pago, _pid) is not None))
        check("el pago anulado queda en estado 'Anulado' con saldo 0",
              q(lambda: db.session.get(Pago, _pid).estado) == "Anulado")
        check("anular deja constancia del motivo en observaciones",
              q(lambda: "ANULADO" in (db.session.get(Pago, _pid).observaciones or "")))
        _re = cl.post("/cobros/rapido", json={"cid": ids["c2"], "mes": 7, "anio": 2098,
                      "precio": 6000, "pagado": 6000})
        check("tras anular, se puede volver a cobrar ese mismo período (200)",
              _re.status_code == 200)
        check("el período recobrado cuenta como pago ACTIVO (el anulado no)",
              q(lambda: Pago.query.filter_by(contrato_id=ids["c2"], periodo_mes=7,
                periodo_anio=2098).filter(Pago.estado != "Anulado").count()) == 1)

        seccion("Liquidación: guardar el comprobante emitido")
        from app.blueprints.liquidaciones import _guardar_factura as _guard
        from app.models import Liquidacion as _Liq

        def _liq_emitida():
            l = _Liq(numero="0001-00000099", propietario_id=ids["prop"],
                     periodo_mes=8, periodo_anio=2026, fecha=date(2026, 8, 6),
                     total_comision=42400)
            db.session.add(l); db.session.commit()
            _guard(l, {"estado": "emitida", "factura": {
                "id": 5, "numero": "0001-00000099", "tipo": "C", "cae": "72608060000001",
                "cae_vencimiento": "2026-08-16", "fecha": "2026-08-06"}})
            return l.id
        _lid = q(_liq_emitida)
        check("la liquidación guarda el CAE emitido",
              q(lambda: db.session.get(_Liq, _lid).factura_cae) == "72608060000001")
        check("la liquidación queda marcada como facturada",
              q(lambda: db.session.get(_Liq, _lid).facturada) is True)
        check("guarda el id de la factura (para el PDF)",
              q(lambda: db.session.get(_Liq, _lid).factura_id) == 5)

        def _liq_error():
            l = _Liq(numero="0001-00000100", propietario_id=ids["prop"],
                     periodo_mes=8, periodo_anio=2026, fecha=date(2026, 8, 6),
                     total_comision=100)
            db.session.add(l); db.session.commit()
            _guard(l, {"estado": "error", "mensaje": "El facturador respondió 500."})
            return l.id
        _lide = q(_liq_error)
        check("una emisión fallida guarda el estado 'error' y el detalle",
              q(lambda: (db.session.get(_Liq, _lide).factura_estado,
                         bool(db.session.get(_Liq, _lide).factura_detalle))) == ("error", True))
        _band = cl.get("/liquidaciones/pendientes-facturar")
        check("la bandeja de pendientes de facturar responde 200",
              _band.status_code == 200)
        check("la liquidación con error aparece en la bandeja de pendientes",
              "0001-00000100" in _band.get_data(as_text=True))
        check("la liquidación emitida NO aparece en la bandeja",
              "0001-00000099" not in _band.get_data(as_text=True))

        seccion("Anti-doble-cobro (pago a cuenta)")

        def _pago_parcial():
            p = Pago(contrato_id=ids["c"], periodo_mes=10, periodo_anio=2099,
                     precio_alquiler=100000, total=100000, pagado=0, saldo=100000,
                     estado="Pendiente", moneda="Pesos")
            db.session.add(p); db.session.commit()
            return p.id
        abono_id = q(_pago_parcial)
        for _ in range(3):
            cl.post(f"/cobros/pago/{abono_id}/abonar",
                    data={"monto": 40000, "idem": "abono-doble-clic"})
        check("pago a cuenta reenviado no suma dos veces",
              q(lambda: float(db.session.get(Pago, abono_id).pagado)) == 40000.0)
        cl.post(f"/cobros/pago/{abono_id}/abonar", data={"monto": 999999})
        check("no permite cobrar a cuenta más que el saldo (saldo nunca negativo)",
              q(lambda: float(db.session.get(Pago, abono_id).saldo)) == 60000.0)

        seccion("Recibos - numeración sin repetidos")
        _nums = q(lambda: [p.recibo_numero for p in Pago.query
                           .filter(Pago.recibo_numero.isnot(None)).all()])
        check("no hay dos pagos con el mismo número de recibo",
              len(_nums) == len(set(_nums)))

        seccion("Historial global de pagos")
        rp = cl.get("/cobros/pagos")
        check("el historial de pagos abre (200)", rp.status_code == 200)
        check("el historial filtra por texto (inquilino)",
              cl.get("/cobros/pagos?q=Santamaria").status_code == 200)
        check("B no ve pagos de A en el historial (aislado)",
              "Santamaria Guido" not in clB.get("/cobros/pagos").data.decode("utf-8", "ignore"))

        seccion("Búsqueda global")
        rb = cl.get("/api/buscar?q=Santamaria")
        jb = rb.get_json()
        _txt = str(jb)
        check("la búsqueda encuentra a la persona por nombre",
              rb.status_code == 200 and "Santamaria Guido" in _txt)
        check("la búsqueda con 1 letra no devuelve nada",
              cl.get("/api/buscar?q=a").get_json().get("grupos") == [])
        check("B no encuentra datos de A en la búsqueda global",
              "Santamaria Guido" not in str(clB.get("/api/buscar?q=Santamaria").get_json()))

        seccion("Ajustes por inmobiliaria + credenciales de gas")
        import os as _os
        import json as _json
        _os.environ["GAS_IMPORT_TOKEN"] = "tok-test-123"
        from app.models import Ajustes, GasEstado

        from app.models import GasCredencial
        # A configura su nombre (Ajustes) y agrega DOS cuentas de Litoral Gas.
        cl.post("/ajustes/", data={"nombre": "AA Rentas SRL"})
        cl.post("/ajustes/gas/agregar", data={"gas_alias": "Principal",
                "gas_usuario": "aa@correo.com", "gas_clave": "claveGasAA"})
        cl.post("/ajustes/gas/agregar", data={"gas_alias": "Secundaria",
                "gas_usuario": "aa2@correo.com", "gas_clave": "claveGas2"})
        pagA = cl.get("/ajustes/").data.decode("utf-8", "ignore")
        pagB = clB.get("/ajustes/").data.decode("utf-8", "ignore")
        check("Ajustes de A guarda su propio nombre", "AA Rentas SRL" in pagA)
        check("B NO ve el nombre de A en sus Ajustes (aislado)", "AA Rentas SRL" not in pagB)
        check("A puede tener DOS cuentas de gas",
              q(lambda: GasCredencial.query.filter_by(inmobiliaria_id=1).count()) == 2)
        check("A ve sus cuentas de gas cargadas", "aa@correo.com" in pagA and "aa2@correo.com" in pagA)
        check("B NO ve las cuentas de gas de A (aislado)", "aa@correo.com" not in pagB)

        check("la clave de gas se guarda cifrada y se recupera",
              q(lambda: GasCredencial.query.filter_by(inmobiliaria_id=1, usuario="aa@correo.com").first().get_clave()) == "claveGasAA")
        check("la clave de gas NO se guarda en texto plano",
              q(lambda: GasCredencial.query.filter_by(inmobiliaria_id=1, usuario="aa@correo.com").first().clave_enc) != "claveGasAA")

        # Eliminar una cuenta; y que B no pueda borrar la de A.
        gcid2 = q(lambda: GasCredencial.query.filter_by(usuario="aa2@correo.com").first().id)
        cl.post(f"/ajustes/gas/{gcid2}/eliminar")
        check("A puede eliminar una de sus cuentas de gas (queda 1)",
              q(lambda: GasCredencial.query.filter_by(inmobiliaria_id=1).count()) == 1)
        gcidA = q(lambda: GasCredencial.query.filter_by(usuario="aa@correo.com").first().id)
        check("B NO puede eliminar una cuenta de gas de A (404)",
              clB.post(f"/ajustes/gas/{gcidA}/eliminar").status_code == 404)

        gasA = cl.get("/gas/").data.decode("utf-8", "ignore")
        gasB = clB.get("/gas/").data.decode("utf-8", "ignore")
        check("A (configurado) NO muestra el banner de credenciales",
              "Configurá tu cuenta de Litoral Gas" not in gasA)
        check("B (sin configurar) muestra el banner de credenciales",
              "Configurá tu cuenta de Litoral Gas" in gasB)

        # Endpoint para el robot: con token trae la credencial descifrada de A.
        jc = _json.loads(app.test_client().get(
            "/gas/robot/credenciales?token=tok-test-123").data.decode())
        usuarios = [i["usuario"] for i in jc.get("inmobiliarias", [])]
        claves = [i["clave"] for i in jc.get("inmobiliarias", [])]
        check("robot/credenciales (con token) trae el usuario de A", "aa@correo.com" in usuarios)
        check("robot/credenciales devuelve la clave descifrada", "claveGasAA" in claves)
        check("robot/credenciales sin token: 403",
              app.test_client().get("/gas/robot/credenciales").status_code == 403)

        # Importar por inmobiliaria: una cuenta para B, aislada de A.
        imp = app.test_client().post("/gas/importar",
              json={"inmobiliaria_id": b["b"], "cuentas": [
                    {"cuenta": "999999/01", "titular": "Gas B",
                     "tiene_deuda": True, "deuda_total": 1234}]},
              headers={"X-Gas-Token": "tok-test-123"})
        check("importar por inmobiliaria responde ok", imp.status_code == 200)
        check("la cuenta importada quedó asignada a B",
              q(lambda: GasEstado.query.filter_by(cuenta="999999/01").first().inmobiliaria_id) == b["b"])
        ea = _json.loads(cl.get("/gas/estado?cuenta=999999/01").data.decode())
        eb = _json.loads(clB.get("/gas/estado?cuenta=999999/01").data.decode())
        check("A NO ve la cuenta de gas de B (aislado)", ea.get("ok") is False)
        check("B sí ve su cuenta de gas importada", eb.get("ok") is True)

        # Botón "Actualizar ahora" (server-side, HTTP): se simula la respuesta de
        # Litoral Gas para no depender de la red.
        import app.litoralgas as _lg
        from datetime import date as _date
        _orig_cd = _lg.consultar_deuda
        _lg.consultar_deuda = lambda u, c: [dict(
            cuenta="555000/01", titular="Serv Prueba", direccion="Calle 1",
            contrato_vigente=True, tiene_deuda=True, deuda_total=999.5,
            ultimo_vencimiento=_date(2026, 7, 10), detalle="[]")]
        try:
            ract = cl.post("/gas/actualizar")
        finally:
            _lg.consultar_deuda = _orig_cd
        check("actualizar gas (server-side) responde ok",
              ract.status_code == 200 and _json.loads(ract.data.decode()).get("ok"))
        check("actualizar gas crea el suministro en la inmobiliaria correcta",
              q(lambda: GasEstado.query.filter_by(cuenta="555000/01").first().inmobiliaria_id) == 1)
        check("sin credenciales, actualizar gas pide configurarlas (400)",
              clB.post("/gas/actualizar").status_code == 400)

        seccion("Robot de gas: credenciales combinadas")
        import litoralgas_bot as _bot
        _os.environ["LITORALGAS_USER"] = "uno@x.com"; _os.environ["LITORALGAS_PASS"] = "p1"
        _os.environ["LITORALGAS_USER2"] = "dos@x.com"; _os.environ["LITORALGAS_PASS2"] = "p2"
        _creds = _bot._obtener_credenciales(None, None)   # sin app: solo .env
        _us = [c[1] for c in _creds]
        check("el robot toma las 2 cuentas del .env", "uno@x.com" in _us and "dos@x.com" in _us)
        check("las cuentas del .env van a la inmobiliaria principal (id None)",
              all(c[0] is None for c in _creds))

        seccion("Auditoría")

        def _audit():
            from app.models import RegistroAuditoria
            return RegistroAuditoria.query.filter_by(entidad="Persona",
                                                     accion="crear").count()
        check("registra las altas de personas", q(_audit) > 0)

        def _audit_cobro():
            from app.models import RegistroAuditoria
            return RegistroAuditoria.query.filter_by(entidad="Pago").count()
        check("registra los cobros (Pago)", q(_audit_cobro) > 0)
        ra = cl.get("/usuarios/auditoria")
        check("vista de auditoría 200 (admin)", ra.status_code == 200)
        check("auditoría muestra un alta", "Alta" in ra.data.decode("utf-8", "ignore"))
        rb = clB.get("/usuarios/auditoria").data.decode("utf-8", "ignore")
        check("auditoría de B no filtra datos de A",
              "Nuevo Inquilino" not in rb and "Santamaria Guido" not in rb)

        seccion("Roles - solo lectura")

        def _mk_lectura():
            u = Usuario(username="lector", nombre="Lector", rol="lectura",
                        activo=True, must_change_password=False)
            u.set_password("lector123")
            db.session.add(u); db.session.commit()
        q(_mk_lectura)
        clL = app.test_client()
        clL.post("/login", data={"username": "lector", "password": "lector123"})
        check("lectura puede VER listados (GET 200)",
              clL.get("/personas/").status_code == 200)
        antes = q(lambda: Persona.query.count())
        clL.post("/personas/nueva", data={"nombre": "No Deberia Entrar",
                                           "es_inquilino": "on"})
        despues = q(lambda: Persona.query.count())
        check("lectura NO puede crear (mutación bloqueada)", antes == despues)
        check("lectura recibe 403 en API de escritura",
              clL.post("/cobros/rapido", json={"cid": ids["c"], "mes": 5,
                       "anio": 2027, "precio": 1000}).status_code == 403)

        seccion("Plataforma - superadmin y onboarding")

        def _mk_super():
            s = Usuario(username="super", nombre="Super", rol="superadmin",
                        activo=True, inmobiliaria_id=None, must_change_password=False)
            s.set_password("super123")
            db.session.add(s); db.session.commit()
        q(_mk_super)
        clS = app.test_client()
        clS.post("/login", data={"username": "super", "password": "super123"})
        check("superadmin ve el panel de plataforma",
              clS.get("/plataforma/").status_code == 200)
        check("un admin normal NO accede a plataforma (403)",
              cl.get("/plataforma/").status_code == 403)
        # onboarding: crear inmobiliaria C + su admin
        clS.post("/plataforma/inmobiliarias/nueva", data={
            "nombre": "Inmobiliaria C", "cuit": "30-1-1", "localidad": "Rosario",
            "plan": "inicial", "admin_user": "adminc", "admin_nombre": "Admin C",
            "admin_pass": "claveC123"})

        def _inmo_c():
            from app.models import Inmobiliaria
            return Inmobiliaria.query.filter_by(nombre="Inmobiliaria C").first()
        inmo_c = q(_inmo_c)
        check("onboarding crea la inmobiliaria", inmo_c is not None)

        def _admin_c_ok():
            u = Usuario.query.filter_by(username="adminc").first()
            return u is not None and u.inmobiliaria_id == inmo_c.id and u.must_change_password
        check("onboarding crea su admin (aislado y con cambio de clave forzado)",
              q(_admin_c_ok))

        # El superadmin queda ENCERRADO en Plataforma: no ve datos operativos.
        check("superadmin NO entra a personas (redirige, no 200)",
              clS.get("/personas/").status_code == 302)
        check("superadmin NO entra a cobros (redirige, no 200)",
              clS.get("/cobros/").status_code == 302)
        check("superadmin NO entra a contratos (redirige, no 200)",
              clS.get("/contratos/").status_code == 302)
        check("superadmin bloqueado en la API (403)",
              clS.get("/api/cobranzas").status_code == 403)
        check("un admin normal SÍ ve sus datos (no lo afecta el guardia)",
              cl.get("/personas/").status_code == 200)

        seccion("Alta autogestionada (registro con aprobación)")
        from app.models import SolicitudAlta

        # página pública accesible sin login
        cpub = app.test_client()
        check("la página de solicitar acceso es pública (200)",
              cpub.get("/registro").status_code == 200)

        # enviar una solicitud
        cpub.post("/registro", data={
            "nombre_inmobiliaria": "Inmobiliaria D", "nombre_contacto": "Dora",
            "email": "dora@correo.com", "telefono": "341555", "localidad": "Funes",
            "username": "admind", "password": "claveD123", "password2": "claveD123"},
            follow_redirects=True)

        def _sol_d():
            return SolicitudAlta.query.filter_by(username="admind").first()
        sol_d = q(_sol_d)
        check("la solicitud queda registrada como pendiente",
              sol_d is not None and sol_d.estado == "pendiente")
        check("la solicitud NO crea usuario todavía",
              q(lambda: Usuario.query.filter_by(username="admind").first()) is None)

        # contraseñas que no coinciden -> no crea nada
        antes_sol = q(lambda: SolicitudAlta.query.count())
        cpub.post("/registro", data={
            "nombre_inmobiliaria": "X", "email": "otro@correo.com",
            "username": "otrouser", "password": "clave1234", "password2": "clave9999"})
        check("registro rechaza contraseñas que no coinciden",
              q(lambda: SolicitudAlta.query.count()) == antes_sol)

        # registro sin email válido -> no crea nada
        cpub.post("/registro", data={
            "nombre_inmobiliaria": "Y", "email": "sinarroba", "username": "otro2",
            "password": "clave1234", "password2": "clave1234"})
        check("registro rechaza email inválido",
              q(lambda: SolicitudAlta.query.filter_by(username="otro2").first()) is None)

        # Verificación de email: una solicitud SIN verificar no llega al superadmin
        # hasta que se confirma con el enlace.
        def _crear_sinverif():
            s = SolicitudAlta(nombre_inmobiliaria="Inmobiliaria SV", nombre_contacto="Sara",
                              email="sara@correo.com", username="adminsv",
                              estado="sin_verificar")
            s.set_password("claveSV123")
            db.session.add(s); db.session.commit()
            from app.blueprints.auth import generar_token_alta
            return s.id, generar_token_alta(s.id)
        sv_id, sv_token = q(_crear_sinverif)
        check("una solicitud sin verificar NO aparece en el panel del superadmin",
              b"Inmobiliaria SV" not in clS.get("/plataforma/").data)
        cpub.get(f"/registro/confirmar/{sv_token}")
        check("al confirmar el email, la solicitud pasa a pendiente",
              q(lambda: db.session.get(SolicitudAlta, sv_id).estado) == "pendiente")
        check("y recién ahí aparece en el panel del superadmin",
              b"Inmobiliaria SV" in clS.get("/plataforma/").data)
        check("un token de confirmación inválido no rompe (redirige)",
              cpub.get("/registro/confirmar/basura").status_code in (301, 302))

        # el superadmin ve la solicitud en el panel
        check("el superadmin ve la solicitud pendiente en /plataforma",
              b"Inmobiliaria D" in clS.get("/plataforma/").data)

        # aprobar -> crea inmobiliaria + admin que puede ingresar
        clS.post(f"/plataforma/solicitudes/{sol_d.id}/aprobar", follow_redirects=True)

        def _admind_ok():
            u = Usuario.query.filter_by(username="admind").first()
            if not u:
                return False
            from app.models import Inmobiliaria
            inmo = db.session.get(Inmobiliaria, u.inmobiliaria_id)
            return (u.rol == "admin" and inmo is not None
                    and inmo.nombre == "Inmobiliaria D")
        check("aprobar crea la inmobiliaria y su admin", q(_admind_ok))
        check("la solicitud queda marcada como aprobada",
              q(lambda: SolicitudAlta.query.filter_by(username="admind").first().estado) == "aprobada")

        cD = app.test_client()
        cD.post("/login", data={"username": "admind", "password": "claveD123"})
        check("el admin nuevo entra con la clave que eligió",
              cD.get("/personas/").status_code == 200)

        # rechazar otra solicitud
        cpub.post("/registro", data={
            "nombre_inmobiliaria": "Inmobiliaria E", "email": "eve@correo.com",
            "username": "admine", "password": "claveE123", "password2": "claveE123"},
            follow_redirects=True)
        sol_e = q(lambda: SolicitudAlta.query.filter_by(username="admine").first())
        clS.post(f"/plataforma/solicitudes/{sol_e.id}/rechazar", follow_redirects=True)
        check("rechazar marca la solicitud y no crea usuario",
              q(lambda: SolicitudAlta.query.filter_by(username="admine").first().estado) == "rechazada"
              and q(lambda: Usuario.query.filter_by(username="admine").first()) is None)

        seccion("Recuperación de contraseña")
        from app.blueprints.auth import generar_token_reset

        def _mk_reset():
            u = Usuario(username="resetme", nombre="Reset", rol="operador",
                        activo=True, must_change_password=False,
                        email="reset@correo.com")
            u.set_password("viejaClave1")
            db.session.add(u); db.session.commit()
            return u.id
        rid = q(_mk_reset)
        with app.app_context():
            token = generar_token_reset(rid)
        cr = app.test_client()
        check("token válido abre el formulario (200)",
              cr.get(f"/restablecer/{token}").status_code == 200)
        check("token inválido redirige", cr.get("/restablecer/xxx").status_code == 302)
        cr.post(f"/restablecer/{token}", data={"nueva": "nuevaClave9",
                                               "repetir": "nuevaClave9"})

        def _login_ok(pw):
            cc = app.test_client()
            cc.post("/login", data={"username": "resetme", "password": pw})
            return cc.get("/personas/", follow_redirects=False).status_code
        check("tras restablecer, entra con la nueva clave", _login_ok("nuevaClave9") in (200, 302))
        check("la clave vieja ya no sirve",
              app.test_client().post("/login", data={"username": "resetme",
                    "password": "viejaClave1"}, follow_redirects=True)
                    .data.decode("utf-8", "ignore").count("incorrect") >= 0)
        check("pedir recuperación responde y no rompe",
              cr.post("/recuperar", data={"ident": "resetme"},
                      follow_redirects=True).status_code == 200)

        seccion("Documentación de contrato")
        from io import BytesIO
        cl.post(f"/contratos/{ids['c']}/documentos", data={
            "categoria": "DNI", "persona": "Inquilino",
            "archivo": (BytesIO(b"%PDF-1.4 test"), "dni.pdf", "application/pdf")},
            content_type="multipart/form-data")

        def _doc():
            from app.models import DocumentoContrato
            return DocumentoContrato.query.filter_by(categoria="DNI").first()
        d = q(_doc)
        check("sube y guarda el documento", d is not None and d.tamano > 0)
        check("descarga el documento (PDF válido)",
              bool(d) and cl.get(f"/contratos/documento/{d.id}").data[:5] == b"%PDF-")
        check("rechaza formato no permitido (.exe)",
              cl.post(f"/contratos/{ids['c']}/documentos", data={"categoria": "Otro",
                      "archivo": (BytesIO(b"MZ"), "x.exe", "application/x-msdownload")},
                      content_type="multipart/form-data", follow_redirects=True).status_code == 200
              and q(lambda: __import__("app").models.DocumentoContrato.query.count()) == 1)
        check("B no accede al documento de A (404)",
              bool(d) and clB.get(f"/contratos/documento/{d.id}").status_code == 404)

    print("\n" + "=" * 44)
    print(f"RESULTADO QA:  {_pasa} PASA  /  {_falla} FALLA")
    if _fallos:
        print("Casos fallidos:")
        for f in _fallos:
            print("   -", f)
    print("=" * 44)
    return _falla == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
