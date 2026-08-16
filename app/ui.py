"""Interruptor entre el diseño clásico y el nuevo (Aurora).

El diseño anterior no se toca: sus plantillas siguen donde estaban. Las nuevas
viven en ``app/templates/aurora/`` con la misma ruta relativa, y ``render_ui``
elige una u otra. Si una pantalla todavía no fue rediseñada, se sirve la
clásica sin que haya que hacer nada.

Prioridad para decidir el diseño:

1. ``?ui=nueva`` o ``?ui=clasica`` en la URL (queda recordado en una cookie).
2. La cookie ``ui`` (preferencia del usuario en ese navegador).
3. La variable de entorno ``UI`` (default de la instalación).

Volver atrás en producción es cambiar ``UI=clasica`` en el entorno; cada
usuario puede volver por su cuenta con el enlace del pie del menú.
"""
import os

from flask import current_app, render_template, request
from jinja2 import TemplateNotFound

COOKIE = "ui"
_VALIDAS = ("nueva", "clasica")


def _default() -> str:
    valor = (current_app.config.get("UI") or os.environ.get("UI") or "clasica").strip().lower()
    return valor if valor in _VALIDAS else "clasica"


def ui_elegida() -> str:
    """Diseño que corresponde a este pedido."""
    pedido = (request.args.get(COOKIE) or "").strip().lower()
    if pedido in _VALIDAS:
        return pedido
    cookie = (request.cookies.get(COOKIE) or "").strip().lower()
    if cookie in _VALIDAS:
        return cookie
    return _default()


def es_nueva() -> bool:
    return ui_elegida() == "nueva"


def plantilla(nombre: str) -> str:
    """Devuelve la plantilla nueva si existe y está activa; si no, la clásica."""
    if not es_nueva():
        return nombre
    candidata = f"aurora/{nombre}"
    try:
        current_app.jinja_env.get_template(candidata)
    except TemplateNotFound:
        return nombre
    return candidata


def render_ui(nombre: str, **ctx):
    return render_template(plantilla(nombre), **ctx)


def registrar(app):
    """Deja ``ui`` disponible en las plantillas y recuerda la elección."""

    @app.context_processor
    def _inject_ui():
        try:
            elegida = ui_elegida()
        except RuntimeError:  # fuera de un request (p. ej. CLI)
            elegida = "clasica"
        return {"ui": elegida, "ui_nueva": elegida == "nueva"}

    @app.after_request
    def _recordar_ui(resp):
        pedido = (request.args.get(COOKIE) or "").strip().lower()
        if pedido in _VALIDAS and request.cookies.get(COOKIE) != pedido:
            resp.set_cookie(COOKIE, pedido, max_age=60 * 60 * 24 * 365,
                            samesite="Lax", secure=request.is_secure)
        return resp
