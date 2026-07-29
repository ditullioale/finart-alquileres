"""Cifrado simétrico para secretos guardados en la base (p. ej. la contraseña
de Litoral Gas de cada inmobiliaria). Usa Fernet con una clave derivada de
SECRET_KEY, así no hace falta configurar otra variable de entorno.

Nota: el cifrado protege la clave en la base. Quien controla el servidor (y por
lo tanto SECRET_KEY) técnicamente puede descifrarla; es el modelo estándar de un
SaaS autohosteado. Nunca se muestra la contraseña en pantalla."""
import base64
import hashlib

from flask import current_app


def _fernet():
    from cryptography.fernet import Fernet
    secret = (current_app.config.get("SECRET_KEY") or "clave-insegura").encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def cifrar(texto):
    """Devuelve el texto cifrado (str) o None si no hay nada que cifrar."""
    if not texto:
        return None
    return _fernet().encrypt(texto.encode("utf-8")).decode("ascii")


def descifrar(token):
    """Devuelve el texto original o None si no se puede (clave cambiada, etc.)."""
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except Exception:
        return None
