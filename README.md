# Gestión de Alquileres

Sistema web **SaaS multiempresa** para administrar alquileres de inmobiliarias:
personas, inmuebles, contratos, cobros, aumentos, liquidaciones a propietarios y
comprobantes imprimibles (recibos y pagarés). Una sola instancia aloja varias
inmobiliarias con sus datos **aislados**. Multiusuario, con base de datos
PostgreSQL e instalable como app en el celular (PWA).

Desarrollado en **Python (Flask)** + **PostgreSQL**, con islas de **React** en
algunas pantallas.

---

## Funcionalidades

- **Personas** — propietarios e inquilinos (DNI, CUIT, contacto, condición IVA).
- **Inmuebles** — datos, estado (disponible/alquilado/reservado), comisión, N° de
  cuenta de Litoral Gas.
- **Contratos** — alta directa (para alquileres en curso) y un **generador de
  contratos tipo asistente (wizard) de 5 pasos** que da de alta el contrato en el
  sistema. Soporta **varios locadores/locatarios**, **CUIT** (con cálculo desde el
  DNI) y **consulta al BCRA** (situación crediticia) integrada. Editable, con
  rescindir / renovar / eliminar.
- **Documentación de contratos** — subir y ver DNI, recibos de sueldo, etc.
  (PDF/imagen), guardados en la base junto al contrato.
- **Cobranzas** — panel mensual tipo checklist con **vencimiento visible**;
  registro de pagos con **mora automática**, gastos extras, **pago a cuenta /
  parcial** y **arrastre de saldo**. Cobro rápido (modal + AJAX) y cobro ampliado.
- **Aumentos** — por **índice oficial** (ICL/IPC/Casa Propia, con carga manual o
  consulta al BCRA) o por **porcentaje**. Historial editable. Aviso de vencidos.
- **Liquidaciones a propietarios** — por período; **todas juntas o individuales**;
  comisión configurable por contrato o por inmueble. Resumen mensual.
- **Comprobantes imprimibles** (HTML → PDF del navegador): recibos de alquiler
  (con vencimiento y fecha de pago), **recibos manuales**, liquidaciones, pagarés
  de contrato y **pagarés manuales**.
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
- **Recuperación de contraseña** — enlace con token temporal (itsdangerous) y
  envío de mail (`app/emailer.py`, SMTP o log si no está configurado).
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
- **SMTP** (opcional, para recuperación de contraseña): `SMTP_HOST`, `SMTP_PORT`,
  `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`.
- **`GAS_IMPORT_TOKEN`** — token del robot de Litoral Gas.

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
   - *(Opcional)* variables SMTP para recuperación de contraseña.
5. El arranque usa `Procfile` (`gunicorn run:app`) y aplica las migraciones solo.
6. **Dominio propio** (opcional): Settings → Networking → Custom Domain, y cargar
   el CNAME en el registrador.

## Copias de seguridad

- **App:** exportación por inmobiliaria desde Herramientas.
- **PostgreSQL:** `pg_dump` de la base (respaldo general).
- Ver **BACKUPS.md** para el plan de respaldos.

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
│  ├─ emailer.py           # envío de mails (SMTP o log)
│  ├─ utils.py             # fechas, montos (Decimal), importe en letras, índices
│  ├─ indices_oficiales.py # consulta ICL (BCRA)
│  ├─ blueprints/          # auth, personas, inmuebles, contratos, cobros, aumentos,
│  │                       #   liquidaciones, recibos, usuarios, ajustes, plataforma, api
│  ├─ templates/           # vistas (Jinja2)
│  └─ static/              # estilos, fuente Inter, íconos, manifest, service worker, React bundle
├─ MANUAL_USUARIO.md       # guía de uso para el día a día
├─ DISENO_MULTIEMPRESA.md  # diseño del aislamiento multiempresa
├─ SEGUIMIENTO_FINART_2_0.md # seguimiento del roadmap
└─ BACKUPS.md              # plan de copias de seguridad
```

Ver **MANUAL_USUARIO.md** para el uso cotidiano del sistema.
