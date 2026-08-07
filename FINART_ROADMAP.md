# FINART — Roadmap técnico (documento vivo)

> Norte a seguir. Se va marcando: ✅ hecho · 🟡 parcial · ⬜ pendiente.
> Última actualización: 2026-08-06.

**Principio rector:** Finart administra el negocio inmobiliario; el Facturador ARCA
administra lo fiscal. Ninguno absorbe responsabilidades del otro.

**Regla de oro:** no agregar complejidad antes de necesitarla; sí dejar listas las
interfaces que permitan escalar cuando haga falta.

---

## Fase 0 — Congelar la arquitectura
- ✅ 0.1 Límites de responsabilidad Finart / Facturador (documentado en `FINART_INTEGRACION_API.md`).
- ✅ 0.2 Contrato formal de integración (endpoints, auth, request/response, códigos HTTP, errores, idempotencia, timeouts — documentado; reintentos con backoff quedan para Fase 5.6).
- 🟡 0.3 Versionar API: Finart ya soporta prefijo versionado (`FACTURADOR_API_PREFIX`, default `/api`); falta que el Facturador exponga `/api/v1`.

## Fase 1 — Seguridad base
- ✅ 1.1 Política única de contraseñas (`validar_password`: mínimo 8, no solo números; usada en registro, restablecer, cambio y alta por admin).
- ✅ 1.2 Logout seguro (POST + CSRF).
- 🟡 1.3 Rate limiting (login ✅ por intentos; registro y recuperación ✅ por IP; APIs/integración ⬜).
- 🟡 1.4 Protección del registro (freno por IP ✅; verificación de email por enlace ✅; CAPTCHA/Turnstile ⬜, requiere cuenta Cloudflare).
- ✅ 1.5 Cabeceras de seguridad (CSP, HSTS en https, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy).
- 🟡 1.6 Secretos fuera de Git (revisar que `.env` esté en `.gitignore`; secretos ya rotados una vez).
- ⬜ 1.7 Rotación de secretos (tokens de integración, claves admin).
- ⬜ 1.8 2FA (primero superadmin, luego admins).

## Fase 2 — Multi-tenancy
- ✅ 2.1 Tenant como frontera (filtro automático por sesión, `with_loader_criteria`).
- ✅ 2.2 `inmobiliaria_id` en todas las entidades comerciales.
- ✅ 2.3 Tests de aislamiento (83 pruebas: listados, por ID, PDF, documentos, búsquedas).
- ✅ 2.4 Tests de escalamiento de privilegios (operador no crea usuarios; admin no puede crear ni ascender a superadmin; admin de A no edita usuarios de B; nadie salvo superadmin entra a la plataforma). Rol validado en el servidor.

## Fase 3 — Testing profesional
- ✅ 3.1 pytest como framework central (carpeta `tests/`; envuelve las 3 suites históricas + pruebas nativas; `pytest` corre todo).
- ✅ 3.2 Unit tests de dinero, mora, aumentos, comisiones y numeración (cubiertos en la suite QA).
- 🟡 3.3 Integración Finart → Facturador con doble de prueba (`test_facturador` + E2E mockeado); falta homologación real.
- ✅ 3.4 E2E completo (`tests/test_e2e.py`: contrato → cobro → liquidación → facturador mock → CAE guardado y visible).

## Fase 4 — CI/CD
- ✅ 4.1 GitHub Actions para Finart (corre las 3 suites en cada push/PR + ruff informativo).
- 🟡 4.2 CI independiente por repo (Finart ✅; Facturador ⬜).
- ⬜ 4.3 Pipeline de integración (levantar PostgreSQL + Finart + Facturador).
- ⬜ 4.4 Separar development / staging / production.

## Fase 5 — Contrato Finart ↔ Facturador
- ✅ 5.1 Identidad del emisor por token: el Facturador resuelve el emisor por el token (`emisor_actual`), la factura usa siempre el CUIT del token, y si Finart manda otro `emisor_cuit` lo **rechaza** (`EmisorInvalidoError`). Verificado en el repo del Facturador.
- 🟡 5.2 Autenticación servicio-a-servicio (Bearer del emisor + X-Admin-Token ✅; separar identidades formalmente ⬜).
- ⬜ 5.3 Credenciales de integración con rotación, revocación y último uso (repo Facturador).
- ✅ 5.4 Idempotency-Key (referencia_externa idempotente en el Facturador + header `Idempotency-Key` desde Finart).
- ✅ 5.5 Timeouts (`FACTURADOR_TIMEOUT`).
- ✅ 5.6 Reintentos controlados (solo transitorios: red/timeout/5xx, con backoff; nunca un 4xx fiscal).

