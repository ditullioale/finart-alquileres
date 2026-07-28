# Backups y continuidad — FINART

## Lo que YA está (en la app)

- **Exportación completa por inmobiliaria** (portabilidad / cierre de cuenta):
  `Ajustes → Respaldo`. Descarga un Excel con **solo los datos de tu inmobiliaria**
  (personas, inmuebles, contratos, pagos, aumentos, liquidaciones, fiadores,
  usuarios, etc.). El superadmin exporta todo. Sirve para dar de baja o migrar un
  cliente sin arrastrar datos de otros.

## Lo que falta (requiere decisión de hosting — Ale)

El roadmap pide **backup automático diario + copia externa + prueba de
restauración**. Eso no vive dentro de la app: depende del proveedor. Opciones para
Railway + PostgreSQL, de más simple a más completa:

### Opción A — Backups del proveedor (recomendada para empezar)
Railway ofrece backups administrados de PostgreSQL (según plan). Activarlos en el
panel de Railway y definir la **retención** (p. ej. 7–30 días). Es lo más simple y
no requiere código. **Acción de Ale:** activarlo en Railway.

### Opción B — Backup programado a almacenamiento externo (más robusto)
Un job diario que corre `pg_dump` y sube el archivo comprimido a un bucket
(Cloudflare R2 / AWS S3 / Backblaze). Da copia **fuera del proveedor principal**.
Requiere:
- Un bucket y sus credenciales (Ale las crea).
- Un cron: Railway Cron Job (o un servicio aparte) que ejecute el script.
- Retención y rotación (borrar copias viejas).

**Cuando tengas el bucket, yo dejo listo** el script `pg_dump` + subida + rotación
y el cron. Solo necesito: proveedor de bucket elegido y sus credenciales cargadas
como variables de entorno (nunca en el código).

### Prueba de restauración (obligatoria antes de vender)
No alcanza con que exista el archivo: hay que **restaurarlo de verdad** en una base
de prueba y verificar que la app arranca y los datos están. Se hace una vez al
configurar y se repite periódicamente. Lo documentamos como checklist cuando
elijamos A o B.

## Recomendación

1. **Ahora:** activar backups de Railway (Opción A) — cero código, cubre lo básico.
2. **Antes del piloto comercial:** sumar copia externa (Opción B) + una prueba de
   restauración real.

> Correo para recuperación de contraseña: la app ya tiene el flujo; para que envíe
> los emails hay que definir las variables SMTP (`SMTP_HOST`, `SMTP_PORT`,
> `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`). Sin ellas, el enlace queda en el log del
> servidor. **Acción de Ale:** definir esas variables con un proveedor de email.
