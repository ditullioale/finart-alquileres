# Seguimiento FINART 2.0 — Roadmap de comercialización

Checklist tildable del roadmap. Estado: ✅ hecho · 🟡 parcial · ⬜ pendiente · 🔴 urgente

Última actualización: 26/08/2026

Leyenda de "Quién": **Claude** = lo hago yo en el código · **Ale** = acción tuya (GitHub, legales, comercial)

---

## Fase 0 · Contención y diagnóstico

- [ ] 🔴 Rotar secretos/credenciales expuestos (Litoral Gas, `GAS_IMPORT_TOKEN`, `SECRET_KEY`) — **Ale**
- [ ] 🔴 Repositorio en **privado** — **Ale**
- [x] ✅ `.env` fuera del repo (verificado: solo se trackea `.env.ejemplo`)
- [ ] ⬜ Revisar historial de Git por secretos antiguos — **Ale/Claude**
- [ ] ⬜ Separar ambientes producción / prueba / desarrollo — **Ale/Claude**
- [x] ✅ Inventario de módulos, rutas y modelos (lo conocemos a fondo)
- [x] ✅ Tablero de incidencias / tareas (lista de tareas del proyecto)

## Fase 1 · Estabilización funcional

- [x] ✅ Pruebas automatizadas de mora, pagos parciales, aumentos, liquidaciones y **redondeos** (56 tests)
- [x] ✅ Montos en **decimales exactos** (sin errores de centavos)
- [x] ✅ Validaciones de fechas, estados y saldos (contratos, cobros)
- [x] ✅ Reemplazar migraciones artesanales por **Alembic/Flask-Migrate**
- [x] ✅ Registrar errores y mejorar mensajes (logging estructurado con `X-Request-Id` + Sentry opcional; mensajes de error más claros)
- [ ] 🟡 Documentar flujo de cada módulo y reglas de negocio (README/MANUAL/roadmap al día; falta doc por módulo) — **Claude**

## Fase 2 · Núcleo multiempresa  ← **próximo bloque grande**

- [x] ✅ Documento de diseño (`DISENO_MULTIEMPRESA.md`)
- [x] ✅ Crear tabla `Inmobiliaria` y vincular `Usuario` (paso 1)
- [x] ✅ `inmobiliaria_id` en todas las entidades + migrar datos actuales a la inmobiliaria #1 (backfill probado)
- [x] ✅ Asignación automática de inmobiliaria al crear registros (Capa 2)
- [x] ✅ Filtro central de tenant en las consultas (Capa 1: cubre listados, búsquedas y accesos por ID)
- [x] ✅ Helper de acceso por ID con verificación de tenant (Capa 3, `get_or_404_tenant`)
- [x] ✅ Pruebas **negativas** de aislamiento (A no ve/abre datos de B; 7 tests en la batería QA)
- [x] ✅ Pasar `inmobiliaria_id` a NOT NULL (cierra el hueco de registros sin dueño)
- [ ] ⬜ FK a nivel base con convención de nombres (endurecimiento opcional) — **Claude**
- [x] 🟡 Config por inmobiliaria: logo, datos fiscales, mora, comisión, numeración (Ajustes por inmobiliaria ✅; falta nombre de remitente de email por tenant) — **Claude**
- [x] ✅ Rol **superadmin** de plataforma (`app/blueprints/plataforma.py` + guardia)

## Fase 3 · Producto mínimo vendible (PMV)

- [x] ✅ Onboarding de inmobiliaria (superadmin crea inmobiliaria + su primer admin)
- [x] ✅ Roles ampliados: solo lectura y contador (bloqueo de mutaciones) + superadmin de plataforma
- [x] ✅ **Auditoría** automática de altas, cambios y eliminaciones + pantalla admin (aislada por inmobiliaria)
- [x] ✅ Exportación completa **por inmobiliaria** (portabilidad / baja) — tenant-safe
- [x] 🟡 **Backups automáticos** diarios (GitHub Actions, dos bases) + **prueba de restauración** verificada ✅; falta la **copia externa** fuera del proveedor — **Claude/Ale** (ver `GUIA_BACKUPS.md`)
- [x] ✅ Dashboard de cartera/mora/vencimientos (existe; se afinará por tenant)
- [ ] ⬜ Documentos con identidad (logo/datos) de cada inmobiliaria — **Claude**
- [ ] ⬜ Términos, privacidad, soporte y proceso de baja/exportación — **Ale** (con asesor)

## Fase 4 · Piloto comercial

- [ ] ⬜ Incorporar 3–5 inmobiliarias piloto — **Ale**
- [ ] ⬜ Migrar datos reales con checklist — **Ale/Claude**
- [ ] ⬜ Medir errores, tiempos y frecuencia de uso — **Ale**
- [ ] ⬜ Definir planes y precio según evidencia — **Ale**

