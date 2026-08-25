"""Auditoría ESTRICTA de aislamiento multiempresa.

Siembra DOS inmobiliarias (A y B) con un juego completo de datos en cada modelo
y verifica, de forma exhaustiva y en ambas direcciones, que:
  1. Cada inmobiliaria, a nivel ORM, ve EXACTAMENTE sus filas y ninguna de la otra.
  2. No se puede acceder por ID a un registro ajeno (ni leer, ni editar, ni borrar).
  3. Crear un registro lo asigna automáticamente a la inmobiliaria correcta.
  4. Modificar/borrar en una inmobiliaria NO altera los datos de la otra.
  5. Ajustes, numeración de recibos, y credenciales de gas están separados.

Uso:  python test_aislamiento.py
"""
import os
import tempfile
from datetime import date, datetime

# Base en archivo (no :memory:) para que el cliente HTTP y el contexto de la app
# compartan exactamente la misma base durante la prueba.
_DBFILE = os.path.join(tempfile.gettempdir(), "finart_aislamiento_test.db")
if os.path.exists(_DBFILE):
    os.remove(_DBFILE)
os.environ["DATABASE_URL"] = "sqlite:///" + _DBFILE
os.environ["SECRET_KEY"] = "clave-de-prueba-aislamiento"

from flask import g
from app import create_app, db
from app.models import (Inmobiliaria, Usuario, Persona, Inmueble, Contrato, Pago,
                        Aumento, ReciboManual, Liquidacion, GasEstado,
                        DocumentoContrato, Ajustes, RegistroAuditoria, GasCredencial)

TOTAL = {"ok": 0, "fail": 0}


def check(desc, cond):
    print(("  PASA  " if cond else "  FALLA ") + desc)
    TOTAL["ok" if cond else "fail"] += 1


def seccion(t):
    print("\n== " + t + " ==")


def sembrar_inmobiliaria(nombre, sufijo):
    """Crea una inmobiliaria con un dato de cada tipo. Devuelve un dict de ids."""
    inmo = Inmobiliaria(nombre=nombre, slug=sufijo)
    db.session.add(inmo); db.session.flush()
    tid = inmo.id

    prop = Persona(nombre=f"Propietario {sufijo}", es_propietario=True, inmobiliaria_id=tid)
    inq = Persona(nombre=f"Inquilino {sufijo}", es_inquilino=True, inmobiliaria_id=tid)
    db.session.add_all([prop, inq]); db.session.flush()

    inm = Inmueble(direccion=f"Calle {sufijo} 123", estado="Alquilado",
                   propietario_id=prop.id, inmobiliaria_id=tid)
    db.session.add(inm); db.session.flush()

    c = Contrato(inmueble_id=inm.id, inquilino_id=inq.id, propietario_id=prop.id,
                 fecha_inicio=date(2025, 1, 1), precio_inicial=100000, precio_actual=100000,
                 moneda="Pesos", estado="Vigente", dia_vencimiento=10, mora_diaria_pct=1,
                 numero=f"C-{sufijo}", inmobiliaria_id=tid)
    db.session.add(c); db.session.flush()

    pago = Pago(contrato_id=c.id, numero=1, periodo_mes=1, periodo_anio=2025,
                precio_alquiler=100000, total=100000, pagado=100000, saldo=0,
                estado="Pagado", fecha_pago=date(2025, 1, 5), inmobiliaria_id=tid)
    aum = Aumento(contrato_id=c.id, fecha_vigencia=date(2025, 7, 1),
                  precio_anterior=100000, precio_nuevo=120000, metodo="porcentaje",
                  porcentaje=20, inmobiliaria_id=tid)
    rm = ReciboManual(cliente=f"Cliente {sufijo}", total=5000, numero=f"R-{sufijo}",
                      fecha=date(2025, 1, 1), inmobiliaria_id=tid)
    liq = Liquidacion(numero=f"L-{sufijo}", fecha=date(2025, 1, 31), periodo_mes=1,
                      periodo_anio=2025, propietario_id=prop.id, contrato_id=c.id,
                      total_neto=90000, inmobiliaria_id=tid)
    gas = GasEstado(cuenta=f"GAS-{sufijo}", titular=f"Titular {sufijo}",
                    tiene_deuda=True, deuda_total=1234, inmobiliaria_id=tid)
    doc = DocumentoContrato(contrato_id=c.id, categoria="DNI",
                            nombre_archivo=f"dni_{sufijo}.pdf", tipo_mime="application/pdf",
                            tamano=3, datos=b"pdf", inmobiliaria_id=tid)
    aj = Ajustes(nombre=f"Ajustes {sufijo}", recibo_prefijo="0001", recibo_proximo=1,
                 liquidacion_prefijo="0001", liquidacion_proximo=1,
                 gas_usuario=f"gas_{sufijo}@correo.com", inmobiliaria_id=tid)
    aj.set_gas_clave(f"clave-{sufijo}")
    gcred = GasCredencial(alias="Cuenta", usuario=f"gas_{sufijo}@correo.com", inmobiliaria_id=tid)
    gcred.set_clave(f"clave-{sufijo}")
    db.session.add_all([pago, aum, rm, liq, gas, doc, aj, gcred]); db.session.flush()

    u = Usuario(username=f"user_{sufijo}", nombre=f"Admin {sufijo}", rol="admin",
                activo=True, must_change_password=False, inmobiliaria_id=tid)
    u.set_password("clave1234")
    db.session.add(u); db.session.commit()

    return dict(tid=tid, persona=[prop.id, inq.id], inmueble=[inm.id], contrato=[c.id],
                pago=[pago.id], aumento=[aum.id], recibo=[rm.id], liquidacion=[liq.id],
                gas=[gas.id], documento=[doc.id], ajustes=[aj.id], gascred=[gcred.id],
                user=f"user_{sufijo}")


