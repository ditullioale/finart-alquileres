"""Configuración de la aplicación.

Por defecto usa SQLite (no requiere instalar nada). Para uso multiusuario en red
con PostgreSQL, completar el archivo .env (ver .env.ejemplo) con los datos de
conexión. No hace falta editar este archivo.
"""
import os
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


def _default_sqlite_path():
    """Ubica la base SQLite en una carpeta local, FUERA de OneDrive.

    OneDrive puede bloquear o corromper archivos SQLite al sincronizarlos, por
    eso la base se guarda por defecto en el directorio de datos local del
    usuario (en Windows: %LOCALAPPDATA%\\GestionAlquileres).
    """
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    carpeta = Path(base) / "GestionAlquileres"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta / "alquileres.db"


class Config:
    # Clave secreta de sesión. Ideal: definir la variable SECRET_KEY en el entorno
    # (Railway). Si no está, se genera una aleatoria fuerte para no dejar una débil
    # por defecto (las sesiones se reinician en cada arranque hasta que la definas).
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        import secrets
        SECRET_KEY = secrets.token_hex(32)
        print("AVISO: SECRET_KEY no está definida; usé una aleatoria. "
              "Definí SECRET_KEY en las variables de entorno para sesiones estables.")

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
