# Plan de migración del front a React — por sprints

## Estrategia elegida: "islas" de React sobre Flask (incremental, sin big-bang)

En vez de tirar abajo la app actual y reescribir todo, mantenemos Flask sirviendo
las páginas y **reemplazamos una pantalla a la vez** por un componente React montado
dentro del template existente. Cada isla es independiente: si algo falla, se vuelve
atrás sin tocar el resto. La API (endpoints que devuelven JSON) se va construyendo
a medida que cada pantalla la necesita.

Ventajas para este proyecto:

- **Bajo riesgo**: lo que ya funciona sigue funcionando; migramos de a poco.
- **Siempre desplegable**: cada sprint deja la app usable en producción.
- **Se puede pausar**: si en cualquier momento querés frenar, la app queda estable
  (mitad Jinja, mitad React) sin problemas.
- **Aprovecha lo hecho**: ya tenés fetch/AJAX, token CSRF en un `<meta>`, sesión por
  cookie. React reusa todo eso.

Al final (opcional) se puede unificar en una SPA completa con navegación sin recargas.

---

## Decisiones técnicas base

- **Herramientas**: React + Vite (compilador rápido) + `fetch` para la API.
  Para el manejo de datos, TanStack Query (cachea, reintenta, refresca). Opcional.
- **Estilos**: se puede reusar el CSS actual al principio, y migrar a Tailwind
  gradualmente si querés (lo evaluamos en el camino; no es obligatorio).
- **Auth**: se reutiliza la sesión de Flask-Login (cookie) + el token CSRF del `<meta>`.
  React llama a la API con `credentials: 'include'` y manda el header `X-CSRFToken`.
- **Build/deploy**: Vite compila los componentes a `app/static/js/`. En Railway se
  agrega un paso de build de Node antes del de Python (Nixpacks lo soporta). Esto es
  el único cambio "de fontanería" del deploy; lo dejamos resuelto en el Sprint 0.

---

## Sprints

### Sprint 0 — Cimientos (sin cambios visibles para el usuario)
- Instalar Vite + React en una carpeta `frontend/` del proyecto.
- Configurar el build para que emita a `app/static/js/`.
- Montar un "hola mundo" React en una página de prueba para validar el pipeline.
- Definir la convención de la API: rutas `/api/...`, formato JSON, manejo de errores
  y de auth (sesión + CSRF).
- Configurar el build de Node en Railway.
- **Resultado**: nada cambia para el usuario, pero queda todo listo para empezar.
- **Riesgo**: bajo.

### Sprint 1 — Primera isla: Cobranzas
La pantalla más interactiva y la mejor para probar el enfoque.
- API: `GET /api/cobranzas?mes=&anio=` (lista + totales), `POST /api/cobros/rapido`
  (ya casi existe), `POST /api/gas/...` según haga falta.
- Componente React de Cobranzas: tabla con filtro instantáneo, cobro en modal,
  totales que se actualizan solos, estados con íconos.
- Reemplaza la pantalla actual de Cobranzas.
- **Resultado**: se valida el enfoque de punta a punta con la pantalla clave.

### Sprint 2 — Listados (Contratos, Personas, Inmuebles)
- API de listados con búsqueda, orden y paginación.
- Un componente de **tabla reutilizable** (búsqueda, orden, acciones por fila).
- Migrar las tres listas usando ese componente.
- **Resultado**: navegación de listas fluida y consistente.

### Sprint 3 — Panel de inicio + Control de gas
- API de estadísticas del dashboard y de estado de gas.
- Dashboard con tarjetas y (opcional) un gráfico de cobranza del mes.
- Panel de gas interactivo (ver facturas, asignar cuentas) en React.

### Sprint 4 — Formularios
Donde más se nota la mejora de experiencia.
- Alta/edición de contrato, cobro detallado, alta de personas e inmuebles en React.
- Validación en vivo, selects buscables, fecha de fin automática, sin perder datos.
- API `POST`/`PUT` para guardar.

### Sprint 5 — Pantallas restantes
- Detalle de contrato, aumentos, liquidaciones, recibos y vistas menores.
- Al terminar, casi toda la app está en React.

### Sprint 6 — Consolidación / SPA (opcional)
- React Router: navegación sin recargas entre todas las pantallas.
- Flask queda como API + sirve un único `index.html`.
- Pulido final: transiciones, estado global, carga perezosa (lazy) de pantallas.

---

## Cómo trabajamos cada sprint

1. Construimos la API que necesita esa pantalla (endpoints JSON).
2. Construimos el/los componente(s) React y los montamos reemplazando el template.
3. Probamos que funcione igual o mejor que antes (mantenemos el QA existente y
   sumamos pruebas de la API).
4. Desplegamos. La app queda usable: parte en React, parte en Jinja, conviviendo.

En cualquier momento se puede frenar: no hay un punto de "no retorno".

---

## A tener en cuenta (honesto)

- **Tiempo**: cada sprint es de varias sesiones de trabajo. Como trabajás con límites
  de uso, lo iremos haciendo por partes a lo largo de varios días.
- **Complejidad de mantenimiento**: una app con React + API es más compleja de
  mantener y desplegar que la actual (dos "mundos": front y back). Es el costo de la
  experiencia más moderna.
- **No es obligatorio llegar al Sprint 6**: con los primeros 2-3 sprints ya tenés las
  pantallas más usadas modernizadas; podés parar ahí si te alcanza.
- **Recomendación de arranque**: Sprint 0 + Sprint 1 (Cobranzas). Si te gusta cómo
  queda y cómo se siente el flujo de trabajo, seguimos; si no, frenamos sin haber
  roto nada.
