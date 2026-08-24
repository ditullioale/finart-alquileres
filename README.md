# Gestión de Alquileres

Sistema web **SaaS multiempresa** para administrar alquileres de inmobiliarias:
personas, inmuebles, contratos, cobros, aumentos, liquidaciones a propietarios y
comprobantes imprimibles (recibos y pagarés). Una sola instancia aloja varias
inmobiliarias con sus datos **aislados**. Multiusuario, con base de datos
PostgreSQL e instalable como app en el celular (PWA).

Desarrollado en **Python (Flask)** + **PostgreSQL**. Incluye un **asistente con IA**
para consultas en lenguaje natural y **facturación electrónica AFIP/ARCA** (emisión
real de CAE) a través del servicio *Facturador ARCA*. La interfaz tiene **dos diseños
conmutables**: el **clásico** y **Aurora** (el nuevo, más moderno); se elige con
`?ui=nueva`/`?ui=clasica` o la variable `UI` (ver `app/ui.py`).

---

## Funcionalidades

- **Personas** — propietarios e inquilinos (DNI, CUIT, contacto, condición IVA).
- **Inmuebles** — datos, estado (disponible/alquilado/reservado), comisión, N° de
  cuenta de Litoral Gas.
- **Contratos** — una entrada única, **Nuevo contrato**, permite elegir entre
  **crear y redactar un contrato nuevo** con un asistente de 5 pasos, o **registrar
  un contrato existente** para administrar un alquiler ya firmado o en curso.
  Soporta **varios locadores/locatarios**, **CUIT** (con cálculo desde el DNI) y
  **consulta al BCRA** (situación crediticia) integrada. Editable, con rescindir /
  renovar / eliminar.
- **Documentación de contratos** — subir y ver DNI, recibos de sueldo, etc.
  (PDF/imagen), guardados en la base junto al contrato.
- **Cobranzas** — panel mensual tipo checklist con **vencimiento visible**;
  registro de pagos con **mora automática** (se calcula desde el **día 1 del mes**,
  con **gracia hasta el vencimiento**), gastos extras (con opción de **trasladar o no**
  al propietario), **pago a cuenta / parcial** y **arrastre de saldo**. Cobro rápido
  (modal + AJAX) y cobro ampliado. Al registrar un cobro se ofrecen las opciones de
  **recibo** (imprimir / PDF / email / WhatsApp) en el acto. **Cargar varios pagos**
  de una vez para contratos que arrancaron hace meses.
- **Aumentos** — por **índice oficial** (ICL/IPC/Casa Propia, con carga manual o
  consulta al BCRA) o por **porcentaje**. Historial editable. Aviso de vencidos.
- **Liquidaciones a propietarios** — por período; **todas juntas o individuales**;
  comisión configurable por contrato o por inmueble; **otros conceptos** para sumar o
  descontar (reparaciones, expensas, reintegros), **gastos extra desglosados por
  descripción** y **columna de período** (mes N/Total del contrato). Resumen mensual.
  Al generar una liquidación, se emite automáticamente la **factura de honorarios**
  (comisión) al propietario a través del **Facturador ARCA** (integración opcional; ver
  `FACTURADOR_URL` en `.env.ejemplo`). Si la comisión no supera el mínimo, la pantalla
  de la liquidación pregunta si se factura igual.
- **Facturación electrónica AFIP/ARCA** — emisión real de comprobantes con **CAE** a
  través del *Facturador ARCA* (en **producción**). Re-emisión segura de comprobantes
  que hayan sido de prueba (mock/homologación) sin duplicar los reales.
- **Asistente con IA** — globo flotante para preguntar en lenguaje natural (p. ej.
  *"¿quién debe?"*, *"¿cuándo vence tal alquiler?"*). Responde solo con datos de la
  inmobiliaria del usuario (herramientas acotadas por tenant, sin SQL libre). Se
  activa con `IA_API_KEY` (ver `.env.ejemplo`).
- **Comprobantes imprimibles** (HTML → PDF del navegador): recibos de alquiler
  (con vencimiento y fecha de pago), **recibos manuales**, liquidaciones, pagarés
  de contrato y **pagarés manuales**. El recibo de alquiler puede **enviarse por
  email en PDF** al inquilino (desde la pantalla del recibo o al registrar el cobro);
  si el inquilino no tiene email, se pide y se guarda en el momento.
- **Recordatorios por WhatsApp** — avisos de deuda a inquilinos.
- **Importador** de datos exportados de Inmosoft (Excel).
- **PWA** — instalable en Android/escritorio.

### Multiempresa, seguridad y administración

- **Aislamiento por inmobiliaria (multi-tenant).** Cada entidad comercial lleva
  `inmobiliaria_id`. Un filtro central de lectura (SQLAlchemy `do_orm_execute` +
  `with_loader_criteria`) limita toda consulta a la inmobiliaria del usuario, y la
  asignación al crear es automática (`before_flush`). Ver `app/tenant.py`.
