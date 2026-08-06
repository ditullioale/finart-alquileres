# Multiempresa — próximos pasos (para retomar)

_Nota rápida para acordarnos por dónde seguir. La base del multiempresa ya está
hecha y probada; esto es lo que queda del plan._

## Dónde estamos hoy (ya funciona)

- Cada inmobiliaria ve **solo sus datos**, mediante un filtro automático por sesión.
- Todas las tablas comerciales tienen dueño (`inmobiliaria_id`).
- Existe el **superadmin de plataforma**: alta y aprobación de inmobiliarias, link de invitación.
- La configuración y el **facturador ARCA** son por inmobiliaria (aislados y cifrados).
- **83 pruebas de aislamiento** verifican que una inmobiliaria no pueda ver ni abrir
  datos de otra. Todas en verde.

## Opciones para el próximo paso (elegir una cuando retomemos)

1. **Roles nuevos por inmobiliaria.** Sumar "solo lectura", "contador" (ve/exporta lo
   financiero, no edita contratos) y "soporte limitado", con una matriz clara de quién
   puede ver y tocar qué. Hoy solo hay admin/operador.

2. **Identidad propia en documentos.** Que cada inmobiliaria tenga su logo, datos
   fiscales y numeración propia en recibos, liquidaciones y PDF. Hace que cada una
   sienta el sistema como "suyo".

3. **Doble candado + prueba con 2 inmobiliarias.** Reforzar los accesos por ID
   (`get_or_404_tenant` en todo el código) y hacer la prueba final con dos inmobiliarias
   de juguete, para dejar el aislamiento cerrado con doble candado antes de vender.

4. **Panel de superadmin.** Métricas, alta/suspensión de inmobiliarias, estado de cada
   cliente. Ampliar lo que ya existe en Plataforma.

## Pendiente aparte (no urgente)

- Confirmar en los logs de Railway que el último deploy aplicó las dos migraciones
  nuevas (`d5e6f7a8b9c0` y `e6f7a8b9c0d1`).
- Limpiar la base de práctica local (Postgres viejo en tu PC) o volver a SQLite para
  desarrollo. No afecta a producción.
