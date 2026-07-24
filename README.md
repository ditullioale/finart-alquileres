# Gestión de Alquileres

Sistema web para administrar alquileres de una inmobiliaria: personas, inmuebles,
contratos, cobros, aumentos, liquidaciones a propietarios y comprobantes
imprimibles (recibos y pagarés). Multiusuario, con base de datos PostgreSQL e
instalable como app en el celular (PWA).

Desarrollado en **Python (Flask)** + **PostgreSQL**.

---

## Funcionalidades

- **Personas** — propietarios e inquilinos (DNI, CUIT, contacto, condición IVA).
- **Inmuebles** — datos, estado (disponible/alquilado/reservado), comisión.
- **Contratos** — alta directa (para alquileres en curso) e integración con un
  **generador de contratos de locación** que da de alta el contrato en el sistema.
  Editable: fechas, precio, comisión, mora, método de aumento. Rescindir/eliminar.
- **Cobranzas** — panel mensual tipo checklist; registro de pagos con **mora
  automática**, gastos extras, **pago a cuenta / parcial** y **arrastre de saldo**
  al mes siguiente. Historial por contrato.
- **Aumentos** — por **índice oficial** (ICL/IPC/Casa Propia, con carga manual o
  consulta al BCRA) o por **porcentaje**. Historial editable. Aviso de vencidos.
- **Liquidaciones a propietarios** — por período; **todas juntas o individuales**
  por inmueble; comisión configurable por contrato o por inmueble. Resumen mensual.
- **Comprobantes imprimibles** (HTML → PDF del navegador): recibos de alquiler,
  **recibos manuales**, liquidaciones, pagarés de contrato y **pagarés manuales**.
- **Usuarios** — login individual, roles Administrador/Operador.
- **Avisos** — aumentos vencidos (badge en el menú) y contratos por vencer (inicio).
- **Importador** de datos exportados de Inmosoft (Excel).
- **PWA** — instalable en Android/escritorio.

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
(cambiala apenas entres, en Ajustes o Usuarios).

Por defecto usa **SQLite** en una carpeta local (`%LOCALAPPDATA%\GestionAlquileres`),
fuera de OneDrive para evitar bloqueos de sincronización.

### Atajo en Windows
Doble clic en `Iniciar Gestion Alquileres.bat` levanta el programa y abre el
navegador. Para acceso desde otra PC de la red: `http://IP-DEL-SERVIDOR:5000`.

## Configuración de la base de datos

La app lee la conexión desde variables de entorno (ver `.env.ejemplo`):

- **PostgreSQL por partes:** `PG_DB`, `PG_USER`, `PG_PASSWORD`, `PG_HOST`, `PG_PORT`.
- **o URL completa:** `DATABASE_URL=postgresql://usuario:clave@host:5432/alquileres`.
- Si no se define nada → SQLite local.

> El archivo `.env` guarda la contraseña de la base y **no debe subirse** a ningún
> repositorio (ya está excluido en `.gitignore`).

## Migraciones (bases ya existentes)

Al agregar columnas nuevas, en una base ya cargada correr una vez:

```bash
python migrar.py
```

Es no destructivo (solo agrega lo que falta). En una base **nueva** no hace falta:
las tablas se crean solas al arrancar.

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
   - `SECRET_KEY` = (una clave larga y secreta).
   - `DATABASE_URL` = referencia a la de PostgreSQL del proyecto.
5. El arranque usa `Procfile` (`gunicorn run:app`). Las tablas se crean solas.
6. Migrar los datos existentes con `pg_dump` / `pg_restore`.

## Copias de seguridad

- **SQLite:** copiar el archivo `alquileres.db`.
- **PostgreSQL:** `pg_dump` de la base `alquileres`.

## Estructura del proyecto

```
gestion-alquileres/
├─ run.py                  # punto de entrada (waitress/gunicorn)
├─ config.py               # configuración (lee .env)
├─ migrar.py               # migraciones no destructivas
├─ importar_inmosoft.py    # importador de Excel
├─ requirements.txt
├─ Procfile / runtime.txt  # despliegue en la nube
├─ app/
│  ├─ __init__.py          # application factory, PWA, arranque
│  ├─ models.py            # modelos (14 tablas)
│  ├─ utils.py             # fechas, montos, importe en letras, índices
│  ├─ indices_oficiales.py # consulta ICL (BCRA)
│  ├─ blueprints/          # personas, inmuebles, contratos, cobros,
│  │                       #   aumentos, liquidaciones, recibos, usuarios, ajustes
│  ├─ templates/           # vistas (Jinja2)
│  └─ static/              # estilos, íconos, manifest, service worker
└─ MANUAL_USUARIO.md       # guía de uso para el día a día
```

Ver **MANUAL_USUARIO.md** para el uso cotidiano del sistema.
