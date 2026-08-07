"""Envío de emails (para recuperación de contraseña y avisos).

Usa SMTP si está configurado por variables de entorno; si no, deja el mensaje en
el log del servidor (útil en desarrollo). Nunca expone el contenido al navegador.

Variables de entorno:
  SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASS, EMAIL_FROM
"""
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def smtp_configurado():
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER")
                and os.environ.get("SMTP_PASS"))


def enviar_email(destino, asunto, cuerpo, adjunto=None):
    """Devuelve True si se envió por SMTP; False si no hay SMTP (queda en log).

    adjunto opcional: tupla (nombre_archivo, datos_bytes, mimetype) — p. ej. el PDF
    del recibo."""
    remitente = os.environ.get("EMAIL_FROM") or os.environ.get("SMTP_USER")
    if not smtp_configurado() or not destino:
        print(f"[EMAIL sin SMTP] Para: {destino} | {asunto}\n{cuerpo}")
        return False
    try:
        if adjunto:
            msg = MIMEMultipart()
            msg.attach(MIMEText(cuerpo, "plain", "utf-8"))
            nombre, datos, mime = adjunto
            subtipo = (mime or "application/octet-stream").split("/", 1)[-1]
            parte = MIMEApplication(datos, _subtype=subtipo)
            parte.add_header("Content-Disposition", "attachment", filename=nombre)
            msg.attach(parte)
        else:
            msg = MIMEText(cuerpo, "plain", "utf-8")
        msg["Subject"] = asunto
        msg["From"] = remitente
        msg["To"] = destino
        host = os.environ["SMTP_HOST"]
        port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls()
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            s.sendmail(remitente, [destino], msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL error] {e}")
        return False
