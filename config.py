"""Configuración de la aplicación.

Por defecto usa SQLite (no requiere instalar nada). Para uso multiusuario en red
con PostgreSQL, completar el archivo .env (ver .env.ejemplo) con los datos de
conexión. No hace falta editar este archivo.
"""
import os
import secrets
from pathlib import Path
from urllib.parse import quote_plus

try:
    from dotenv import load_dotenv
    load_dotenv()  # carga variables desde un archivo .env si existe
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent


def _database_uri():
    """Elige la base: PostgreSQL si está configurado, si no SQLite local."""
    # 1) URL completa explícita (avanzado).
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    # 2) Datos de PostgreSQL por partes (recomendado; evita problemas con
    #    contraseñas que tengan caracteres especiales).
    pg_db = os.environ.get("PG_DB")
    pg_pass = os.environ.get("PG_PASSWORD")
    if pg_db and pg_pass is not None:
        user = os.environ.get("PG_USER", "postgres")
        host = os.environ.get("PG_HOST", "localhost")
        port = os.environ.get("PG_PORT", "5432")
        return (f"postgresql+psycopg2://{user}:{quote_plus(pg_pass)}"
                f"@{host}:{port}/{pg_db}")
    # 3) SQLite local por defecto.
    return f"sqlite:///{_default_sqlite_path()}"


def _carpeta_datos():
    """Carpeta de datos local, FUERA de OneDrive.

    OneDrive puede bloquear o corromper archivos SQLite al sincronizarlos, por
    eso los datos se guardan por defecto en el directorio local del usuario
    (en Windows: %LOCALAPPDATA%\\GestionAlquileres).
    """
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    carpeta = Path(base) / "GestionAlquileres"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _default_sqlite_path():
    return _carpeta_datos() / "alquileres.db"


def _clave_secreta():
    """Clave de firma de sesiones y tokens CSRF.

    Debe ser la misma en todos los procesos y entre reinicios: con varios
    workers de gunicorn, una clave por proceso hace que las sesiones y los
    tokens CSRF fallen de forma intermitente según qué worker atienda el
    pedido. Si no está definida en el entorno se usa una clave generada una
    sola vez y guardada en la carpeta de datos local.
    """
    clave = os.environ.get("SECRET_KEY")
    if clave:
        return clave

    archivo = _carpeta_datos() / "secret_key"
    try:
        guardada = archivo.read_text().strip()
        if guardada:
            return guardada
    except OSError:
        pass

    nueva = secrets.token_hex(32)
    try:
        archivo.write_text(nueva)
        os.chmod(archivo, 0o600)
        print(f"AVISO: SECRET_KEY no está definida; generé una y la guardé en "
              f"{archivo}. Definí SECRET_KEY en las variables de entorno.")
    except OSError:
        print("AVISO: SECRET_KEY no está definida y no pude guardar una clave "
              "persistente. Las sesiones se van a cortar en cada reinicio y "
              "entre workers. Definí SECRET_KEY en las variables de entorno.")
    return nueva


class Config:
    # Clave secreta de sesión. Ideal: definir la variable SECRET_KEY en el entorno
    # (Railway). Si no está, se usa una generada y guardada en la carpeta de datos.
    SECRET_KEY = _clave_secreta()

    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Límite de subida de archivos (documentación de contratos): 10 MB por request.
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024

    # --- Endurecimiento de la sesión (cookies) ---
    # La cookie de sesión no es accesible por JavaScript (mitiga robo por XSS).
    SESSION_COOKIE_HTTPONLY = True
    # Solo se envía en navegaciones del mismo sitio (mitiga CSRF).
    SESSION_COOKIE_SAMESITE = "Lax"
    # Solo viaja por HTTPS. Activada por defecto (Railway usa HTTPS). Para probar
    # localmente por HTTP sin quedar afuera, definí COOKIE_SECURE=0 en el entorno.
    SESSION_COOKIE_SECURE = (os.environ.get("COOKIE_SECURE", "1") == "1"
                             and not os.environ.get("TESTING"))
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    # La sesión dura hasta 12 horas de inactividad.
    from datetime import timedelta as _td
    PERMANENT_SESSION_LIFETIME = _td(hours=12)

    APP_VERSION = "1.0.0"

    # Datos de la inmobiliaria (se usan en recibos y liquidaciones).
    INMOBILIARIA_NOMBRE = os.environ.get("INMOBILIARIA_NOMBRE", "Mi Inmobiliaria")
    INMOBILIARIA_CUIT = os.environ.get("INMOBILIARIA_CUIT", "")
    INMOBILIARIA_DIRECCION = os.environ.get("INMOBILIARIA_DIRECCION", "")
    INMOBILIARIA_LOCALIDAD = os.environ.get("INMOBILIARIA_LOCALIDAD", "")
    INMOBILIARIA_TELEFONO = os.environ.get("INMOBILIARIA_TELEFONO", "")