- **Superadmin de plataforma.** Cuenta sin inmobiliaria propia que administra el
  alta de inmobiliarias (`app/blueprints/plataforma.py`). Un guardia
  (`_guardia_superadmin` en `app/__init__.py`) lo **encierra en el panel de
  Plataforma**: no accede a datos operativos de ninguna inmobiliaria (ni a la API).
- **Alta autogestionada.** Página pública `/registro`: una inmobiliaria pide
  acceso (queda pendiente) y el superadmin la **aprueba o rechaza**.
- **Roles** — `admin`, `operador`, `contador` (solo lectura + exportar),
  `lectura`, y `superadmin`. Los roles de solo lectura tienen bloqueadas las
  mutaciones (`_guardia_solo_lectura`).
- **Auditoría** — registro de acciones (quién/qué/cuándo) vía `after_flush`
  (`app/auditoria.py`), consultable desde la app.
- **Seguridad** — protección **CSRF**, cookies de sesión endurecidas, **forzar
  cambio de contraseña** por defecto, **límite de intentos de login**, y montos en
  **Decimal** exacto (`q2()` en `utils.py`).
- **Envío de emails** (`app/emailer.py`) — recuperación de contraseña, verificación
  de email en el registro y **recibos en PDF al inquilino**. Usa la **API HTTP de
  Brevo** (`BREVO_API_KEY`, recomendada en la nube porque no depende de los puertos
  SMTP que bloquea Railway) o SMTP clásico; si no hay nada configurado, deja el
  mensaje en el log.
- **Observabilidad** — health checks (`/app-health`, `/database-health`,
  `/facturador-health`), logging estructurado con id de correlación (`X-Request-Id`)
  por request y monitoreo de errores con **Sentry** (se activa con `SENTRY_DSN`).
- **Backup por inmobiliaria** — exportación de los datos de cada inmobiliaria.

---

## Requisitos

- Python 3.10 o superior.
- Para uso multiusuario en red o nube: PostgreSQL.

## Instalación local (desarrollo / una PC)

```bash
cd gestion-alquileres
python -m venv venv
venv\Scripts\activate        # Windows   (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
python run.py
```

Abrir http://localhost:5000 — usuario inicial **admin** / **admin123**
(el sistema te obliga a cambiarla en el primer ingreso).

Por defecto usa **SQLite** en una carpeta local (`%LOCALAPPDATA%\GestionAlquileres`),
fuera de OneDrive para evitar bloqueos de sincronización.

### Atajo en Windows
Doble clic en `Iniciar Gestion Alquileres.bat` levanta el programa y abre el
navegador. Para acceso desde otra PC de la red: `http://IP-DEL-SERVIDOR:5000`.

## Configuración (variables de entorno)

La app lee la configuración desde variables de entorno (ver `.env.ejemplo`):

- **Base de datos:** `DATABASE_URL=postgresql://usuario:clave@host:5432/alquileres`
  (o `PG_DB`, `PG_USER`, `PG_PASSWORD`, `PG_HOST`, `PG_PORT`). Sin nada → SQLite.
- **`SECRET_KEY`** — clave larga y secreta (obligatoria en producción).
- **`COOKIE_SECURE`** — `1` en producción (cookies solo por HTTPS).
- **`SUPERADMIN_USER` / `SUPERADMIN_PASS`** — si se definen, se crea el superadmin
  de plataforma en el arranque (una sola vez).
- **Email** (opcional; recuperación de contraseña, verificación de registro y envío
  de recibos). Recomendado: **`BREVO_API_KEY`** (API HTTP de Brevo, funciona donde el
  hosting bloquea SMTP) + **`EMAIL_FROM`** (remitente verificado en Brevo) y
  **`EMAIL_FROM_NAME`** (nombre visible). Alternativa por SMTP: `SMTP_HOST`,
  `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` (con `EMAIL_FROM`).
- **`SENTRY_DSN`** (opcional) — activa el monitoreo de errores con Sentry.
- **`GAS_IMPORT_TOKEN`** — token del robot de Litoral Gas.
- **`IA_API_KEY`** (opcional) — habilita el **asistente con IA** (API de Anthropic).
  Sin esta clave, el globo del asistente no aparece.
- **Facturador ARCA** (opcional) — `FACTURADOR_URL` y token de integración para la
  facturación electrónica (ver `.env.ejemplo` y `FINART_INTEGRACION_API.md`).

> El archivo `.env` guarda secretos y **no debe subirse** al repositorio
> (excluido en `.gitignore`). El repositorio debe ser **privado**.

## Migraciones (Alembic / Flask-Migrate)

El esquema se gestiona con **Alembic** (carpeta `migrations/`). En el arranque, la
app aplica las migraciones pendientes automáticamente (`flask db upgrade` interno).
Para generar una nueva migración durante el desarrollo:

