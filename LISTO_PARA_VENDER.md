# FINART — Checklist "listo para vender"

> Lo imprescindible antes del primer cliente pago. ✅ hecho · 🟡 parcial · ⬜ falta.
> Última actualización: 2026-08-11.

---

## Pilar 1 — Integridad fiscal probada (riesgo #1)

El circuito Finart → Facturador → ARCA → CAE → Finart tiene que ser a prueba de errores.

- ✅ Identidad del emisor derivada del token (Finart no elige el CUIT).
- ✅ Consulta por `referencia_externa` (endpoint directo + respaldo).
- ✅ Idempotencia (`referencia_externa` en el Facturador + `Idempotency-Key`).
- ✅ Reintentos controlados (solo transitorios; nunca un 4xx fiscal).
- ✅ Reconciliación automática ante timeouts (cron corriendo).
- ✅ Sin doble facturación (garantizado por idempotencia).
- ✅ Test E2E del escenario completo (con Facturador mockeado).
- ✅ **Emisión REAL en producción de ARCA** (11/08/2026) — certificado de producción cargado, punto de venta Web Services (7), **CAE válido** emitido y verificable en "Mis Comprobantes". Superados mock y homologación.
- ✅ Handshake SSL con ARCA producción (`DH_KEY_TOO_SMALL`) resuelto; condición de IVA real del receptor; re-emisión de comprobantes de prueba → producción (liquidaciones y transferencias).
- 🟡 **Vencimiento del certificado de ARCA**: caducan (~1–2 años) y al vencer la facturación se corta **sin aviso**. `GET /api/emisores/diagnostico` (header `X-Admin-Token`) informa los días restantes por emisor (avisa a 30 días). ← engancharlo al monitor de uptime.
- ⬜ CI de integración real (Postgres + Finart + Facturador juntos).

## Pilar 2 — Aislamiento entre inmobiliarias, probado con ataques (riesgo #2)

Que A no pueda ver ni tocar NADA de B, ni siquiera a propósito.

- ✅ Filtro automático por inmobiliaria (todas las consultas).
- ✅ `inmobiliaria_id` en todas las entidades.
- ✅ 83 pruebas de aislamiento (listados, por ID, PDF, documentos, búsquedas).
- ✅ Escalamiento de privilegios (operador→admin, admin→superadmin bloqueados).
- ✅ **Batería adversarial explícita** (10 pruebas nuevas): A no puede, por ID ni por API, ver el detalle de cobros, recibos, PDF, liquidaciones ni recibos manuales de B; no puede abrir el aumento ni editar un inmueble de B; no puede registrar un cobro sobre el contrato de B ni anular su pago. Todo 404 y sin alterar datos ajenos. Aislamiento total: 93 pruebas.

## Pilar 3 — Producción confiable y recuperable (riesgo #3)

Que el servicio no se caiga sin aviso y que se pueda recuperar de un desastre.

- ✅ HTTPS (Railway).
- ✅ Health checks (`/app-health`, `/database-health`, `/facturador-health`).
- ✅ CI (corre las pruebas en cada push).
- ✅ Logging estructurado con id de correlación (`X-Request-Id`) por request.
- ✅ Monitoreo de errores con Sentry (se activa con la variable `SENTRY_DSN`). ← falta que cargues el DSN en Railway.
- ⬜ **Backups automáticos de la base + un restore probado** (un backup que nunca restauraste no es un backup). ← acción tuya en Railway.
- ⬜ Aviso/alerta si Finart o el Facturador se caen (uptime monitor sobre los health checks) **y aviso de vencimiento del certificado de ARCA** (`/api/emisores/diagnostico`).
- ⬜ Entorno de **staging** separado (probar sin tocar producción).
- ⬜ Rotación de secretos.

## Pilar 4 — Legal / comercial (silencioso, pero bloqueante)

No es código, pero vender sin esto es un riesgo real.

- ⬜ Términos y condiciones.
- ⬜ Política de privacidad (manejás datos fiscales de terceros).
- ⬜ Claridad de responsabilidad (qué pasa si ARCA rechaza algo).
- ⬜ Cómo se cobra (planes / suscripción / facturación).

---

## Por dónde empezar

1. ✅ **Hecho:** Pilar 1 — emisión real en producción de ARCA (CAE válido, 11/08/2026).
2. ✅ **Hecho:** Pilar 2 — aislamiento entre inmobiliarias (93 pruebas).
3. ✅ **Hecho:** Pilar 3 (parcial) — logging + Sentry (queda cargar `SENTRY_DSN`).
4. **Siguiente (Pilar 3, acción tuya con guía):** (a) backups del Postgres + un **restore probado** (`GUIA_BACKUPS.md`); (b) **uptime monitor** sobre los health checks + aviso de vencimiento del certificado (`/api/emisores/diagnostico`); (c) **staging** separado.
5. **Antes de cobrarle a otras inmobiliarias (Pilar 4):** términos, privacidad, responsabilidad y forma de cobro (con contador/abogado).
