"""Asistente de consulta (IA) sobre los datos de la inmobiliaria actual.

Diseño pensado para multiempresa y para no inventar datos:

- La IA **no toca la base directamente ni escribe SQL**. Elige entre un conjunto de
  funciones pre-armadas ("herramientas"), y la app las ejecuta.
- Cada herramienta usa los modelos normales (`Contrato.query`...), que ya están
  **filtrados por la inmobiliaria del usuario** (ver `app/tenant.py`). Una inmobiliaria
  nunca ve datos de otra, aunque lo pida.
- Es **solo lectura**: responde, no registra cobros ni cambia nada.

La clave de IA va por variable de entorno (`IA_API_KEY`), en el servidor. Modelo
configurable con `IA_MODEL`. Si no hay clave, el asistente avisa que no está configurado.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta

import requests

from . import calculos
from .models import Contrato
from .utils import MESES_ES

API_URL = "https://api.anthropic.com/v1/messages"
MODELO_DEFECTO = "claude-haiku-4-5-20251001"
MAX_VUELTAS = 6  # tope de llamadas a herramientas por pregunta (evita loops/costos)


def configurado() -> bool:
    return bool(os.environ.get("IA_API_KEY"))


# --------------------------------------------------------------------------- #
#  Herramientas: consultas seguras, filtradas por inmobiliaria (solo lectura)
# --------------------------------------------------------------------------- #
def _nombre_inq(c) -> str:
    try:
        if getattr(c, "locatarios_texto", None):
            return c.locatarios_texto
    except Exception:
        pass
    return c.inquilino.nombre if getattr(c, "inquilino", None) else "—"


def _dir_inm(c) -> str:
    inm = getattr(c, "inmueble", None)
    if not inm:
        return "—"
    cod = f"({inm.codigo}) " if getattr(inm, "codigo", None) else ""
    return f"{cod}{inm.direccion or ''}".strip() or "—"


def h_quien_debe(**_):
    """Inquilinos con deuda real (meses vencidos sin cobrar), de mayor a menor."""
    hoy = date.today()
    filas = []
    for c in Contrato.query.all():
        d = calculos.deuda_real(c, hoy)
        if d > 0:
            imp = calculos.periodos_impagos(c, hoy)
            filas.append({
                "inquilino": _nombre_inq(c),
                "inmueble": _dir_inm(c),
                "deuda": round(d, 2),
                "meses_adeudados": [f"{MESES_ES[p['mes']]} {p['anio']}" for p in imp],
            })
    filas.sort(key=lambda f: f["deuda"], reverse=True)
    return {"cantidad": len(filas), "deudores": filas}


def h_deuda_de(consulta: str = "", **_):
    """Deuda de un inquilino o inmueble concreto (búsqueda por nombre/dirección)."""
    hoy = date.today()
    q = (consulta or "").strip().lower()
    res = []
    for c in Contrato.query.all():
        if q and q not in _nombre_inq(c).lower() and q not in _dir_inm(c).lower():
            continue
        imp = calculos.periodos_impagos(c, hoy)
        res.append({
            "inquilino": _nombre_inq(c),
            "inmueble": _dir_inm(c),
            "deuda": round(calculos.deuda_real(c, hoy), 2),
            "meses_adeudados": [f"{MESES_ES[p['mes']]} {p['anio']}" for p in imp],
        })
    return {"resultados": res}


def h_vencimiento_contrato(consulta: str = "", **_):
    """Cuándo vence (fecha de fin) el/los contrato(s) de un inquilino o inmueble."""
    q = (consulta or "").strip().lower()
    res = []
    for c in Contrato.query.all():
        if q and q not in _nombre_inq(c).lower() and q not in _dir_inm(c).lower():
            continue
        res.append({
            "inquilino": _nombre_inq(c),
            "inmueble": _dir_inm(c),
            "inicio": c.fecha_inicio.isoformat() if c.fecha_inicio else None,
            "vence": c.fecha_fin.isoformat() if c.fecha_fin else "sin fecha de fin cargada",
        })
    return {"contratos": res}


def h_contratos_por_vencer(dias: int = 60, **_):
    """Contratos cuyo fin cae dentro de los próximos N días (default 60)."""
    hoy = date.today()
    try:
        limite = hoy + timedelta(days=int(dias))
    except (TypeError, ValueError):
        limite = hoy + timedelta(days=60)
    res = []
    for c in Contrato.query.all():
        if c.fecha_fin and hoy <= c.fecha_fin <= limite:
            res.append({
                "inquilino": _nombre_inq(c),
                "inmueble": _dir_inm(c),
                "vence": c.fecha_fin.isoformat(),
                "dias_restantes": (c.fecha_fin - hoy).days,
            })
    res.sort(key=lambda x: x["dias_restantes"])
    return {"cantidad": len(res), "contratos": res}


def h_cobros_del_periodo(mes: int | None = None, anio: int | None = None, **_):
    """Total cobrado en un período (mes/año). Sin datos usa el mes actual."""
    hoy = date.today()
    try:
        mes = int(mes) if mes else hoy.month
        anio = int(anio) if anio else hoy.year
    except (TypeError, ValueError):
        mes, anio = hoy.month, hoy.year
    total, cant = 0.0, 0
    for c in Contrato.query.all():
        p = calculos.pago_de_periodo(c, mes, anio)
        if p and (p.pagado or 0) > 0:
            total += float(p.pagado or 0)
            cant += 1
    return {"mes": MESES_ES[mes], "anio": anio,
            "total_cobrado": round(total, 2), "cantidad_de_pagos": cant}


def h_resumen_general(**_):
    """Panorama: contratos activos, deuda total y cuántos deben."""
    hoy = date.today()
    cs = Contrato.query.all()
    con_deuda = [c for c in cs if calculos.deuda_real(c, hoy) > 0]
    activos = [c for c in cs if not c.fecha_fin or c.fecha_fin >= hoy]
    deuda_total = round(sum(calculos.deuda_real(c, hoy) for c in cs), 2)
    return {"contratos_total": len(cs), "contratos_activos": len(activos),
            "inquilinos_con_deuda": len(con_deuda), "deuda_total": deuda_total}


# Registro: nombre -> (función, descripción, esquema de parámetros)
HERRAMIENTAS = {
    "quien_debe": (h_quien_debe,
                   "Lista los inquilinos con deuda (meses vencidos sin cobrar), de mayor a menor.",
                   {"type": "object", "properties": {}}),
    "deuda_de": (h_deuda_de,
                 "Deuda de un inquilino o inmueble concreto. Pasá el nombre o la dirección en 'consulta'.",
                 {"type": "object", "properties": {
                     "consulta": {"type": "string", "description": "Nombre del inquilino o dirección del inmueble"}}}),
    "vencimiento_contrato": (h_vencimiento_contrato,
                             "Cuándo vence (fin) el contrato de un inquilino o inmueble. Pasá el nombre/dirección en 'consulta'.",
                             {"type": "object", "properties": {
                                 "consulta": {"type": "string", "description": "Nombre del inquilino o dirección"}}}),
    "contratos_por_vencer": (h_contratos_por_vencer,
                             "Contratos que vencen dentro de los próximos N días.",
                             {"type": "object", "properties": {
                                 "dias": {"type": "integer", "description": "Ventana en días (default 60)"}}}),
    "cobros_del_periodo": (h_cobros_del_periodo,
                           "Total cobrado en un mes/año. Si no se indica, usa el mes actual.",
                           {"type": "object", "properties": {
                               "mes": {"type": "integer", "description": "Mes 1-12"},
                               "anio": {"type": "integer", "description": "Año, ej 2026"}}}),
    "resumen_general": (h_resumen_general,
                        "Panorama general: contratos activos, cuántos inquilinos deben y la deuda total.",
                        {"type": "object", "properties": {}}),
}


def _tools_payload():
    return [{"name": n, "description": d, "input_schema": s}
            for n, (_f, d, s) in HERRAMIENTAS.items()]


SISTEMA = (
    "Sos el asistente de una inmobiliaria dentro del sistema FINART. Respondés preguntas "
    "sobre alquileres, cobranzas y contratos usando SOLO las herramientas disponibles, que "
    "consultan los datos reales de ESTA inmobiliaria. No inventes datos: si una herramienta "
    "no trae resultados, decilo. Respondé en español rioplatense, breve y claro, con montos "
    "en pesos y fechas en formato día/mes/año. Si la pregunta no se puede responder con las "
    "herramientas, explicá qué sí podés consultar."
)


def preguntar(pregunta: str) -> dict:
    """Responde una pregunta en lenguaje natural. Devuelve {ok, respuesta} o {ok:False,error}.

    Ejecuta el loop de tool-use: la IA elige herramientas, la app las corre (filtradas por
    inmobiliaria) y la IA arma la respuesta final."""
    clave = os.environ.get("IA_API_KEY")
    if not clave:
        return {"ok": False, "error": "El asistente de IA no está configurado (falta IA_API_KEY)."}
    headers = {"x-api-key": clave, "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    modelo = os.environ.get("IA_MODEL", MODELO_DEFECTO)
    mensajes = [{"role": "user", "content": pregunta.strip()[:2000]}]
    for _ in range(MAX_VUELTAS):
        cuerpo = {"model": modelo, "max_tokens": 1024, "system": SISTEMA,
                  "tools": _tools_payload(), "messages": mensajes}
        try:
            r = requests.post(API_URL, headers=headers, json=cuerpo, timeout=40)
        except requests.RequestException as exc:
            return {"ok": False, "error": f"No se pudo contactar al servicio de IA: {exc}"}
        if r.status_code != 200:
            detalle = ""
            try:
                detalle = (r.json().get("error") or {}).get("message", "")
            except ValueError:
                detalle = r.text[:200]
            return {"ok": False,
                    "error": f"El servicio de IA respondió {r.status_code}"
                             + (f": {detalle}" if detalle else ".")}
        data = r.json()
        contenido = data.get("content", [])
        mensajes.append({"role": "assistant", "content": contenido})
        if data.get("stop_reason") != "tool_use":
            texto = "".join(b.get("text", "") for b in contenido if b.get("type") == "text")
            return {"ok": True, "respuesta": texto.strip() or "No tengo una respuesta."}
        # Ejecutar cada herramienta pedida y devolver los resultados.
        resultados = []
        for b in contenido:
            if b.get("type") != "tool_use":
                continue
            fn = HERRAMIENTAS.get(b.get("name"))
            try:
                salida = fn[0](**(b.get("input") or {})) if fn else {"error": "herramienta desconocida"}
            except Exception as exc:  # noqa: BLE001 - nunca romper por una herramienta
                salida = {"error": f"no se pudo consultar: {exc}"}
            resultados.append({"type": "tool_result", "tool_use_id": b.get("id"),
                               "content": json.dumps(salida, ensure_ascii=False, default=str)})
        mensajes.append({"role": "user", "content": resultados})
    return {"ok": False, "error": "La consulta fue demasiado compleja (muchos pasos). Probá reformularla."}
