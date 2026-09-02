"""Control de la mora diaria mal cargada en los contratos.

Contexto: un bug del parser (parse_num) interpretaba el punto como separador de
miles cuando había 3 decimales, así '0.300' se guardaba como 300 y '0.400' como
400 -- es decir, la mora quedaba multiplicada por 1000. Este script encuentra
los contratos con una mora diaria implausible y propone corregirla dividiéndola
por 1000 (300 -> 0,3 ; 400 -> 0,4).

Uso (con el venv del proyecto):

    # Solo listar (NO toca nada):
    .\\venv\\Scripts\\python.exe revisar_mora.py

    # Aplicar la corrección de verdad:
    .\\venv\\Scripts\\python.exe revisar_mora.py --aplicar

    # Cambiar el umbral de "sospechoso" (por defecto 5 %/día):
    .\\venv\\Scripts\\python.exe revisar_mora.py --umbral 5

Recorre TODAS las inmobiliarias (se corre fuera de un request, así el filtro
multiempresa no aplica). Por las dudas, hacé un respaldo de la base antes de
usar --aplicar.
"""
import argparse
from decimal import Decimal

from app import create_app, db
from app.models import Contrato


def _proponer(valor):
    """Devuelve (nuevo_valor, nota) o (None, motivo) si conviene revisarla a mano.

    El bug conocido multiplica por 1000, así que la corrección natural es /1000.
    Si tras dividir sigue quedando alto (>10), se marca para revisar a mano."""
    corregido = (Decimal(valor) / Decimal(1000)).quantize(Decimal("0.001"))
    corregido = corregido.normalize()
    if corregido <= 0:
        return None, "queda 0 o negativo"
    if corregido > 10:
        return None, "sigue alto tras /1000 (revisar a mano)"
    return corregido, "/1000"


def main():
    ap = argparse.ArgumentParser(description="Detecta y corrige mora mal cargada.")
    ap.add_argument("--aplicar", action="store_true",
                    help="Aplica la corrección. Sin esto, solo lista (dry-run).")
    ap.add_argument("--umbral", type=float, default=5.0,
                    help="Mora diaria (%%/día) por encima de la cual se considera "
                         "sospechosa. Por defecto 5.")
    args = ap.parse_args()

    app = create_app()
    with app.app_context():
        sospechosos = (Contrato.query
                       .filter(Contrato.mora_diaria_pct.isnot(None),
                               Contrato.mora_diaria_pct > args.umbral)
                       .order_by(Contrato.inmobiliaria_id, Contrato.id)
                       .all())

        if not sospechosos:
            print(f"No hay contratos con mora diaria > {args.umbral} %/día. "
                  "Todo en orden.")
            return

        modo = "APLICANDO CORRECCIÓN" if args.aplicar else "SOLO LISTADO (dry-run)"
        print(f"== Mora diaria sospechosa (> {args.umbral} %/día) — {modo} ==\n")
        print(f"{'ID':>5}  {'Inmob':>5}  {'Actual':>10}  {'Propuesto':>10}   Contrato")
        print("-" * 78)

        corregidos = a_mano = 0
        for c in sospechosos:
            actual = c.mora_diaria_pct
            nuevo, nota = _proponer(actual)
            inm = c.inmueble.direccion if c.inmueble else "(sin inmueble)"
            inq = c.inquilino.nombre if c.inquilino else "(sin inquilino)"
            etiqueta = f"{inm} — {inq}"
            if nuevo is None:
                a_mano += 1
                print(f"{c.id:>5}  {c.inmobiliaria_id or '-':>5}  {float(actual):>10.3f}  "
                      f"{'? ':>10}   {etiqueta}   ⚠ {nota}")
                continue
            print(f"{c.id:>5}  {c.inmobiliaria_id or '-':>5}  {float(actual):>10.3f}  "
                  f"{float(nuevo):>10.3f}   {etiqueta}   ({nota})")
            if args.aplicar:
                c.mora_diaria_pct = nuevo
                corregidos += 1

        print("-" * 78)
        if args.aplicar:
            db.session.commit()
            print(f"\nListo: {corregidos} contrato(s) corregido(s)."
                  + (f" {a_mano} quedaron para revisar a mano." if a_mano else ""))
        else:
            print(f"\n{len(sospechosos)} sospechoso(s). Nada se modificó (dry-run). "
                  "Volvé a correr con --aplicar para corregirlos."
                  + (f" {a_mano} habría que revisarlos a mano." if a_mano else ""))


if __name__ == "__main__":
    main()
