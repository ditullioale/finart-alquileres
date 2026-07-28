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
                        Aumento, IndiceValor)
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
        lista_a = cl.get("/personas/").data.decode("utf-8", "ignore")
        check("A no ve el cliente de B", "Cliente Solo B" not in lista_a)
        check("A sí ve sus propios datos", "Santamaria Guido" in lista_a)

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