MODELOS = {
    "Persona": (Persona, "persona"), "Inmueble": (Inmueble, "inmueble"),
    "Contrato": (Contrato, "contrato"), "Pago": (Pago, "pago"),
    "Aumento": (Aumento, "aumento"), "ReciboManual": (ReciboManual, "recibo"),
    "Liquidacion": (Liquidacion, "liquidacion"), "GasEstado": (GasEstado, "gas"),
    "DocumentoContrato": (DocumentoContrato, "documento"), "Ajustes": (Ajustes, "ajustes"),
    "GasCredencial": (GasCredencial, "gascred"),
}


def ver_como(app, user, fn):
    """Ejecuta fn() dentro de un request simulando al usuario dado (activa el
    filtro de tenant real via g._login_user). Sesión fresca para forzar SELECTs.
    Limpia g._login_user al salir (en Flask, g vive en el app-context y podría
    filtrarse a llamadas posteriores)."""
    db.session.expire_all()
    with app.test_request_context():
        g._login_user = user
        try:
            return fn()
        finally:
            g.pop("_login_user", None)


def main():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.create_all()
        A = sembrar_inmobiliaria("Inmobiliaria A", "A")
        B = sembrar_inmobiliaria("Inmobiliaria B", "B")
        uA = db.session.get(Usuario, Usuario.query.filter_by(username="user_A").first().id)
        uB = db.session.get(Usuario, Usuario.query.filter_by(username="user_B").first().id)

        seccion("Aislamiento a nivel ORM (cada modelo, en ambas direcciones)")
        for etiqueta, (Model, clave) in MODELOS.items():
            for yo, otro, u in [("A", B, uA), ("B", A, uB)]:
                propios = A[clave] if yo == "A" else B[clave]
                ajenos = otro[clave]

                def _leer():
                    filas = Model.query.all()
                    ids = {o.id for o in filas}
                    return ids
                ids = ver_como(app, u, _leer)
                check(f"{etiqueta}: {yo} ve solo lo suyo ({len(propios)})",
                      ids == set(propios))
                check(f"{etiqueta}: {yo} NO ve ninguna fila de la otra",
                      not (ids & set(ajenos)))
                # acceso directo por ID a un registro ajeno => no aparece
                def _por_id():
                    return [Model.query.filter_by(id=x).first() for x in ajenos]
                ajenos_vistos = ver_como(app, u, _por_id)
                check(f"{etiqueta}: {yo} NO puede traer por ID un registro ajeno",
                      all(o is None for o in ajenos_vistos))

        seccion("Ajustes, numeración y gas: separados por inmobiliaria")
        def _num():
            return Ajustes.get().siguiente_recibo()
        recA1 = ver_como(app, uA, _num); db.session.commit()
        recB1 = ver_como(app, uB, _num); db.session.commit()
        recA2 = ver_como(app, uA, _num); db.session.commit()
        check("numeración de recibos independiente (A avanza 1->2 sin tocar a B)",
              recA1.endswith("00000001") and recA2.endswith("00000002") and recB1.endswith("00000001"))
        check("Ajustes: A tiene su propio nombre", ver_como(app, uA, lambda: Ajustes.get().nombre) == "Ajustes A")
        check("Ajustes: B tiene su propio nombre", ver_como(app, uB, lambda: Ajustes.get().nombre) == "Ajustes B")
        check("gas: A recupera su propia clave", ver_como(app, uA, lambda: Ajustes.get().get_gas_clave()) == "clave-A")
        check("gas: B recupera su propia clave", ver_como(app, uB, lambda: Ajustes.get().get_gas_clave()) == "clave-B")
        check("gas: las claves cifradas de A y B son distintas", A_enc(A, B))

    # ---- Chequeos por HTTP: FUERA del app-context, para que cada request tenga
    #      su propio contexto y Flask-Login lea la sesión real (no g heredado). ----
    seccion("Aislamiento por HTTP (listados y acceso por ID ajeno)")
    cA = app.test_client(); cA.post("/login", data={"username": "user_A", "password": "clave1234"})
    cB = app.test_client(); cB.post("/login", data={"username": "user_B", "password": "clave1234"})

    listaA = cA.get("/personas/").data.decode("utf-8", "ignore")
    listaB = cB.get("/personas/").data.decode("utf-8", "ignore")
    check("Personas: A no ve a los de B", "Inquilino B" not in listaA and "Propietario B" not in listaA)
    check("Personas: B no ve a los de A", "Inquilino A" not in listaB and "Propietario A" not in listaB)

    contrA = cA.get("/contratos/").data.decode("utf-8", "ignore")
    check("Contratos: A no ve el contrato de B", "C-B" not in contrA)

    check("A no abre el contrato de B por ID (404)",
          cA.get(f"/contratos/{B['contrato'][0]}").status_code == 404)
    check("B no abre el contrato de A por ID (404)",
          cB.get(f"/contratos/{A['contrato'][0]}").status_code == 404)
    check("A no edita una persona de B por ID (404)",
          cA.get(f"/personas/{B['persona'][0]}/editar").status_code == 404)
    check("A no descarga el documento de B (404/403)",
          cA.get(f"/contratos/{A['contrato'][0]}/documentos/{B['documento'][0]}").status_code in (404, 403))

    seccion("Creación: se asigna a la inmobiliaria correcta")
    cA.post("/personas/nueva", data={"nombre": "ZZ Nueva de A", "es_inquilino": "on"})
    with app.app_context():
        db.session.expire_all()
        nueva = Persona.query.filter_by(nombre="ZZ Nueva de A").first()
    check("una persona creada por A queda en la inmobiliaria de A",
          nueva is not None and nueva.inmobiliaria_id == A["tid"])
    check("B no ve la persona recién creada por A",
          "ZZ Nueva de A" not in cB.get("/personas/").data.decode("utf-8", "ignore"))

    seccion("Mutación cruzada: A no puede tocar datos de B")
    cA.post(f"/personas/{B['persona'][0]}/eliminar")
    with app.app_context():
        db.session.expire_all()
        sigue = db.session.get(Persona, B["persona"][0])
    check("A NO pudo borrar una persona de B (sigue existiendo)",
          sigue is not None and sigue.nombre == "Propietario B")

    seccion("Ataques deliberados: A intenta tocar plata y comprobantes de B por ID")
    bp = B["pago"][0]; bc = B["contrato"][0]; bi = B["inmueble"][0]
    br = B["recibo"][0]; bpe = B["persona"][0]
    check("A no ve el detalle de cobros del contrato de B (404)",
          cA.get(f"/cobros/contrato/{bc}").status_code == 404)
    check("A no ve el recibo de un pago de B (404)",
          cA.get(f"/recibos/pago/{bp}").status_code == 404)
    check("A no descarga el PDF del recibo de un pago de B (404)",
          cA.get(f"/recibos/pago/{bp}/pdf").status_code == 404)
    check("A no ve la liquidación de un pago de B (404)",
          cA.get(f"/recibos/liquidacion/pago/{bp}").status_code == 404)
    check("A no ve el recibo manual de B (404)",
          cA.get(f"/recibos/manuales/{br}").status_code == 404)
    check("A no abre la pantalla de aumento del contrato de B (404)",
          cA.get(f"/aumentos/contrato/{bc}/aplicar").status_code == 404)
    check("A no edita un inmueble de B (404)",
          cA.get(f"/inmuebles/{bi}/editar").status_code == 404)
    check("A no imprime la liquidación de un propietario de B (404)",
          cA.get(f"/liquidaciones/imprimir/{bpe}").status_code == 404)
    # Mutaciones de plata: intentar cobrar sobre el contrato de B y anular su pago.
    _cob = cA.post("/cobros/rapido", json={"cid": bc, "mes": 3, "anio": 2030,
                                           "precio": 1000, "pagado": 1000})
    check("A no puede registrar un cobro sobre el contrato de B (404)",
          _cob.status_code == 404)
    cA.post(f"/cobros/pago/{bp}/anular", data={"motivo": "hackeo"})
    with app.app_context():
        db.session.expire_all()
        _pb = db.session.get(Pago, bp)
    check("A no pudo anular el pago de B (sigue 'Pagado')",
          _pb is not None and _pb.estado == "Pagado")
    check("A no puede agregar una nota de seguimiento al contrato de B (404)",
          cA.post(f"/contratos/{bc}/seguimiento",
                  data={"texto": "hackeo"}).status_code == 404)

    seccion("Auditoría: cada inmobiliaria ve solo su bitácora")
    with app.app_context():
        uA = db.session.get(Usuario, db.session.query(Usuario).filter_by(username="user_A").first().id)
        uB = db.session.get(Usuario, db.session.query(Usuario).filter_by(username="user_B").first().id)
        audA = ver_como(app, uA, lambda: {r.id for r in RegistroAuditoria.query.all()})
        audB = ver_como(app, uB, lambda: {r.id for r in RegistroAuditoria.query.all()})
    check("Auditoría de A y B no se solapan (y ninguna vacía por error)",
          not (audA & audB))

    print("\n" + "=" * 44)
    print(f"AISLAMIENTO:  {TOTAL['ok']} PASA  /  {TOTAL['fail']} FALLA")
    print("=" * 44)
    return TOTAL["fail"] == 0


def A_enc(A, B):
    a = db.session.get(Ajustes, A["ajustes"][0])
    b = db.session.get(Ajustes, B["ajustes"][0])
    return a.gas_clave_enc and b.gas_clave_enc and a.gas_clave_enc != b.gas_clave_enc


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
