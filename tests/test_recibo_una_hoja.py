"""El recibo (original + duplicado) tiene que entrar en UNA sola hoja A4, para
todos los casos realistas: con conceptos, observaciones y saldo parcial."""
import io
from datetime import date

import pytest
from app import db
from app.models import Persona, Inmueble, Contrato, Pago, GastoExtra
from app.blueprints.recibos import _recibo_pdf_bytes

pytest.importorskip("pypdf")
from pypdf import PdfReader  # noqa: E402


def _paginas(app, tag, conceptos=0, obs=False, parcial=False):
    with app.app_context():
        prop = Persona(nombre=f"Prop Hoja {tag}", dni=f"18{tag}", es_propietario=True)
        inq = Persona(nombre=f"Inquilino Apellido {tag}", dni=f"19{tag}", es_inquilino=True,
                      domicilio="Avenida Siempre Viva 1234 Piso 3 Depto B", localidad="Rosario")
        db.session.add_all([prop, inq]); db.session.commit()
        inm = Inmueble(direccion=f"Avenida Pellegrini 1234 Piso 5 Depto A {tag}", tipo="Depto",
                       propietario_id=prop.id); db.session.add(inm); db.session.commit()
        c = Contrato(inmueble_id=inm.id, inquilino_id=inq.id, propietario_id=prop.id,
                     fecha_inicio=date(2026, 1, 1), fecha_fin=date(2028, 1, 1),
                     precio_inicial=600000, precio_actual=600000, estado="Vigente",
                     metodo_ajuste="sin_ajuste"); db.session.add(c); db.session.commit()
        pg = Pago(contrato_id=c.id, numero=1, periodo_mes=10, periodo_anio=2026,
                  precio_alquiler=600000, total=680000,
                  pagado=(400000 if parcial else 680000), saldo=(280000 if parcial else 0),
                  estado=("Parcial" if parcial else "Pagado"), forma_pago="Transferencia",
                  fecha_pago=date(2026, 10, 8),
                  observaciones=("Pago en dos transferencias, el 5 y el 8 de octubre." if obs else None))
        pg.gastos = [GastoExtra(descripcion=f"Concepto numero {i+1} de ejemplo", monto=10000)
                     for i in range(conceptos)]
        db.session.add(pg); db.session.commit()
        datos, _ = _recibo_pdf_bytes(db.session.get(Pago, pg.id))
    return len(PdfReader(io.BytesIO(datos)).pages)


def test_recibo_simple_una_hoja(client):
    _, app, _ = client
    assert _paginas(app, "a") == 1


def test_recibo_con_conceptos_y_obs_una_hoja(client):
    _, app, _ = client
    assert _paginas(app, "b", conceptos=4, obs=True) == 1


def test_recibo_parcial_con_conceptos_una_hoja(client):
    _, app, _ = client
    assert _paginas(app, "c", conceptos=3, obs=True, parcial=True) == 1
