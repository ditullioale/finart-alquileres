"""Mail de bienvenida al portal para un inquilino nuevo.

Se dispara SOLO cuando quien está cargando el contrato lo pide explícitamente
(el checkbox del alta manual en /contratos/nuevo, o del generador de
contratos) -- nunca automático, y solo se ofrece cuando el inquilino tiene
email cargado. Aun así, se manda como máximo una vez por persona: si ya tiene
``bienvenida_enviada_at`` cargado, no se reenvía aunque el checkbox esté
tildado (para no volver a mandarlo si aparece en otro contrato más adelante)."""
from datetime import datetime

from flask import render_template, url_for

from . import db
from .models import Ajustes


def enviar_bienvenida_inquilino(persona):
    """Intenta mandar el mail de bienvenida a esta persona.

    Devuelve una tupla (enviado: bool, motivo: str) -- motivo explica por qué
    no se mandó cuando enviado es False, para poder mostrarlo en un flash."""
    if not persona.es_inquilino:
        return False, "la persona no está marcada como inquilino"
    if not persona.email:
        return False, "no tiene un email cargado"
    if not persona.dni:
        # El login del portal es email + DNI: sin DNI cargado, la invitación
        # sería inútil (no podría entrar con lo que le decimos en el mail).
        return False, "no tiene DNI cargado (hace falta para el login del portal)"
    if persona.bienvenida_enviada_at:
        return False, "ya se le había mandado antes"

    a = Ajustes.get()
    portal_link = url_for("portal.acceder", _external=True)
    nombre = persona.nombre

    # El acceso al portal es email + DNI (decisión de Ale, con la salvedad de
    # que el DNI no es un dato secreto -- ver conversación del 2026-08-28).
    acceso_texto = "y tu contraseña es tu D.N.I."
    acceso_html = "y tu contraseña es tu D.N.I."

    texto = (
        f"Hola {nombre},\n\n"
        "¡Bienvenido/a a FINART! Nos alegra tenerte como parte de nuestra "
        "comunidad.\n\n"
        "Somos FINART, una inmobiliaria con más de 40 años en Arroyo Seco -- y "
        "también un Estudio Jurídico. Además de alquileres y ventas, "
        "asesoramos en derecho sucesorio, laboral, contractual y de familia.\n\n"
        "Estamos para acompañarte a lo largo de todo tu contrato. Para que "
        "tengas todo a mano armamos un portal donde vas a poder ver tus "
        "recibos de pago, el estado de tu contrato, tus próximos aumentos y "
        f"la cuenta de gas -- todo en un solo lugar. Entrás con tu email "
        f"({persona.email}) {acceso_texto}.\n\nPortal: {portal_link}\n\n"
        "Cualquier consulta, estamos a tu disposición.\n\n"
        "Saludos cordiales,\n"
        "Dr. Alejandro R. Di Tullio -- Abogado, Corredor Inmobiliario\n"
        "Dra. María M. Di Tullio -- Abogado\n\n"
        "P.D.: por tu seguridad, no compartas tu DNI de acceso con otras personas."
    )
    html = render_template(
        "email/bienvenida_inquilino.html", nombre=nombre, email=persona.email,
        portal_link=portal_link, logo_url=(a.logo_url or None),
        acceso_html=acceso_html)

    # Import diferido (como en portal.py/auth.py): así los tests pueden
    # monkeypatchear app.emailer.enviar_email y que surta efecto acá.
    from .emailer import enviar_email
    enviado = enviar_email(persona.email, "¡Bienvenido/a a FINART!", texto, html=html)
    if enviado:
        persona.bienvenida_enviada_at = datetime.utcnow()
        db.session.commit()
        return True, "enviado"
    return False, "el envío de mail falló (revisá la configuración de mail)"
