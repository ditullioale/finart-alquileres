[1mdiff --git a/MANUAL_USUARIO.md b/MANUAL_USUARIO.md[m
[1mindex 3adf280..be75e95 100644[m
[1m--- a/MANUAL_USUARIO.md[m
[1m+++ b/MANUAL_USUARIO.md[m
[36m@@ -39,13 +39,9 @@[m [mEn la barra lateral están las secciones. En el **Inicio** ves de un vistazo:[m
 [m
 ## 5. Contratos[m
 [m
[31m-Dos formas de dar de alta:[m
[31m-[m
[31m-- **Alta directa** (Contratos → + Alta directa): para un alquiler **ya en curso**.[m
[31m-  Cargás fecha de inicio real (aunque sea pasada), precio actual, día de[m
[31m-  vencimiento, mora, **comisión** y método de aumento.[m
[31m-- **Generar contrato** (menú Generador): un **asistente por pasos (wizard)** te[m
[31m-  va guiando:[m
[32m+[m[32mEntrá en **Nuevo contrato** y elegí según lo que necesitás:[m
[32m+[m[32m- **Crear un contrato nuevo:** para un alquiler que todavía vas a iniciar. Un[m
[32m+[m[32m  **asistente por pasos** redacta el documento y lo registra en el sistema:[m
   1. **Partes** — locador/es y locatario/es (podés cargar varios). Incluye[m
      **CUIT** y un botón para calcularlo desde el DNI, y la **consulta al BCRA**[m
      (situación crediticia) directo en la app.[m
[36m@@ -55,6 +51,10 @@[m [mDos formas de dar de alta:[m
      (DNI y recibos de sueldo del locatario y los fiadores).[m
   5. **Revisión** — generás el documento y luego **Guardar contrato en el[m
      sistema**. Queda guardado para reimprimir (opción "Ver contrato").[m
[32m+[m[32m- **Registrar un contrato existente:** para un contrato ya firmado o un alquiler[m
[32m+[m[32m  **ya en curso**. Cargás la fecha de inicio real (aunque sea pasada), precio[m
[32m+[m[32m  actual, día de vencimiento, mora, **comisión** y método de aumento. Esta opción[m
[32m+[m[32m  no redacta un documento legal nuevo.[m
 [m
 En la lista, cada fila tiene **💵 Cobrar** y un menú **⋯ Más** (Ver, Ver contrato,[m
 Rescindir, Renovar, Eliminar). **Rescindir** conserva el historial y libera el[m
[1mdiff --git a/README.md b/README.md[m
[1mindex 34b15de..76eb6a7 100644[m
[1m--- a/README.md[m
[1m+++ b/README.md[m
[36m@@ -16,11 +16,12 @@[m [malgunas pantallas.[m
 - **Personas** — propietarios e inquilinos (DNI, CUIT, contacto, condición IVA).[m
 - **Inmuebles** — datos, estado (disponible/alquilado/reservado), comisión, N° de[m
   cuenta de Litoral Gas.[m
[31m-- **Contratos** — alta directa (para alquileres en curso) y un **generador de[m
[31m-  contratos tipo asistente (wizard) de 5 pasos** que da de alta el contrato en el[m
[31m-  sistema. Soporta **varios locadores/locatarios**, **CUIT** (con cálculo desde el[m
[31m-  DNI) y **consulta al BCRA** (situación crediticia) integrada. Editable, con[m
[31m-  rescindir / renovar / eliminar.[m
[32m+[m[32m- **Contratos** — una entrada única, **Nuevo contrato**, permite elegir entre[m
[32m+[m[32m  **crear y redactar un contrato nuevo** con un asistente de 5 pasos, o **registrar[m
[32m+[m[32m  un contrato existente** para administrar un alquiler ya firmado o en curso.[m
[32m+[m[32m  Soporta **varios locadores/locatarios**, **CUIT** (con cálculo desde el DNI) y[m
[32m+[m[32m  **consulta al BCRA** (situación crediticia) integrada. Editable, con rescindir /[m
[32m+[m[32m  renovar / eliminar.[m
 - **Documentación de contratos** — subir y ver DNI, recibos de sueldo, etc.[m
   (PDF/imagen), guardados en la base junto al contrato.[m
 - **Cobranzas** — panel mensual tipo checklist con **vencimiento visible**;[m
[1mdiff --git a/app/blueprints/contratos.py b/app/blueprints/contratos.py[m
[1mindex 69d18bb..7d5b42b 100644[m
[1m--- a/app/blueprints/contratos.py[m
[1m+++ b/app/blueprints/contratos.py[m
[36m@@ -69,6 +69,13 @@[m [mdef react():[m
     return redirect(url_for("contratos.listar"))[m
 [m
 [m
[32m+[m[32m@contratos_bp.route("/crear")[m
[32m+[m[32m@login_required[m
[32m+[m[32mdef crear():[m
[32m+[m[32m    """Permite elegir el flujo correcto antes de iniciar un contrato."""[m
[32m+[m[32m    return render_template("contratos/elegir_tipo.html")[m
[32m+[m
[32m+[m
 @contratos_bp.route("/<int:cid>/documento")[m
 @login_required[m
 def documento(cid):[m
[36m@@ -184,7 +191,7 @@[m [mdef eliminar_documento(doc_id):[m
 [m
 [m
 # --------------------------------------------------------------------------- #[m
[31m-#  Alta directa / edición (formulario manual)[m
[32m+[m[32m#  Registro de contrato existente / edición (formulario manual)[m
 # --------------------------------------------------------------------------- #[m
 def _opciones():[m
     return dict([m
[36m@@ -288,21 +295,24 @@[m [mdef nuevo():[m
         _leer_form(c)[m
         _leer_fiadores(c)   # cargar fiadores antes de validar, para no perderlos si falla[m
         _leer_copartes(c)[m
[32m+[m[32m        renovar_de = parse_num(request.form.get("renovar_de"), entero=True)[m
         error = _validar(c)[m
         if error:[m
             flash(error, "error")[m
[31m-            return render_template("contratos/form.html", c=c, **_opciones())[m
[32m+[m[32m            return render_template("contratos/form.html", c=c, renovar_de=renovar_de,[m
[32m+[m[32m                                   **_opciones())[m
         db.session.add(c)[m
         _marcar_alquilado(c)[m
         # Si es una renovación, finalizar el contrato anterior.[m
[31m-        renovar_de = parse_num(request.form.get("renovar_de"), entero=True)[m
         if renovar_de:[m
             old = db.session.get(Contrato, renovar_de)[m
             if old:[m
                 old.estado = "Finalizado"[m
         db.session.commit()[m
[31m-        flash("Contrato dado de alta correctamente." +[m
[31m-              (" El contrato anterior quedó finalizado." if renovar_de else ""), "ok")[m
[32m+[m[32m        if renovar_de:[m
[32m+[m[32m            flash("Renovación registrada correctamente. El contrato anterior quedó finalizado.", "ok")[m
[32m+[m[32m        else:[m
[32m+[m[32m            flash("Contrato existente registrado correctamente.", "ok")[m
         return redirect(url_for("contratos.ver", cid=c.id))[m
     c = Contrato(fecha_inicio=date.today(), metodo_ajuste="porcentaje",[m
                  moneda="Pesos", estado="Vigente", dia_vencimiento=10)[m
[1mdiff --git a/app/templates/base.html b/app/templates/base.html[m
[1mindex e34a3e3..96ba8e3 100644[m
[1m--- a/app/templates/base.html[m
[1m+++ b/app/templates/base.html[m
[36m@@ -58,7 +58,7 @@[m
       <button type="button" class="nav-search" onclick="abrirBuscar()">[m
         <span class="i">{{ icon('search') }}</span> <span>Buscar…</span> <kbd>Ctrl&nbsp;K</kbd></button>[m
       <a class="nav-item {{ 'active' if bp=='main' }}" href="{{ url_for('main.index') }}"><span class="i">{{ icon('home') }}</span> Inicio</a>[m
[31m-      <a class="nav-item {{ 'active' if bp=='contratos' and ep!='contratos.generador' }}" href="{{ url_for('contratos.listar') }}"><span class="i">{{ icon('file-text') }}</span> Contratos</a>[m
[32m+[m[32m      <a class="nav-item {{ 'active' if bp=='contratos' and ep not in ('contratos.generador','contratos.crear') }}" href="{{ url_for('contratos.listar') }}"><span class="i">{{ icon('file-text') }}</span> Contratos</a>[m
       <a class="nav-item {{ 'active' if bp=='cobros' }}" href="{{ url_for('cobros.index') }}"><span class="i">{{ icon('banknote') }}</span> Cobranzas</a>[m
       <a class="nav-item {{ 'active' if bp=='liquidaciones' }}" href="{{ url_for('liquidaciones.index') }}"><span class="i">{{ icon('receipt') }}</span> Liquidaciones</a>[m
       <a class="nav-item {{ 'active' if bp=='aumentos' and 'indice' not in ep }}" href="{{ url_for('aumentos.index') }}"><span class="i">{{ icon('trending-up') }}</span> Aumentos[m
[36m@@ -68,7 +68,7 @@[m
       <a class="nav-item {{ 'active' if bp=='personas' }}" href="{{ url_for('personas.listar') }}"><span class="i">{{ icon('users') }}</span> Personas</a>[m
 [m
       <div class="nav-sec">Herramientas</div>[m
[31m-      <a class="nav-item {{ 'active' if ep=='contratos.generador' }}" href="{{ url_for('contratos.generador') }}"><span class="i">{{ icon('file-pen') }}</span> Generar contrato</a>[m
[32m+[m[32m      <a class="nav-item {{ 'active' if ep in ('contratos.crear','contratos.generador') }}" href="{{ url_for('contratos.crear') }}"><span class="i">{{ icon('file-pen') }}</span> Nuevo contrato</a>[m
       <a class="nav-item {{ 'active' if ep in ('recibos.manuales','recibos.manual_nuevo','recibos.manual_ver') }}" href="{{ url_for('recibos.manuales') }}"><span class="i">{{ icon('receipt') }}</span> Recibos manuales</a>[m
       <a class="nav-item {{ 'active' if 'pagare_manual' in ep or ep=='recibos.pagares_manuales' }}" href="{{ url_for('recibos.pagares_manuales') }}"><span class="i">{{ icon('scroll') }}</span> Pagarés manuales</a>[m
       <a class="nav-item {{ 'active' if bp=='aumentos' and 'indice' in ep }}" href="{{ url_for('aumentos.indices') }}"><span class="i">{{ icon('bar-chart') }}</span> Índices</a>[m
[1mdiff --git a/app/templates/contratos/form.html b/app/templates/contratos/form.html[m
[1mindex 2d39da9..e6d6305 100644[m
[1m--- a/app/templates/contratos/form.html[m
[1m+++ b/app/templates/contratos/form.html[m
[36m@@ -1,15 +1,16 @@[m
 {% extends "base.html" %}[m
[31m-{% block title %}{{ 'Editar' if c.id else 'Alta directa de' }} contrato{% endblock %}[m
[32m+[m[32m{% set es_renovacion = renovar_de|default(None) %}[m
[32m+[m[32m{% block title %}{{ 'Editar contrato' if c.id else ('Renovar contrato' if es_renovacion else 'Registrar contrato existente') }}{% endblock %}[m
 {% block content %}[m
[31m-<div class="pagehead"><h1>{{ 'Editar contrato' if c.id else 'Alta directa de contrato' }}</h1></div>[m
[31m-[m
[31m-{% if not c.id %}[m
[32m+[m[32m<div class="pagehead"><h1>{{ 'Editar contrato' if c.id else ('Renovar contrato' if es_renovacion else 'Registrar contrato existente') }}</h1></div>[m
[32m+[m[32m{% if not c.id and not es_renovacion %}[m
 <div class="flash ok" style="background:#eaf0fb;border-color:#b9cdf0;color:#274b8f">[m
[31m-  Usá esta alta para cargar un alquiler <b>ya en curso</b>: podés poner la fecha de inicio real[m
[31m-  (aunque sea pasada) y el precio actual ya aumentado. El historial de pagos se carga luego en Cobros.[m
[32m+[m[32m  <b>Esta opción no redacta un documento legal nuevo.</b> Usala para registrar un contrato[m
[32m+[m[32m  ya firmado o un alquiler en curso. Podés cargar la fecha de inicio real, aunque sea pasada,[m
[32m+[m[32m  y el precio actual ya aumentado. Si necesitás redactar el contrato desde cero,[m
[32m+[m[32m  <a href="{{ url_for('contratos.generador') }}"><b>abrí el asistente de contrato nuevo</b></a>.[m
 </div>[m
 {% endif %}[m
[31m-[m
 <form method="post" action="{{ url_for('contratos.nuevo') if renovar_de else '' }}" class="cardform">[m
   {% if renovar_de %}<input type="hidden" name="renovar_de" value="{{ renovar_de }}">{% endif %}[m
   <h2>Partes e inmueble</h2>[m
[1mdiff --git a/app/templates/contratos/list.html b/app/templates/contratos/list.html[m
[1mindex 9b98a75..8aaa833 100644[m
[1m--- a/app/templates/contratos/list.html[m
[1m+++ b/app/templates/contratos/list.html[m
[36m@@ -13,8 +13,7 @@[m
     <p class="sub">Alquileres cargados. Desde acá registrás cobros y aumentos.</p>[m
   </div>[m
   <div class="quick">[m
[31m-    <a class="btn" href="{{ url_for('contratos.nuevo') }}">+ Alta directa</a>[m
[31m-    <a class="btn sec" href="{{ url_for('contratos.generador') }}">📝 Generar contrato</a>[m
[32m+[m[32m    <a class="btn" href="{{ url_for('contratos.crear') }}">+ Nuevo contrato</a>[m
   </div>[m
 </div>[m
 [m
[36m@@ -82,8 +81,8 @@[m
 <div class="empty-state">[m
   <div class="em">📄</div>[m
   <h3>No hay contratos {{ 'con ese filtro' if q or estado else 'todavía' }}</h3>[m
[31m-  <p>Cargá un alquiler en curso con “Alta directa”, o generá un contrato nuevo con el asistente.</p>[m
[31m-  <a class="btn" href="{{ url_for('contratos.nuevo') }}">+ Alta directa</a>[m
[32m+[m[32m  <p>Empezá indicando si necesitás crear un documento nuevo o registrar un contrato existente.</p>[m
[32m+[m[32m  <a class="btn" href="{{ url_for('contratos.crear') }}">+ Nuevo contrato</a>[m
 </div>[m
 {% endif %}[m
 [m
[1mdiff --git a/app/templates/contratos/ver.html b/app/templates/contratos/ver.html[m
[1mindex 63d3cad..59faa8d 100644[m
[1m--- a/app/templates/contratos/ver.html[m
[1m+++ b/app/templates/contratos/ver.html[m
[36m@@ -54,7 +54,7 @@[m
   <div class="grid2">[m
     <div><span class="k">Inmueble</span><br>{{ (c.inmueble.codigo ~ ' · ' if c.inmueble.codigo else '') }}{{ c.inmueble.direccion }}</div>[m
     <div><span class="k">Estado</span><br><span class="badge {{ c.estado|lower }}">{{ c.estado }}</span>[m
[31m-         {% if c.origen=='generador' %}<span class="badge reservado">Desde generador</span>{% endif %}</div>[m
[32m+[m[32m         {% if c.origen=='generador' %}<span class="badge reservado">Documento creado en FINART</span>{% endif %}</div>[m
     <div><span class="k">{{ 'Locatarios' if c.colocatarios else 'Inquilino' }}</span><br>[m
       <span style="display:inline-flex;align-items:center;gap:8px">{{ c.inquilino.nombre if c.inquilino else '—' }}[m
         {% if c.inquilino %}{{ wa_icon(c.inquilino.telefono, "Hola " ~ c.inquilino.nombre ~ "! Te escribo por el alquiler de " ~ c.inmueble.direccion ~ ".") }}{% endif %}[m
[1mdiff --git a/app/templates/main/index.html b/app/templates/main/index.html[m
[1mindex 3de893c..9edbb7f 100644[m
[1m--- a/app/templates/main/index.html[m
[1m+++ b/app/templates/main/index.html[m
[36m@@ -94,8 +94,7 @@[m
   <div class="panel">[m
     <h2>Accesos rápidos</h2>[m
     <div class="quick">[m
[31m-      <a class="btn" href="{{ url_for('contratos.nuevo') }}">{{ icon('plus', 16) }} Nuevo contrato</a>[m
[31m-      <a class="btn" href="{{ url_for('contratos.generador') }}">{{ icon('file-pen', 16) }} Generar contrato</a>[m
[32m+[m[32m      <a class="btn" href="{{ url_for('contratos.crear') }}">{{ icon('plus', 16) }} Nuevo contrato</a>[m
       <a class="btn sec" href="{{ url_for('inmuebles.nuevo') }}">{{ icon('plus', 16) }} Nuevo inmueble</a>[m
     </div>[m
   </div>[m
