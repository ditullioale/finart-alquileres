"""Punto de entrada para levantar la aplicación.

Uso:
    python run.py

Luego abrir http://localhost:5000 en el navegador.
Para acceso desde otras PC de la red, la app escucha en 0.0.0.0.
"""
from app import create_app, db
from app.models import Usuario

app = create_app()


@app.cli.command("init-db")
def init_db():
    """Crea las tablas y el usuario administrador inicial."""
    db.create_all()
    Usuario.crear_admin_inicial()
    print("Base de datos inicializada.")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        Usuario.crear_admin_inicial()

    print("=" * 56)
    print("  Gestión de Alquileres en marcha.")
    print("  En esta PC:        http://localhost:5000")
    print("  Desde otra PC:     http://IP-DE-ESTA-PC:5000")
    print("  (para saber la IP, abrí otra terminal y escribí: ipconfig)")
    print("=" * 56)

    # Servidor estable para varios usuarios (waitress). Si no está instalado,
    # usa el servidor propio de Flask (también sirve, pero es más básico).
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=5000, threads=8)
    except ImportError:
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