## Fase 6 — Estado fiscal
- ✅ 6.1 Estado en Finart (cada liquidación guarda estado, CAE, número, tipo, vencimiento y PDF, con el mapeo real de `FacturaOut`).
- ✅ 6.2 Estado propio en el Facturador (mantiene `Factura.estado` y ahora expone `GET /api/integracion/liquidacion?referencia_externa=...` para consultarlo).
- ✅ 6.3 Reconciliación (acción "Reconciliar con el facturador": usa el endpoint directo del Facturador —con respaldo al listado— y actualiza las pendientes con su CAE).

## Fases 7–23 (pendientes, según prioridad del roadmap)
- ⬜ 7 Asincronía (job de facturación, cola, backoff, DLQ).
- ⬜ 8 Webhook/callback Facturador → Finart.
- ⬜ 9 Auditoría cross-system (correlation IDs) — nota: ya hay auditoría funcional interna.
- 🟡 10 Documentos (adjuntos de contrato ✅; storage externo S3/R2, URLs firmadas, versionado y hash ⬜).
- 🟡 11 Performance (índices por `inmobiliaria_id` ✅; paginación general, N+1, agregaciones, cache ⬜).
- 🟡 12 Observabilidad (health checks `/app-health`, `/database-health`, `/facturador-health` ✅; logging estructurado, error tracking y métricas ⬜).
- ⬜ 13 Modelo Persona multi-rol + Inmueble + Operación.
- ⬜ 14 CRM · ⬜ 15 Ventas · ⬜ 16 Dashboard · ⬜ 17 Automatización.
- ⬜ 18 SaaS/planes/billing · ⬜ 19 Superadmin avanzado (base ya existe en Plataforma).
- ⬜ 20 IA · ⬜ 21 Escalabilidad · ⬜ 22 Recuperación ante desastres · ⬜ 23 Compliance.

## Fase 24 — Calidad de producto
- ⬜ 24.1 Design system · ⬜ 24.2 Accesibilidad.
- ✅ 24.3 Responsive (desktop/tablet/móvil, tablas→tarjetas).
- 🟡 24.4 UX de errores comprensibles (arreglado `[object Object]` de CUIT; feedback al facturar y al traer ICL; falta barrer el resto).

---

## Hecho recientemente (changelog)
- **Fase 5 y 6 (lado Facturador):** nuevo endpoint `GET /api/integracion/liquidacion?referencia_externa=...` para reconciliación directa (repo `facturador-arca`, 55 pruebas verdes); confirmado que el 5.1 ya estaba bien (emisor por token, rechazo de `emisor_cuit` ajeno). Finart usa el endpoint directo con respaldo al listado.
- **Fase 5 y 6 (lado Finart):** Idempotency-Key en la emisión, reintentos controlados por tipo de error (solo transitorios, con backoff), reconciliación de pendientes contra el Facturador, y mapeo real de `FacturaOut` (corrige número/tipo/fecha que antes se adivinaban). El comprobante emitido se ve siempre en la liquidación.
- **Testing con pytest + E2E (Fase 3.1/3.4):** `pytest` corre todo (E2E del circuito completo + las 3 suites históricas, 306+ verificaciones). CI usa pytest.
- **Health checks (Fase 12):** `/app-health`, `/database-health` y `/facturador-health` públicos para monitoreo.
- **Contrato de integración (Fase 0):** documento formal `FINART_INTEGRACION_API.md` (responsabilidades, endpoints, auth, errores, idempotencia) + API del Facturador versionable desde Finart.
- **Verificación de email en el registro (Fase 1.4):** la solicitud no llega al superadmin hasta que el interesado confirma su email por enlace (con resguardo si no hay correo saliente configurado).
- **Escalamiento de privilegios (Fase 2.4):** rol validado en el servidor (un admin no puede fabricar un superadmin), + 6 pruebas negativas.
- **Seguridad base (Fase 1):** política única de contraseñas, logout POST+CSRF, cabeceras de seguridad, freno por IP en registro/recuperación.
- **CI (Fase 4.1):** GitHub Actions corriendo QA + aislamiento + facturador.
- **Estado fiscal (6.1) y reconciliación básica (6.3):** CAE guardado en la liquidación + bandeja de pendientes de facturar.
- **Errores de plata:** precio por período (aumentos con fecha), parseo es-AR, anulación de pagos con rastro.
- **UX (24.4):** feedback de facturación/ICL, `[object Object]` corregido, ficha de contrato con teléfono y deuda real.

## Próximo sugerido
Ya con acceso al repo del Facturador (`ditullioale/facturador-arca`), se puede cerrar lo
que quedó en amarillo de Fase 5/6 desde ese lado: exponer `GET /integracion/liquidacion/{referencia_externa}`
(reconciliación fina), endurecer 5.1 (que Finart no pueda forzar otro emisor) y versionar
a `/api/v1`. Alternativa 100% Finart: resto de **Fase 12** (logging estructurado + error
tracking) o **Fase 11** (paginación + N+1).
