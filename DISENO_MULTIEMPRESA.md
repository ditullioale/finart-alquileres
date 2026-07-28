# FINART 2.0 — Diseño técnico de multiempresa (multi-tenant)

> Documento de diseño. **No implementa nada todavía**: define cómo vamos a aislar
> los datos de cada inmobiliaria antes de escribir el código. Se ejecuta después
> de revisarlo y aprobarlo.

Versión 1.0 · Base: roadmap FINART 2.0 (28/07/2026)

---

## 1. Objetivo y decisiones ya cerradas

Convertir FINART en un **SaaS multiempresa**: una sola app, un solo código, una
sola base PostgreSQL compartida, donde **cada inmobiliaria ve y toca únicamente
sus propios datos**.

Decisiones tomadas (del roadmap):

- Base **PostgreSQL compartida** con aislamiento lógico por `inmobiliaria_id`.
- Bases/entornos dedicados solo como plan "Empresa" (excepción, más adelante).
- Backend **Flask**, frontend **Jinja + React selectivo**.
- Prioridad: confiabilidad, seguridad y aislamiento **probado**.

**Regla de oro:** toda entidad comercial pertenece a una inmobiliaria. Ninguna
consulta, edición, exportación ni descarga puede depender solo del ID del
registro: **siempre** se verifica además la inmobiliaria del usuario logueado.

---

## 2. Modelo de datos

### 2.1. Tabla nueva: `Inmobiliaria` (el "tenant")

| Campo | Tipo | Nota |
|---|---|---|
| id | int PK | Raíz del tenant |
| nombre | str | Razón social / nombre comercial |
| slug | str único | Identificador corto (para URLs/subdominios a futuro) |
| cuit | str | Datos fiscales |
| direccion, localidad, telefono, email | str | Datos de contacto |
| logo_path | str | Ruta al logo (almacenamiento privado, ver §6) |
| mora_diaria_pct_default | num | Config por tenant |
| comision_pct_default | num | Config por tenant |
| numeracion_recibos | int | Contador propio de recibos/comprobantes |
| plan | str | inicial / profesional / empresa |
| activa | bool | Baja lógica / suspensión por falta de pago |
| creada | datetime | |

### 2.2. `Usuario` pertenece a una inmobiliaria

- Agregar `inmobiliaria_id` (FK, obligatorio salvo el **superadmin** de la
  plataforma, ver §2.4).
- El login sigue igual; al autenticar, el usuario "trae" su `inmobiliaria_id`.

### 2.3. `inmobiliaria_id` en todas las entidades comerciales

Se agrega `inmobiliaria_id` (FK, **NOT NULL**, indexado) a:

`Persona`, `Inmueble`, `Contrato`, `Pago`, `GastoExtra`, `Aumento`, `Fiador`,
`Liquidacion`, `ReciboManual`, `GasEstado`, `IndiceValor` (a evaluar: los índices
podrían ser globales), y la config de la inmobiliaria (que ya vive en la propia
tabla `Inmobiliaria`).

> Las tablas puente `contrato_colocatarios` / `contrato_colocadores` heredan el
> tenant del contrato; no necesitan columna propia si siempre se acceden vía el
> contrato (que sí está aislado).

### 2.4. Rol de plataforma (superadmin)

Un rol extra **por encima** de las inmobiliarias, para vos como dueño del SaaS:
dar de alta inmobiliarias, suspender, ver métricas. No pertenece a ninguna
inmobiliaria y es el único que puede cruzar tenants (con muchísimo cuidado).

---

## 3. Estrategia de aislamiento (lo más importante)

El riesgo real no es agregar la columna: es **olvidarse de filtrar** en alguna de
las decenas de consultas. Por eso el roadmap pide "centralizar el filtro". Tres
capas de defensa:

### Capa 1 — Filtro automático por sesión (defensa principal)

Usar el evento de SQLAlchemy **`with_loader_criteria`**: en cada request, apenas
sabemos qué inmobiliaria es la del usuario logueado, se instala un criterio
global que agrega `WHERE inmobiliaria_id = :actual` a **toda** consulta sobre
modelos con tenant, sin que haya que escribirlo en cada `query`.

```python
# Bosquejo (se pule en la implementación)
from sqlalchemy import event
from sqlalchemy.orm import with_loader_criteria

@event.listens_for(db.session.__class__, "do_orm_execute")
def _filtrar_por_tenant(execute_state):
    if not execute_state.is_select:
        return
    tid = tenant_actual()          # inmobiliaria del usuario logueado
    if tid is None:                # superadmin o proceso de sistema
        return
    for mapper in mappers_con_tenant:
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(mapper.class_,
                                 lambda cls: cls.inmobiliaria_id == tid,
                                 include_aliases=True))
```

### Capa 2 — Asignación automática al crear

Un hook `before_insert` que, si el objeto tiene `inmobiliaria_id` vacío, lo
completa con el tenant actual. Así nadie crea un registro "sin dueño" ni con el
dueño equivocado.

### Capa 3 — Verificación explícita en accesos por ID

`db.session.get(Modelo, id)` **no** pasa por el filtro de la Capa 1 (busca por
clave primaria directo). Todo acceso por ID (editar, ver, descargar, PDF,
exportar) debe validar `obj.inmobiliaria_id == tenant_actual()` o devolver 404.
Se encapsula en un helper único, p. ej. `get_or_404_tenant(Modelo, id)`, y se usa
en todos lados en lugar de `db.session.get`.

> **Por qué las tres capas:** la 1 cubre listados y búsquedas (el 90% de los
> olvidos). La 2 evita datos huérfanos. La 3 blinda el punto que la 1 no cubre
> (acceso directo por ID, que es justo donde se filtran datos ajenos en las apps
> reales). El roadmap exige **pruebas negativas** para verificar las tres.

