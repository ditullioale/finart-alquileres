"""Contenido de los mails automáticos (bienvenida y notificaciones al portal),
armado a partir de lo que cada inmobiliaria cargó en Ajustes.

Multi-tenant: si una inmobiliaria no cargó su propio texto, estos mails NO
deben mencionar a otra inmobiliaria ni mostrar su firma -- se arma un texto
genérico con el nombre de la inmobiliaria que sí tiene cargado (`Ajustes.nombre`,
que siempre existe). Cada inmobiliaria puede personalizar su "quiénes somos",
su firma y el pie del mail desde Ajustes → Mails automáticos.
"""


def bio_bienvenida(ajustes):
    """Párrafo de presentación para el mail de bienvenida al portal."""
    if ajustes.email_bio and ajustes.email_bio.strip():
        return ajustes.email_bio.strip()
    return (f"Somos {ajustes.nombre}. Estamos para acompañarte a lo largo de "
            "todo tu contrato.")


def firma(ajustes):
    """Firma de los mails, como texto (puede tener varios renglones)."""
    if ajustes.email_firma and ajustes.email_firma.strip():
        return ajustes.email_firma.strip()
    return f"El equipo de {ajustes.nombre}"


def firma_lineas(ajustes):
    """La firma como lista de líneas no vacías -- para las plantillas HTML,
    que muestran cada renglón en un <p> aparte."""
    return [linea for linea in firma(ajustes).splitlines() if linea.strip()]


def pie(ajustes):
    """Línea de pie de página del mail (nombre + localidad, o lo que la
    inmobiliaria haya cargado)."""
    if ajustes.email_pie and ajustes.email_pie.strip():
        return ajustes.email_pie.strip()
    partes = [p for p in (ajustes.nombre, ajustes.localidad) if p]
    return " — ".join(partes) if partes else ajustes.nombre
