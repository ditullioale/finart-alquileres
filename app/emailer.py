"""Envío de emails (para recuperación de contraseña y avisos).

Usa SMTP si está configurado por variables de entorno; si no, deja el mensaje en
el log del servidor (útil en desarrollo). Nunca expone el contenido al navegador.

Variables de entorno:
  SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASS, EMAIL_FROM
"""
import os
import smtplib
from email.mime.text import MIMEText


def smtp_configurado():
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER")
                and os.environ.get("SMTP_PASS"))


def enviar_email(destino, asunto, cuerpo):
    """Devuelve True si se envió por SMTP; False si no hay SMTP (queda en log)."""
    remitente = os.environ.get("EMAIL_FROM") or os.environ.get("SMTP_USER")
    if not smtp_configurado() or not destino:
        print(f"[EMAIL sin SMTP] Para: {destino} | {asunto}\n{cuerpo}")
        return False
    try:
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
