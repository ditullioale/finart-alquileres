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

## 3. Probar un restore SIN riesgo (el paso que casi todos saltean)

Lo importante es comprobar que el backup **sirve**, no solo que existe. Y en Railway se puede
hacer **sin tocar producción**, porque el restore **no pisa** la base en uso: crea una copia.

1. En el servicio de base → pestaña **Backups** (o **PITR / Point-in-Time Recovery**, si tu
   plan lo incluye).
2. Elegí un backup (o un momento puntual, en PITR) y dale **Restore**.
3. Railway **provisiona un Postgres NUEVO** con los datos restaurados y **deja intacta** la
   base original. (En backups normales, el cambio queda "en borrador": lo revisás y recién ahí
   lo confirmás; con PITR siempre nace una base nueva.)
4. **Verificá que los datos están** (este es el hito): abrí el servicio nuevo → pestaña
   **Data** y mirá que las tablas tengan filas —por ejemplo `contratos`, `pagos`,
   `liquidaciones` en la base del gestor; `facturas`, `emisores` en la del facturador—. Si ves
   los registros, **el restore funciona de verdad**.
5. Cuando lo confirmaste, **borrá el servicio nuevo** (era solo para el ensayo) para no pagar
   de más.

Con esto tenés un restore **probado**, no solo la teoría. Anotá la fecha del ensayo y repetilo
cada tanto (p. ej. cada 3–6 meses).

## 4. Point-in-Time Recovery (el nivel más alto)

Railway ofrece **PITR**: en vez de volver solo al último backup diario, restaura la base a
**cualquier momento** dentro de la ventana de retención (por ejemplo "ayer a las 15:42, justo
antes del problema"), y **siempre sobre una base nueva** (ideal para el ensayo del punto 3).
Si tu plan lo permite, activalo. Es la mejor protección.

## Resumen mínimo para vender

- ✅ Backups **diarios activados** en las dos bases.
- ✅ Un backup **manual tomado** al menos una vez.
- ✅ Un **restore ENSAYADO** en una base nueva, con los datos verificados (no solo "sé dónde
  está el botón"). Fecha del último ensayo: __ / __ / ____.
- 🎯 Ideal a futuro: un entorno de **staging** para ensayar sin pensar.

---

Fuentes: [Railway — Back Up and Restore Postgres](https://docs.railway.com/guides/postgres-backups-restores) ·
[Railway — Point-in-Time Recovery](https://docs.railway.com/volumes/point-in-time-recovery)
