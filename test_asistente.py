"""Pruebas del Asistente IA (herramientas de consulta).

Verifica que las herramientas:
  1. Traen la deuda real correcta.
  2. Respetan el aislamiento por inmobiliaria (A no ve datos de B).
  3. `preguntar()` avisa cuando no hay clave de IA configurada.

Uso:  python test_asistente.py
"""
import os
import tempfile
from datetime import date

_DBFILE = os.path.join(tempfile.gettempdir(), "finart_asistente_test.db")
if os.path.exists(_DBFILE):
    os.remove(_DBFILE)
os.environ["DATABASE_URL"] = "sqlite:///" + _DBFILE
os.environ["SECRET_KEY"] = "clave-de-prueba-asistente"
os.environ.pop("IA_API_KEY", None)   # asegurar que NO haya clave para el test del path sin clave

from flask import g
from app import create_app, db, asistente
from app.models import Inmobiliaria, Usuario, Persona, Inmueble, Contrato
from app.utils import add_months

TOTAL = {"ok": 0, "fail": 0}


def check(desc, cond):
    print(("  PASA  " if cond else "  FALLA ") + desc)
    TOTAL["ok" if cond else "fail"] += 1


def sembrar(sufijo, precio):
    """Inmobiliaria con un contrato que arranca hace 4 meses y sin pagos (deuda real)."""
    inmo = Inmobiliaria(nombre=f"Inmo {sufijo}", slug=sufijo)
    db.session.add(inmo); db.session.flush()
    tid = inmo.id
    prop = Persona(nombre=f"Prop {sufijo}", es_propietario=True, inmobiliaria_id=tid)
    inq = Persona(nombre=f"Inquilino {sufijo}", es_inquilino=True, inmobiliaria_id=tid)
    db.session.add_all([prop, inq]); db.session.flush()
    inm = Inmueble(codigo=f"INM-{sufijo}", direccion=f"Calle {sufijo} 123",
                   propietario_id=prop.id, inmobiliaria_id=tid)
    db.session.add(inm); db.session.flush()
    inicio = add_months(date.today(), -4)
    c = Contrato(inmueble_id=inm.id, inquilino_id=inq.id, propietario_id=prop.id,
                 fecha_inicio=inicio, fecha_fin=add_months(date.today(), 8),
                 precio_actual=precio, precio_inicial=precio, dia_vencimiento=10,
                 metodo_ajuste="sin_ajuste", numero=f"C-{sufijo}", inmobiliaria_id=tid)
    db.session.add(c); db.session.flush()
    u = Usuario(username=f"user_{sufijo}", rol="admin", activo=True,
                must_change_password=False, inmobiliaria_id=tid)
    u.set_password("clave1234")
    db.session.add(u); db.session.commit()
    return {"tid": tid, "user": u, "inq": f"Inquilino {sufijo}"}


def como(app, user, fn):
    with app.test_request_context():
        g._login_user = user
        try:
            return fn()
        finally:
            g.pop("_login_user", None)


def main():
    app = create_app()
    with app.app_context():
        db.create_all()
        A = sembrar("A", 100000)
        B = sembrar("B", 50000)

        print("\n== Deuda y aislamiento ==")
        rA = como(app, A["user"], asistente.h_quien_debe)
        nombres_A = [d["inquilino"] for d in rA["deudores"]]
        check("A ve a su propio inquilino como deudor", A["inq"] in nombres_A)
        check("A NO ve al inquilino de B", B["inq"] not in nombres_A)
        # 4 meses de deuda a 100.000 => ~300.000-400.000 (según el día del mes)
        deuda_A = rA["deudores"][0]["deuda"] if rA["deudores"] else 0
        check(f"la deuda de A es coherente (>0, fue {deuda_A})", deuda_A > 0)

        rB = como(app, B["user"], asistente.h_quien_debe)
        nombres_B = [d["inquilino"] for d in rB["deudores"]]
        check("B ve a su propio inquilino", B["inq"] in nombres_B)
        check("B NO ve al inquilino de A", A["inq"] not in nombres_B)

        # resumen general filtrado
        resu = como(app, A["user"], asistente.h_resumen_general)
        check("resumen de A cuenta 1 contrato (no los de B)", resu["contratos_total"] == 1)

        # vencimiento
        venc = como(app, A["user"], lambda: asistente.h_vencimiento_contrato(consulta="Inquilino A"))
        check("vencimiento trae el contrato de A por nombre", len(venc["contratos"]) == 1)

        print("\n== Sin clave de IA ==")
        r = como(app, A["user"], lambda: asistente.preguntar("¿quién debe?"))
        check("preguntar() avisa que falta IA_API_KEY", (not r["ok"]) and "IA_API_KEY" in r["error"])

    print("\n" + "=" * 44)
    print(f"ASISTENTE:  {TOTAL['ok']} PASA  /  {TOTAL['fail']} FALLA")
    print("=" * 44)
    return 0 if TOTAL["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
