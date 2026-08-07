# FINART — Checklist "listo para vender"

> Lo imprescindible antes del primer cliente pago. ✅ hecho · 🟡 parcial · ⬜ falta.
> Última actualización: 2026-08-07.

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
- ⬜ **Emitir al menos 1 comprobante REAL en homologación de ARCA** (hoy todo es `mock`). ← acción tuya (certificados + alta en ARCA homologación).
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
- ⬜ Aviso/alerta si Finart o el Facturador se caen (uptime monitor sobre los health checks).
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

1. ✅ **Hecho:** Pilar 2 — batería adversarial de aislamiento (93 pruebas de aislamiento).
2. ✅ **Hecho:** Pilar 3 — logging estructurado + Sentry (queda que cargues el `SENTRY_DSN`).
3. **Acción tuya, con guía (Pilar 3):** activar backups del Postgres y probar el restore → ver `GUIA_BACKUPS.md`.
4. **Acción tuya, con guía (Pilar 1):** emitir un CAE real en homologación de ARCA → ver `GUIA_HOMOLOGACION_ARCA.md` (en el repo del Facturador). ⚠️ Lo que emitiste hasta ahora fue en modo `mock` = CAE simulado, sin validez fiscal.
5. **Antes de cobrar (Pilar 4):** lo legal (con un contador/abogado).
