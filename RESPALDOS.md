# Respaldos de la base (Postgres en Railway)

Desde que se guardan **firmas digitales** (imágenes y PDFs) dentro de Postgres, conviene
tener los respaldos al día. Hay tres capas, de más a menos automática.

## 1) Backups automáticos de Railway (la red de seguridad principal)

Railway hace snapshots del servicio de Postgres. En el proyecto de Railway:

1. Entrá al servicio **Postgres**.
2. Pestaña **Backups** (o **Data → Backups**, según la versión).
3. Activá los backups automáticos (diarios) y, si está disponible en tu plan, subí la
   retención (cuántos días se guardan).

Esto corre solo y es lo que te salva ante un borrado o una caída. Verificá cada tanto que
la fecha del último backup esté al día.

## 2) `pg_dump` manual (copia que te guardás vos, restaurable)

Una copia completa y **restaurable** de toda la base, en un archivo. Necesitás la
connection string **pública** de Postgres (Railway → servicio Postgres → **Connect** →
`DATABASE_URL`/`Postgres Connection URL`, la que usa `...proxy.rlwy.net`, no la privada).

```bash
# Copia comprimida (formato custom, recomendado para restaurar):
pg_dump "postgresql://USUARIO:CLAVE@HOST:PUERTO/railway" -Fc -f finart-backup.dump

# O en SQL plano (legible):
pg_dump "postgresql://USUARIO:CLAVE@HOST:PUERTO/railway" -f finart-backup.sql
```

Restaurar en una base vacía:

```bash
pg_restore --clean --if-exists -d "postgresql://USUARIO:CLAVE@HOST:PUERTO/railway" finart-backup.dump
# (si es .sql):  psql "postgresql://..." -f finart-backup.sql
```

> Guardá estos archivos fuera de Railway (tu compu, un drive). Son datos sensibles:
> tratalos con cuidado.

Con la **Railway CLI** también podés: `railway connect Postgres` para abrir una sesión, o
`railway run pg_dump ...` para tomar el dump desde el entorno del proyecto.

## 3) Respaldo desde la app (copia lógica complementaria)

En **Plataforma** (solo el superadmin), botón **"Descargar respaldo"** baja un `.zip` con un
JSON por tabla, incluidas las firmas y sus PDFs (los binarios van en base64). No reemplaza
a `pg_dump` para restaurar, pero es una copia rápida que te podés guardar en cualquier
momento sin herramientas externas.

---

**Recomendación mínima:** tené activados los backups automáticos de Railway (capa 1) y, de
vez en cuando, bajá un `pg_dump` (capa 2) y guardalo aparte.
