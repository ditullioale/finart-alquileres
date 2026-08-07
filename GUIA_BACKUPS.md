# Guía — Backups y restore del Postgres (Railway)

> Pilar 3 del checklist "listo para vender". El objetivo: que si un día se rompe o se
> borra algo, puedas volver atrás. Un backup que nunca restauraste no es un backup.

Tenés **dos bases** en Railway y las dos importan:
- **Postgres** → datos del gestor (personas, contratos, cobranzas, liquidaciones…).
- **Postgres-tV6l** → datos del facturador (emisores, comprobantes, CAE).

Hacé esto en **las dos**.

## 1. Activar backups automáticos

1. En Railway, clic en el servicio de base (por ejemplo **Postgres**).
2. Andá a la pestaña **Settings** → sección **Backups**.
3. Activá un **schedule**: elegí **Daily** (diario). Railway los guarda según la retención
   que elijas.
4. (Recomendado) sumá también **Weekly** o **Monthly** para tener copias más viejas.
5. Repetí todo en **Postgres-tV6l**.

Con esto ya tenés copias automáticas todos los días, sin hacer nada.

## 2. Tomar un backup manual ahora (para probar)

En la misma pestaña **Backups** suele haber un botón para crear un backup **manual /
snapshot** al instante. Tomá uno ahora en cada base. Así tenés una copia fresca antes de
seguir.

## 3. Probar un restore (el paso que casi todos saltean)

Esto es lo importante: comprobar que el backup **sirve**, no solo que existe.

1. En la pestaña **Backups**, buscá un backup por su fecha.
2. Al lado tiene un botón **Restore**.
3. Railway te va a pedir confirmación porque el restore **reemplaza los datos actuales**
   de esa base por los del backup.

⚠️ **Cuidado:** un restore sobre la base de producción PISA los datos actuales. Para
*probar* sin riesgo, lo ideal es hacerlo en un momento tranquilo y sabiendo que vas a
volver a un estado anterior. Si querés cero riesgo, la forma más segura de "ensayar" es:
tomar el backup, y hacer el restore recién cuando tengas un entorno de **staging** (una
copia separada de producción). Mientras no tengas staging, al menos **confirmá que el
botón Restore está disponible y entendés el flujo** — eso ya te da la tranquilidad de que
la copia existe y es restaurable.

## 4. (Opcional, más avanzado) Point-in-Time Recovery

Railway ofrece **PITR**: en vez de volver solo al último backup diario, te deja restaurar
la base a **cualquier momento** dentro de la ventana de retención (por ejemplo "ayer a las
15:42, justo antes del problema"). Si tu plan lo permite, activalo en la configuración de
la base. Es el nivel más alto de protección.

## Resumen mínimo para vender

- ✅ Backups **diarios activados** en las dos bases.
- ✅ Un backup **manual tomado** al menos una vez.
- ✅ Sabés **dónde está el botón Restore** y qué hace.
- 🎯 Ideal a futuro: un entorno de **staging** para ensayar el restore sin tocar producción.

---

Fuentes: [Railway — Back Up and Restore Postgres](https://docs.railway.com/guides/postgres-backups-restores) ·
[Railway — Point-in-Time Recovery](https://docs.railway.com/volumes/point-in-time-recovery)