```bash
flask db migrate -m "descripcion"
flask db upgrade
```

En una base **nueva** en modo test se crean las tablas directamente.

## Importar datos de Inmosoft

```bash
python importar_inmosoft.py            # carpeta por defecto: ../DatosInmosoft_...
python importar_inmosoft.py --reset    # recrea las tablas antes de importar
```

## Despliegue en la nube (Railway)

1. Subir el código a un repositorio **privado** de GitHub.
2. En Railway: New Project → GitHub Repository → seleccionar el repo.
3. Agregar **PostgreSQL** (Database → Postgres) al proyecto.
4. Variables del servicio de la app:
   - `SECRET_KEY` = clave larga y secreta.
   - `DATABASE_URL` = referencia a la Postgres del proyecto.
   - `COOKIE_SECURE` = `1`.
   - `SUPERADMIN_USER` / `SUPERADMIN_PASS` = credenciales del administrador de
     plataforma (para el onboarding de inmobiliarias).
   - `MIGRATE_ON_BOOT` = `0` para que **no** migre al arrancar: con 2 workers,
     los dos correrían Alembic a la vez. Las migraciones las aplica el
     `release: flask db upgrade` del `Procfile` (en Railway, Settings → Deploy →
     Pre-deploy Command), una sola vez y antes de levantar los workers.
   - *(Opcional)* `BREVO_API_KEY` + `EMAIL_FROM` (+ `EMAIL_FROM_NAME`) para el envío
     de emails (recuperación de contraseña, verificación de registro y recibos).
   - *(Opcional)* `SENTRY_DSN` para el monitoreo de errores.
5. El arranque usa `Procfile` (`gunicorn run:app`); las migraciones van en el
   comando de release (ver `MIGRATE_ON_BOOT` arriba).
6. **Dominio propio** (opcional): Settings → Networking → Custom Domain, y cargar
   el CNAME en el registrador.

## Copias de seguridad y monitoreo

- **App:** exportación por inmobiliaria desde Herramientas.
- **PostgreSQL:** `pg_dump` de la base (respaldo general).
- **Backups automáticos diarios** por **GitHub Actions** (`.github/workflows/backup.yml`):
  `pg_dump` de las dos bases (gestor y facturador) con **verificación de restauración**
  en un contenedor y retención de los artefactos. Ver **GUIA_BACKUPS.md** / **BACKUPS.md**.
- **Monitoreo:** health checks públicos para *uptime* y una alerta semanal de
  **vencimiento del certificado ARCA** (`.github/workflows/cert-check.yml`).

## Pruebas (QA)

```bash
python tests_qa.py
```

Batería de pruebas que cubre aislamiento multiempresa, roles, onboarding, alta
autogestionada, guardia del superadmin, recuperación de contraseña, documentación,
cobros/recibos y más.

## Estructura del proyecto

```
gestion-alquileres/
├─ run.py                  # punto de entrada (waitress/gunicorn)
├─ config.py               # configuración (lee .env)
├─ importar_inmosoft.py    # importador de Excel
├─ tests_qa.py             # batería de pruebas QA
├─ requirements.txt
├─ Procfile / runtime.txt  # despliegue en la nube
├─ migrations/             # Alembic (esquema versionado)
├─ app/
│  ├─ __init__.py          # application factory, PWA, arranque, guardias
│  ├─ models.py            # modelos (incluye Inmobiliaria, auditoría, documentos, solicitudes)
│  ├─ tenant.py            # aislamiento multiempresa (filtro + asignación)
│  ├─ auditoria.py         # registro de acciones
│  ├─ ui.py                # conmutador de diseño clásico / Aurora
│  ├─ asistente.py         # asistente con IA (herramientas acotadas por tenant)
│  ├─ emailer.py           # envío de mails (API de Brevo / SMTP o log)
│  ├─ utils.py             # fechas, montos (Decimal), importe en letras, índices
│  ├─ indices_oficiales.py # consulta ICL (BCRA)
│  ├─ blueprints/          # auth, personas, inmuebles, contratos, cobros, aumentos,
│  │                       #   liquidaciones, recibos, usuarios, ajustes, plataforma,
│  │                       #   api, asistente_web, facturador_web
│  ├─ templates/           # vistas (Jinja2): diseño clásico + carpeta aurora/
│  └─ static/              # estilos, fuente Inter, íconos, manifest, service worker, aurora.js/css
├─ .github/workflows/      # CI + backups automáticos + alerta de vencimiento de certificado ARCA
├─ MANUAL_USUARIO.md       # guía de uso para el día a día
├─ DISENO_MULTIEMPRESA.md  # diseño del aislamiento multiempresa
├─ SEGUIMIENTO_FINART_2_0.md # seguimiento del roadmap
└─ BACKUPS.md              # plan de copias de seguridad
```

Ver **MANUAL_USUARIO.md** para el uso cotidiano del sistema.
