# Seguimiento FINART 2.0 — Roadmap de comercialización

Checklist tildable del roadmap. Estado: ✅ hecho · 🟡 parcial · ⬜ pendiente · 🔴 urgente

Última actualización: 28/07/2026

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
- [ ] 🟡 Registrar errores y mejorar mensajes (hay flashes; falta logging/monitoreo) — **Claude**
- [ ] ⬜ Documentar flujo de cada módulo y reglas de negocio — **Claude**

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
- [ ] ⬜ Config por inmobiliaria: logo, datos fiscales, mora, comisión, numeración — **Claude**
- [ ] ⬜ Rol **superadmin** de plataforma — **Claude**

## Fase 3 · Producto mínimo vendible (PMV)

- [x] ✅ Onboarding de inmobiliaria (superadmin crea inmobiliaria + su primer admin)
- [x] ✅ Roles ampliados: solo lectura y contador (bloqueo de mutaciones) + superadmin de plataforma
- [x] ✅ **Auditoría** automática de altas, cambios y eliminaciones + pantalla admin (aislada por inmobiliaria)
- [x] ✅ Exportación completa **por inmobiliaria** (portabilidad / baja) — tenant-safe
- [ ] 🟡 **Backups automáticos** diarios + copia externa + prueba de restauración — **Ale** (hosting; ver `BACKUPS.md`)
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
- [ ] ⬜ Roles ampliados (ver Fase 3)
- [x] ✅ Auditoría (altas, cambios, eliminaciones)
- [ ] ⬜ Pruebas de aislamiento entre inmobiliarias (ver Fase 2)
- [ ] ⬜ Cifrado de backups y secretos gestionados por el proveedor — **Ale/Claude**

## Backups y continuidad (sección 4.3)

- [x] 🟡 Respaldo descargable manual (existe)
- [ ] ⬜ Backup **automático** diario de PostgreSQL con retención — **Claude/Ale**
- [ ] ⬜ Copia fuera del proveedor principal — **Ale**
- [ ] ⬜ Prueba **real** de restauración — **Ale/Claude**
- [ ] ⬜ Exportación completa por inmobiliaria — **Claude**
- [ ] ⬜ Plan documentado de incidentes y recuperación — **Ale/Claude**

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
| Errores críticos | 0 en cálculos o aislamiento | 🟡 cálculos ok; aislamiento pendiente |
| Cobertura de pruebas | dinero, fechas, permisos | 🟡 dinero/fechas ok; permisos/aislamiento pendiente |
| Restauración | backup restaurado en prueba | ⬜ |
| Onboarding | cliente piloto sin tocar código | ⬜ |
| Aislamiento | pruebas automáticas y manuales OK | ⬜ |
| Soporte | incidencias clasificadas y medidas | ⬜ |
| Uso | pilotos usan semanalmente | ⬜ |
| Retención | pilotos quieren seguir | ⬜ |

---

## Próximos pasos acordados

1. 🔴 **Ale:** repo privado + rotar secretos.
2. ✅ **Claude:** Alembic adoptado (hecho).
3. ✅ **Claude:** documento de diseño de multiempresa (hecho — revisar `DISENO_MULTIEMPRESA.md`).
4. ⬜ **Siguiente:** ejecutar Fase 2 (multiempresa) según el diseño, o intercalar auditoría + backups automáticos. A definir con Ale.
