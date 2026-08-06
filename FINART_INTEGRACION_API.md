# Contrato de integración FINART ↔ Facturador ARCA (v1)

> Documento de la Fase 0 del roadmap ("congelar la arquitectura"). Describe el
> contrato **real y actual** entre Finart (el gestor) y el Facturador ARCA, más las
> reglas que ambos servicios se comprometen a respetar. Fuente de verdad del lado
> Finart: `app/facturador.py` y `app/blueprints/facturador_web.py`.
> Última actualización: 2026-08-06.

---

## 0.1 — Límites de responsabilidad

**Finart (gestión inmobiliaria)** es dueño de: personas, inmuebles, contratos,
alquileres, cobranzas, liquidaciones, comisiones y la relación con el cliente. Finart
**decide qué** hay que facturar y **cuándo**, y guarda el resultado fiscal asociado a
cada liquidación (estado, CAE, número, PDF).

**Facturador ARCA (servicio fiscal)** es dueño de: emisores, certificados y claves,
consulta de padrón, emisión de comprobantes, CAE, QR, PDF fiscal, comunicación con
ARCA y auditoría fiscal. El Facturador **decide cómo** se emite y es la fuente de
verdad de todo lo fiscal.

**Regla:** ninguno absorbe responsabilidades del otro. Finart nunca habla con ARCA
directo; el Facturador nunca conoce la lógica de negocio inmobiliaria. La frontera es
esta API.

```
Finart  ──HTTP (esta API)──▶  Facturador ARCA  ──▶  ARCA
```

---

## 0.3 — Versionado

- La API se versiona por **prefijo de ruta**: `/<prefijo>/...`. Hoy el prefijo es
  `/api`; el objetivo es `/api/v1`.
- Del lado Finart el prefijo es configurable con la variable `FACTURADOR_API_PREFIX`
  (por defecto `/api`). Cuando el Facturador exponga `/api/v1`, se cambia esa variable
  y Finart apunta a la nueva versión **sin tocar código** (ver `app/facturador.py`).
- Compromiso: un cambio que rompa el contrato exige una versión nueva (`/api/v2`); la
  anterior se mantiene hasta que Finart migre.

---

## 0.2 — Contrato formal

### Autenticación

| Quién llama | Cómo se autentica | Uso |
|---|---|---|
| Finart en nombre de una inmobiliaria | `Authorization: Bearer <token_emisor>` | Emitir/consultar comprobantes de esa inmobiliaria. El token del emisor se guarda **cifrado** en `Ajustes` de cada inmobiliaria. |
| Finart como administrador de la integración | `X-Admin-Token: <FACTURADOR_ADMIN_TOKEN>` | Alta/actualización de emisores (`/emisores`). |

Si la inmobiliaria no tiene emisor propio, Finart no manda token y el Facturador usa
su emisor por defecto (modo una sola empresa). **Pendiente (Fase 5.1):** la identidad
del emisor debe resolverla el token del lado servidor; nunca confiar ciegamente en el
`emisor_cuit` que manda Finart.

### Configuración (variables de entorno en Finart)

| Variable | Default | Para qué |
|---|---|---|
| `FACTURADOR_URL` | — (vacío = integración apagada) | Base del servicio. |
| `FACTURADOR_API_PREFIX` | `/api` | Prefijo versionado. |
| `FACTURADOR_ADMIN_TOKEN` | — | Token de administración para `/emisores`. |
| `FACTURADOR_CUIT` | — | CUIT autorizado a usar el emisor por defecto. |
| `FACTURADOR_TIMEOUT` | `20` | Timeout de cada request (segundos). |
| `FACTURA_CONCEPTO` | `HONORARIOS PROFESIONALES` | Descripción del concepto. |

### Endpoints (todos bajo el prefijo versionado)

| Método | Ruta | Auth | Para qué |
|---|---|---|---|
| POST | `/emisores` | X-Admin-Token | Alta/actualización del emisor de una inmobiliaria (cert, clave, punto de venta, modo ARCA). Devuelve `{token, emisor}`. |
| POST | `/integracion/liquidacion` | Bearer | Emitir la factura de honorarios de una liquidación. **(principal)** |
| POST | `/lotes` | Bearer | Subir un resumen bancario (multipart) y detectar transferencias. |
| GET | `/transferencias` | Bearer | Listar transferencias detectadas. |
| PATCH | `/transferencias/{id}` | Bearer | Editar una transferencia (p. ej. cargar CUIT, marcar ignorada). |
| POST | `/transferencias/{id}/facturar?confirmar=` | Bearer | Facturar una transferencia. |
| POST | `/transferencias/facturar` | Bearer | Facturar un lote de transferencias. |
| GET | `/facturas` | Bearer | Listar comprobantes emitidos. |
| GET | `/facturas/{id}/pdf` | Bearer | PDF del comprobante. |

