"""Envío de emails (recuperación de contraseña, verificación de registro, recibos).

Dos formas de envío, en este orden de preferencia:
  1. API HTTP de Brevo (recomendado en la nube): usa HTTPS (puerto 443), que no
     bloquean los hostings como Railway. Se activa con BREVO_API_KEY.
  2. SMTP clásico (SMTP_HOST/PORT/USER/PASS): muchos hostings bloquean los puertos
     SMTP (587/465/2525), así que puede dar timeout en la nube.
Si no hay ninguna configurada, deja el mensaje en el log del servidor (desarrollo).

Variables de entorno:
  BREVO_API_KEY           -> clave de API de Brevo (xkeysib-...). Preferida.
  EMAIL_FROM              -> remitente (debe estar verificado en Brevo).
  EMAIL_FROM_NAME         -> nombre visible del remitente (opcional).
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS  -> alternativa por SMTP.
"""
import base64
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _brevo_api_key():
    return os.environ.get("BREVO_API_KEY")


def smtp_configurado():
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER")
                and os.environ.get("SMTP_PASS"))


def email_disponible():
    """True si hay alguna vía de envío configurada (Brevo o SMTP). Se usa para no
    ofrecer/forzar el 2FA por email cuando el servidor no puede mandar correos."""
    return bool(_brevo_api_key()) or smtp_configurado()


def enviar_email(destino, asunto, cuerpo, adjunto=None):
    """Devuelve True si se envió; False si no (queda en el log).

    adjunto opcional: tupla (nombre_archivo, datos_bytes, mimetype) — p. ej. el PDF
    del recibo."""
    remitente = os.environ.get("EMAIL_FROM") or os.environ.get("SMTP_USER")
    if not destino:
        print(f"[EMAIL sin destino] {asunto}")
        return False
    # 1) API HTTP de Brevo (recomendada: no depende de puertos SMTP).
    if _brevo_api_key():
        return _enviar_por_brevo_api(remitente, destino, asunto, cuerpo, adjunto)
    # 2) SMTP clásico.
    if not smtp_configurado():
        print(f"[EMAIL sin SMTP] Para: {destino} | {asunto}\n{cuerpo}")
        return False
    return _enviar_por_smtp(remitente, destino, asunto, cuerpo, adjunto)


def _enviar_por_brevo_api(remitente, destino, asunto, cuerpo, adjunto):
    import requests
    sender = {"email": remitente}
    nombre_remitente = os.environ.get("EMAIL_FROM_NAME")
    if nombre_remitente:
        sender["name"] = nombre_remitente
    payload = {
        "sender": sender,
        "to": [{"email": destino}],
        "subject": asunto,
        "textContent": cuerpo,
    }
    if adjunto:
        nombre, datos, _mime = adjunto
        payload["attachment"] = [{
            "name": nombre,
            "content": base64.b64encode(datos).decode("ascii"),
        }]
    try:
        r = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers={"api-key": _brevo_api_key(), "Content-Type": "application/json"},
            timeout=20,
        )
        if r.status_code in (200, 201):
            return True
        print(f"[EMAIL brevo-api error] {r.status_code} {r.text[:300]}")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"[EMAIL brevo-api excepcion] {e}")
        return False


def _enviar_por_smtp(remitente, destino, asunto, cuerpo, adjunto):
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
    except Exception as e:  # noqa: BLE001
        print(f"[EMAIL error] {e}")
        return False
