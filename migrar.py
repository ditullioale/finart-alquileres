"""Migración no destructiva: agrega la tabla de liquidaciones y las columnas
nuevas de ajustes, sin borrar los datos existentes.

Uso:
    python migrar.py
"""
from sqlalchemy import text

from app import create_app, db

ALTERS = [
    "ALTER TABLE ajustes ADD COLUMN IF NOT EXISTS liquidacion_prefijo VARCHAR(8) DEFAULT '0001'",
    "ALTER TABLE ajustes ADD COLUMN IF NOT EXISTS liquidacion_proximo INTEGER DEFAULT 1",
    "ALTER TABLE contratos ADD COLUMN IF NOT EXISTS documento_html TEXT",
    "ALTER TABLE contratos ADD COLUMN IF NOT EXISTS comision_pct NUMERIC(12,2)",
    "ALTER TABLE liquidaciones ADD COLUMN IF NOT EXISTS contrato_id INTEGER",
]
# Nota: la tabla pagares_manuales la crea db.create_all() automáticamente.

app = create_app()
with app.app_context():
    db.create_all()  # crea tablas nuevas (liquidaciones) sin tocar las existentes
    for sql in ALTERS:
        try:
            db.session.execute(text(sql))
            db.session.commit()
            print("OK:", sql)
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            print("Aviso (probablemente ya existía):", e)
    print("\nMigración completada.")