### Operación principal: emitir honorarios de una liquidación

`POST /integracion/liquidacion`

Request (JSON):

```json
{
  "receptor_cuit": "27123456780",
  "importe": "42400.00",
  "fecha": "2026-08-06",
  "referencia_externa": "gestor:1:0001-00000001",
  "emisor_cuit": "20305903990",
  "concepto_descripcion": "HONORARIOS PROFESIONALES",
  "razon_social": "PEREZ SA",
  "domicilio": "Calle 1",
  "confirmar_bajo_minimo": false
}
```

Respuesta — el campo `estado` manda. Valores que Finart entiende:

| `estado` | Significado | Qué hace Finart |
|---|---|---|
| `emitida` | Se emitió. Trae `factura: {id, numero, tipo, cae, cae_vencimiento, fecha}` | Guarda CAE/número/PDF en la liquidación y avisa. |
| `requiere_confirmacion` | La comisión no supera el mínimo | Muestra el botón "Sí, facturar" (reenvía con `confirmar_bajo_minimo=true`). |
| `sin_cuit` | Falta el CUIT del receptor | Deja la liquidación en "pendientes de facturar". |
| `error` | Falló la emisión | Deja la liquidación en "pendientes de facturar" con el detalle. |
| `deshabilitado` | La integración no está configurada | No hace nada. |

Ejemplo de respuesta emitida:

```json
{
  "estado": "emitida",
  "factura": {
    "id": 5, "numero": "0001-00000001", "tipo": "C",
    "cae": "72608060000001", "cae_vencimiento": "2026-08-16", "fecha": "2026-08-06"
  }
}
```

### Códigos HTTP

- `200` — respuesta válida; Finart lee `estado`.
- `401` — token de administración rechazado (`/emisores`).
- `422` — datos inválidos (p. ej. CUIT mal). Finart lo trata como `error`.
- Otros `4xx/5xx` — Finart lo trata como `error` (mensaje genérico).
- El detalle de error viaja en `detail` (string). Finart lo muestra tal cual (nunca
  `[object Object]`).

### Idempotencia

- Cada liquidación lleva `referencia_externa = "gestor:{inmobiliaria_id}:{numero_liquidacion}"`,
  única por inmobiliaria y liquidación.
- **Compromiso del Facturador:** si llega dos veces la misma `referencia_externa`, no
  emite un segundo comprobante; devuelve el existente. Así un reintento o un doble clic
  no genera dos facturas.
- **Pendiente (Fase 5.4/6.3):** formalizar `Idempotency-Key` y la reconciliación
  (`FECompConsultar` antes de reintentar) para timeouts.

### Timeouts y reintentos

- Timeout por request: `FACTURADOR_TIMEOUT` (default 20 s).
- La integración es **best-effort**: ante una caída, Finart nunca lanza excepción a la
  vista; marca la liquidación como pendiente de facturar y ofrece reintento manual.
- **Pendiente (Fase 5.6):** reintentos automáticos con backoff, diferenciados por tipo
  de error. Nunca reintentar a ciegas una operación fiscal (primero consultar si ya se
  emitió).

### Estados fiscales (alineados con Fase 6)

Vocabulario común de estados: `PENDIENTE`, `EN_PROCESO`, `EMITIDA`, `ERROR`,
`REQUIERE_CONFIRMACION`, `CANCELADA`. Cada sistema mantiene su propia fuente de verdad;
Finart guarda el estado de la factura en cada liquidación y el Facturador guarda el
estado fiscal completo.

---

## Estado de este contrato

- ✅ Endpoints, auth, request/response y códigos HTTP: documentados y en uso.
- ✅ Idempotencia por `referencia_externa`: implementada.
- ✅ Timeouts: implementados.
- ✅ Prefijo versionable desde Finart (`FACTURADOR_API_PREFIX`).
- 🟡 Versionar el Facturador a `/api/v1`: pendiente del lado del Facturador.
- ⬜ `Idempotency-Key` formal, reintentos con backoff y reconciliación automática (Fase 5–6).
- ⬜ Validación de identidad del emisor 100% del lado servidor (Fase 5.1).
