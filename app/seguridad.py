"""Seguridad transversal: política de contraseñas y cabeceras HTTP.

Un solo lugar para (1) validar contraseñas con la misma regla en todos los flujos
(registro, restablecer, cambio, alta por admin) y (2) agregar las cabeceras de
seguridad a cada respuesta. Así no hay reglas distintas repartidas por el código.
"""
from flask import request

# Regla única de contraseñas.
PASSWORD_MIN = 8


def validar_password(pw: str):
    """Devuelve un mensaje de error si la contraseña no cumple la política, o None
    si está bien. Regla: al menos PASSWORD_MIN caracteres y no puede ser solo
    números (evita '12345678')."""
    pw = pw or ""
    if len(pw) < PASSWORD_MIN:
        return f"La contraseña debe tener al menos {PASSWORD_MIN} caracteres."
    if pw.isdigit():
        return "La contraseña no puede ser solo números; combiná letras y números."
    return None


def _csp() -> str:
    """Content-Security-Policy. La app usa estilos y scripts en línea propios, por
    eso se permite 'unsafe-inline' para style/script del mismo origen; todo lo demás
    queda restringido al propio sitio (nada de terceros, ni frames externos)."""
    return "; ".join([
        "default-src 'self'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
        "img-src 'self' data:",
        "style-src 'self' 'unsafe-inline'",
        "script-src 'self' 'unsafe-inline'",
        "connect-src 'self'",
        "form-action 'self'",
    ])


def aplicar_headers_seguridad(app):
    """Agrega las cabeceras de seguridad a todas las respuestas."""

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy",
                                "geolocation=(), microphone=(), camera=()")
        resp.headers.setdefault("Content-Security-Policy", _csp())
        # HSTS solo sobre HTTPS (no romper el desarrollo local por HTTP).
        seguro = request.is_secure or \
            request.headers.get("X-Forwarded-Proto", "").lower() == "https"
        if seguro:
            resp.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains")
        return resp