## Fase 5 · Escala inicial

- [ ] ⬜ Autoservicio de alta y usuarios — **Claude**
- [ ] ⬜ Facturación / suscripciones — **Claude/Ale**
- [ ] ⬜ Portal del propietario — **Claude**
- [ ] ⬜ Automatizaciones de avisos y comprobantes — **Claude**
- [ ] ⬜ Base de conocimiento y métricas de soporte — **Ale**

---

## Seguridad (sección 4.2 del roadmap) — controles antes de vender

- [x] ✅ Protección CSRF
- [x] ✅ Cookies HttpOnly / Secure / SameSite
- [x] ✅ Registro de intentos fallidos y límite de abuso (bloqueo de login)
- [x] ✅ Forzar cambio de contraseña por defecto
- [x] ✅ SECRET_KEY sin default débil
- [x] ✅ Recuperación de contraseña por email (flujo con token; requiere SMTP de Ale para enviar)
- [x] ✅ Roles ampliados (solo lectura / contador)
- [ ] 🟡 Validación de archivos y límites de carga (import Excel: falta límite) — **Claude**
- [x] ✅ Roles ampliados (solo lectura / contador / superadmin — ver Fase 3)
- [x] ✅ Auditoría (altas, cambios, eliminaciones)
- [x] ✅ Pruebas de aislamiento entre inmobiliarias (batería adversarial, 90+ pruebas)
- [x] ✅ Verificación en dos pasos (2FA) por email, opt-in por usuario
- [x] ✅ Dependencias sin CVEs conocidas (pip-audit) + tokens de servicio en tiempo constante
- [x] ✅ Certificados de ARCA cifrados en reposo (Fernet, `FACTURADOR_SECRET`)
- [ ] ⬜ Cifrado de backups y secretos gestionados por el proveedor — **Ale/Claude**

## Backups y continuidad (sección 4.3)

- [x] ✅ Respaldo descargable manual (existe)
- [x] ✅ Backup **automático** diario de PostgreSQL con retención (GitHub Actions, dos bases)
- [ ] ⬜ Copia fuera del proveedor principal (S3/R2) — **Ale**
- [x] ✅ Prueba **real** de restauración (verificada en el workflow, dump → restore en contenedor)
- [x] ✅ Exportación completa por inmobiliaria (tenant-safe)
- [ ] 🟡 Plan documentado de incidentes y recuperación (existe `GUIA_BACKUPS.md`; falta runbook corto de restore) — **Ale/Claude**

## Legales (sección 8) — con asesoramiento, antes de vender

- [ ] ⬜ Términos y condiciones del servicio — **Ale**
- [ ] ⬜ Política de privacidad y tratamiento de datos — **Ale**
- [ ] ⬜ Contrato de suscripción y niveles de soporte — **Ale**
- [ ] ⬜ Cláusulas de disponibilidad y limitación de responsabilidad — **Ale**
- [ ] ⬜ Régimen de propiedad, exportación y eliminación de datos — **Ale**
- [ ] ⬜ Aviso: la plataforma asiste la gestión, no reemplaza asesoría legal/contable — **Ale**

---

## Indicadores de "listo para vender" (sección 9)

| Indicador | Criterio | Estado |
|---|---|---|
| Errores críticos | 0 en cálculos o aislamiento | ✅ cálculos y aislamiento con pruebas |
| Cobertura de pruebas | dinero, fechas, permisos | ✅ dinero/fechas/permisos/aislamiento cubiertos |
| Restauración | backup restaurado en prueba | ✅ verificado en el workflow de backups |
| Onboarding | cliente piloto sin tocar código | 🟡 alta por superadmin lista; falta piloto real |
| Aislamiento | pruebas automáticas y manuales OK | ✅ batería adversarial verde |
| Soporte | incidencias clasificadas y medidas | ⬜ |
| Uso | pilotos usan semanalmente | ⬜ |
| Retención | pilotos quieren seguir | ⬜ |

---

## Próximos pasos acordados

1. 🔴 **Ale:** confirmar repo **privado** + rotación de secretos expuestos.
2. ✅ **Claude:** multiempresa completa (aislamiento + superadmin + onboarding), auditoría, backups automáticos con restore verificado, ARCA en producción, asistente IA.
3. ⬜ **Ale (comercial/legal):** términos y privacidad, planes/precio, y sumar 1 inmobiliaria **piloto**.
4. ⬜ **Siguiente técnico:** copia de backups **fuera del proveedor** (S3/R2) + runbook de restore; remitente de email por inmobiliaria; paginación/N+1 (Fase 11).