### ¿De dónde sale el "tenant actual"?

Del `current_user` de Flask-Login (`current_user.inmobiliaria_id`). Se guarda en
un contexto por request. Para procesos sin usuario (robot de gas, tareas
programadas) el tenant se pasa explícito por token/parámetro.

---

## 4. Migración de datos existentes

Tu base actual es de **una** inmobiliaria (la tuya). El plan:

1. Migración Alembic que crea la tabla `Inmobiliaria` y agrega las columnas
   `inmobiliaria_id` **nullable** primero.
2. Crear la inmobiliaria #1 con tus datos actuales (los de "Ajustes").
3. Backfill: `UPDATE ... SET inmobiliaria_id = 1` en todas las tablas.
4. Segunda migración: pasar las columnas a **NOT NULL** + índices + FKs.
5. Asignar todos tus usuarios actuales a la inmobiliaria #1.

Todo con Alembic (ya adoptado), reversible y probado antes en una copia.

---

## 5. Impacto por módulo (qué hay que tocar)

| Módulo | Cambio principal |
|---|---|
| `models.py` | Tabla `Inmobiliaria`; `inmobiliaria_id` en entidades; `TenantMixin` |
| `__init__.py` | Instalar filtro por sesión (Capa 1) y hook de alta (Capa 2) |
| `auth.py` | Login trae el tenant; superadmin aparte |
| Todos los blueprints | Reemplazar `db.session.get(...)` por `get_or_404_tenant(...)` |
| `ajustes.py` | Los datos de la inmobiliaria pasan a ser **por tenant** (no globales) |
| Recibos/PDF/liquidaciones | Usar logo y datos fiscales del tenant; numeración propia |
| `gas.py` (robot) | El importador asocia cada cuenta al tenant correcto |
| Exportar / respaldo | Filtrado por tenant; export completo por inmobiliaria (portabilidad) |
| `usuarios.py` | Alta de usuarios dentro del tenant; roles ampliados (§7) |

---

## 6. Configuración e identidad por inmobiliaria

- **Logo y documentos:** almacenamiento **fuera de la base**, en rutas privadas
  con permiso por tenant (el roadmap lo pide). En Railway: un volumen o un bucket
  (S3/R2). Los recibos y contratos usan el logo y datos fiscales del tenant.
- **Parámetros propios:** mora, comisión, numeración de recibos, moneda por
  defecto — todos por inmobiliaria.

---

## 7. Roles (ampliación pedida por el roadmap)

Hoy: `admin`, `operador`. El roadmap pide sumar: **solo lectura**, **contador**
(ve/exporta lo financiero, no edita contratos) y **soporte limitado**. Se define
una matriz de permisos por rol **dentro** de cada inmobiliaria, más el
**superadmin** de plataforma por encima.

---

## 8. Plan de pruebas de aislamiento (obligatorio)

Pruebas automáticas **negativas** (que deben FALLAR el acceso):

1. Usuario de la inmobiliaria A **no** ve personas/inmuebles/contratos de B en
   ningún listado ni búsqueda.
2. Usuario de A **no** puede abrir por URL un registro de B (ID de B → 404).
3. Usuario de A **no** puede editar, borrar ni descargar PDF/recibo de B.
4. Al crear un registro, queda con el tenant de A (nunca de B).
5. La exportación/respaldo de A no incluye ni una fila de B.
6. El robot de gas de A no pisa datos de B.

Estas pruebas se suman a la batería actual (hoy 56) y son **criterio de salida**
para poder vender (indicador "Aislamiento" del roadmap).

---

## 9. Riesgos y decisiones abiertas

- **Olvidos de filtro:** mitigado por las 3 capas + pruebas negativas. Es el
  riesgo #1 de todo multi-tenant.
- **`db.session.get` por ID:** hay que migrarlos **todos** al helper con verificación. Hacer un inventario y no dejar ninguno.
- **Índices globales vs. por tenant:** los valores ICL/IPC/Casa Propia son
  públicos e iguales para todos → conviene dejarlos **globales** (sin tenant).
  Decisión a confirmar.
- **Almacenamiento de logos/documentos:** elegir volumen de Railway vs. bucket
  externo (S3/Cloudflare R2). Afecta backups y portabilidad.
- **Rendimiento:** índices en `inmobiliaria_id` en todas las tablas para que los
  filtros sean rápidos.
- **Onboarding de un tenant nuevo:** alta de inmobiliaria + primer admin +
  importación Excel. Se diseña como flujo aparte (Fase 3).

---

## 10. Plan de implementación (cuando se apruebe)

1. **Diseño aprobado** (este documento).
2. Migración 1 (Alembic): tabla `Inmobiliaria` + columnas `inmobiliaria_id`
   nullable + backfill a la inmobiliaria #1 con tus datos.
3. Migración 2: NOT NULL + índices + FKs.
4. `TenantMixin` + Capa 1 (filtro por sesión) + Capa 2 (alta automática).
5. Helper `get_or_404_tenant` y reemplazo de todos los `db.session.get`.
6. Config/identidad por tenant (ajustes, logo, numeración, recibos).
7. Roles ampliados + superadmin de plataforma.
8. Batería de **pruebas negativas** de aislamiento.
9. Prueba real con **dos** inmobiliarias de juguete antes de dar por cerrado.

Cada paso deja la app funcionando (tu inmobiliaria opera normal en todo momento).

---

## 11. Qué NO entra en esta etapa

Facturación/suscripciones, autoservicio de alta, portal del propietario,
subdominios por cliente. Son Fase 5. Acá solo garantizamos el **aislamiento
correcto y probado**, que es la base sobre la que se apoya todo lo comercial.
