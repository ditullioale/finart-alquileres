"""ABM de Contratos + integración con el generador de contratos."""
from pathlib import Path
from datetime import date

from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, abort, jsonify, Response)
from flask_login import login_required
from sqlalchemy.orm import aliased

from .. import db
from ..models import Contrato, Inmueble, Persona, Fiador
from ..utils import add_months, parse_fecha, parse_num, INDICE_MAP, INDICE_NOMBRE

contratos_bp = Blueprint("contratos", __name__, url_prefix="/contratos")

METODOS = [("porcentaje", "Por porcentaje fijo"),
           ("indice", "Por índice oficial"),
           ("sin_ajuste", "Sin ajuste")]
INDICES = [("ICL", "ICL (BCRA)"), ("IPC", "IPC (INDEC)"), ("CasaPropia", "Casa Propia")]
ESTADOS = ["Vigente", "Finalizado", "Rescindido"]


# --------------------------------------------------------------------------- #
#  Listado y vista
# --------------------------------------------------------------------------- #
@contratos_bp.route("/")
@login_required
def listar():
    q = request.args.get("q", "").strip()
    estado = request.args.get("estado", "")
    Inq = aliased(Persona)
    Prop = aliased(Persona)
    query = (Contrato.query.join(Inmueble)
             .outerjoin(Inq, Contrato.inquilino_id == Inq.id)
             .outerjoin(Prop, Contrato.propietario_id == Prop.id))
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Inmueble.direccion.ilike(like),
                                    Inmueble.codigo.ilike(like),
                                    Contrato.numero.ilike(like),
                                    Inq.nombre.ilike(like),
                                    Prop.nombre.ilike(like)))
    if estado:
        query = query.filter(Contrato.estado == estado)

    sort = request.args.get("sort", "")
    direccion = request.args.get("dir", "asc")
    cols = {"inquilino": db.func.lower(Inq.nombre), "propietario": db.func.lower(Prop.nombre),
            "inmueble": db.func.lower(Inmueble.direccion), "precio": Contrato.precio_actual,
            "ajuste": Contrato.metodo_ajuste, "estado": Contrato.estado}
    col = cols.get(sort)
    if col is not None:
        query = query.order_by(col.desc() if direccion == "desc" else col.asc())
    else:
        query = query.order_by(Contrato.fecha_inicio.desc())
    contratos = query.all()
    return render_template("contratos/list.html", contratos=contratos,
                           q=q, estado=estado, estados=ESTADOS)


@contratos_bp.route("/react")
@login_required
def react():
    return render_template("contratos/react.html")


@contratos_bp.route("/<int:cid>/documento")
@login_required
def documento(cid):
    c = db.session.get(Contrato, cid) or abort(404)
    if not c.documento_html:
        flash("Este contrato no tiene un documento generado guardado.", "error")
        return redirect(url_for("contratos.ver", cid=c.id))
    volver = url_for("contratos.ver", cid=c.id)
    pagina = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Contrato — {c.inmueble.direccion if c.inmueble else c.id}</title>
<style>
  body{{font-family:'Times New Roman',Georgia,serif;color:#111;margin:0;background:#f0f0f0}}
  .toolbar{{background:#12263f;color:#fff;padding:10px 16px;display:flex;gap:10px;align-items:center;font-family:Arial}}
  .toolbar a{{color:#cfe0f5;text-decoration:none}}
  .toolbar button{{background:#2f6fed;color:#fff;border:0;border-radius:7px;padding:8px 16px;font-weight:600;cursor:pointer}}
  .hoja{{max-width:820px;margin:16px auto;background:#fff;padding:40px 46px;line-height:1.55;text-align:justify}}
  .hoja h2{{text-align:center}} .hoja ol li{{margin:9px 0}}
  @media print{{ .toolbar{{display:none}} body{{background:#fff}} .hoja{{margin:0;max-width:none;box-shadow:none}} }}
</style></head><body>
<div class="toolbar"><a href="{volver}">← Volver</a><span style="flex:1"></span>
  <button onclick="window.print()">🖨️ Imprimir / Guardar PDF</button></div>
<div class="hoja">{c.documento_html}</div>
</body></html>"""
    return Response(pagina, mimetype="text/html")


@contratos_bp.route("/<int:cid>")
@login_required
def ver(cid):
    contrato = db.session.get(Contrato, cid) or abort(404)
    return render_template("contratos/ver.html", c=contrato,
                           indice_nombre=INDICE_NOMBRE)


# --------------------------------------------------------------------------- #
#  Alta directa / edición (formulario manual)
# --------------------------------------------------------------------------- #
def _opciones():
    return dict(
        inmuebles=Inmueble.query.order_by(Inmueble.codigo).all(),
        inquilinos=Persona.query.filter_by(es_inquilino=True).order_by(Persona.nombre).all(),
        propietarios=Persona.query.filter_by(es_propietario=True).order_by(Persona.nombre).all(),
        metodos=METODOS, indices=INDICES, estados=ESTADOS,
    )


def _leer_form(c: Contrato):
    c.numero = request.form.get("numero", "").strip()
    c.inmueble_id = parse_num(request.form.get("inmueble_id"), entero=True)
    c.inquilino_id = parse_num(request.form.get("inquilino_id"), entero=True)
    c.propietario_id = parse_num(request.form.get("propietario_id"), entero=True)
    c.fecha_inicio = parse_fecha(request.form.get("fecha_inicio"))
    c.duracion_meses = parse_num(request.form.get("duracion_meses"), entero=True)
    c.fecha_fin = parse_fecha(request.form.get("fecha_fin"))
    if not c.fecha_fin and c.fecha_inicio and c.duracion_meses:
        c.fecha_fin = add_months(c.fecha_inicio, c.duracion_meses)
    c.precio_inicial = parse_num(request.form.get("precio_inicial"))
    c.precio_actual = parse_num(request.form.get("precio_actual")) or c.precio_inicial
    c.moneda = request.form.get("moneda", "Pesos")
    c.dia_vencimiento = parse_num(request.form.get("dia_vencimiento"), entero=True)
    c.mora_diaria_pct = parse_num(request.form.get("mora_diaria_pct")) or 0
    c.comision_pct = parse_num(request.form.get("comision_pct"))
    c.metodo_ajuste = request.form.get("metodo_ajuste", "porcentaje")
    c.indice_tipo = request.form.get("indice_tipo") or None
    c.ajuste_cada_meses = parse_num(request.form.get("ajuste_cada_meses"), entero=True)
    c.porcentaje_ajuste = parse_num(request.form.get("porcentaje_ajuste"))
    c.estado = request.form.get("estado", "Vigente")
    c.observaciones = request.form.get("observaciones", "").strip()


def _leer_fiadores(c: Contrato):
    """Reemplaza los fiadores del contrato con los enviados en el form."""
    c.fiadores.clear()
    nombres = request.form.getlist("fiador_nombre")
    dnis = request.form.getlist("fiador_dni")
    doms = request.form.getlist("fiador_dom")
    tels = request.form.getlist("fiador_tel")
    mails = request.form.getlist("fiador_email")
    solvs = request.form.getlist("fiador_solvencia")
    for i, nombre in enumerate(nombres):
        if nombre.strip():
            c.fiadores.append(Fiador(
                nombre=nombre.strip(),
                dni=dnis[i].strip() if i < len(dnis) else "",
                domicilio=doms[i].strip() if i < len(doms) else "",
                telefono=tels[i].strip() if i < len(tels) else "",
                email=mails[i].strip() if i < len(mails) else "",
                solvencia=solvs[i].strip() if i < len(solvs) else "",
            ))


def _leer_copartes(c: Contrato):
    """Carga co-locatarios y co-locadores (personas adicionales de cada lado)
    a partir de los IDs enviados en el formulario. Ignora vacíos, duplicados y
    a los titulares para no repetirlos."""
    def personas_de(campo, excluir_id):
        vistos, out = set(), []
        for v in request.form.getlist(campo):
            pid = parse_num(v, entero=True)
            if not pid or pid == excluir_id or pid in vistos:
                continue
            per = db.session.get(Persona, pid)
            if per:
                vistos.add(pid)
                out.append(per)
        return out

    c.colocatarios = personas_de("colocatario_id", c.inquilino_id)
    c.colocadores = personas_de("colocador_id", c.propietario_id)


def _marcar_alquilado(c: Contrato):
    if c.estado == "Vigente" and c.inmueble_id:
        inm = db.session.get(Inmueble, c.inmueble_id)
        if inm and inm.estado != "Alquilado":
            inm.estado = "Alquilado"


def _liberar_si_sin_contrato(inmueble_id, excluir_id=None):
    """Marca un inmueble como Disponible si ya no tiene ningún contrato vigente."""
    inm = db.session.get(Inmueble, inmueble_id)
    if not inm:
        return
    q = Contrato.query.filter(Contrato.inmueble_id == inmueble_id,
                              Contrato.estado == "Vigente")
    if excluir_id:
        q = q.filter(Contrato.id != excluir_id)
    if q.first() is None and inm.estado == "Alquilado":
        inm.estado = "Disponible"


@contratos_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    if request.method == "POST":
        c = Contrato()
        _leer_form(c)
        _leer_fiadores(c)   # cargar fiadores antes de validar, para no perderlos si falla
        _leer_copartes(c)
        error = _validar(c)
        if error:
            flash(error, "error")
            return render_template("contratos/form.html", c=c, **_opciones())
        db.session.add(c)
        _marcar_alquilado(c)
        # Si es una renovación, finalizar el contrato anterior.
        renovar_de = parse_num(request.form.get("renovar_de"), entero=True)
        if renovar_de:
            old = db.session.get(Contrato, renovar_de)
            if old:
                old.estado = "Finalizado"
        db.session.commit()
        flash("Contrato dado de alta correctamente." +
              (" El contrato anterior quedó finalizado." if renovar_de else ""), "ok")
        return redirect(url_for("contratos.ver", cid=c.id))
    c = Contrato(fecha_inicio=date.today(), metodo_ajuste="porcentaje",
                 moneda="Pesos", estado="Vigente", dia_vencimiento=10)
    return render_template("contratos/form.html", c=c, **_opciones())


@contratos_bp.route("/<int:cid>/editar", methods=["GET", "POST"])
@login_required
def editar(cid):
    c = db.session.get(Contrato, cid) or abort(404)
    if request.method == "POST":
        inm_anterior = c.inmueble_id
        _leer_form(c)
        _leer_fiadores(c)
        _leer_copartes(c)
        error = _validar(c)
        if error:
            flash(error, "error")
            return render_template("contratos/form.html", c=c, **_opciones())
        _marcar_alquilado(c)
        # Si se cambió el inmueble, liberar el anterior si ya no tiene contrato vigente.
        if inm_anterior and inm_anterior != c.inmueble_id:
            _liberar_si_sin_contrato(inm_anterior, excluir_id=c.id)
        db.session.commit()
        flash("Contrato actualizado.", "ok")
        return redirect(url_for("contratos.ver", cid=c.id))
    return render_template("contratos/form.html", c=c, **_opciones())


@contratos_bp.route("/<int:cid>/renovar")
@login_required
def renovar(cid):
    """Precarga un contrato nuevo con los datos del anterior, para renovarlo.
    Al guardar, el contrato viejo queda Finalizado."""
    from datetime import timedelta
    old = db.session.get(Contrato, cid) or abort(404)
    inicio = (old.fecha_fin + timedelta(days=1)) if old.fecha_fin else date.today()
    c = Contrato(
        inmueble_id=old.inmueble_id, inquilino_id=old.inquilino_id,
        propietario_id=old.propietario_id, fecha_inicio=inicio,
        duracion_meses=old.duracion_meses,
        precio_inicial=old.precio_actual or old.precio_inicial,
        precio_actual=old.precio_actual or old.precio_inicial,
        moneda=old.moneda, dia_vencimiento=old.dia_vencimiento,
        mora_diaria_pct=old.mora_diaria_pct, comision_pct=old.comision_pct,
        metodo_ajuste=old.metodo_ajuste, indice_tipo=old.indice_tipo,
        ajuste_cada_meses=old.ajuste_cada_meses, porcentaje_ajuste=old.porcentaje_ajuste,
        estado="Vigente")
    if inicio and c.duracion_meses:
        c.fecha_fin = add_months(inicio, c.duracion_meses)
    for f in old.fiadores:
        c.fiadores.append(Fiador(nombre=f.nombre, dni=f.dni, domicilio=f.domicilio,
                                 telefono=f.telefono, email=f.email, solvencia=f.solvencia))
    # Arrastrar co-firmantes de cada lado a la renovación.
    c.colocatarios = list(old.colocatarios)
    c.colocadores = list(old.colocadores)
    flash("Renovación: revisá y actualizá lo que haga falta (fechas, precio, etc.) y guardá. "
          "El contrato anterior quedará finalizado automáticamente.", "ok")
    return render_template("contratos/form.html", c=c, renovar_de=old.id, **_opciones())


@contratos_bp.route("/<int:cid>/rescindir", methods=["POST"])
@login_required
def rescindir(cid):
    c = db.session.get(Contrato, cid) or abort(404)
    c.estado = "Rescindido"
    hoy = date.today()
    if not c.fecha_fin or c.fecha_fin > hoy:
        c.fecha_fin = hoy
    if c.inmueble and c.inmueble.estado == "Alquilado":
        c.inmueble.estado = "Disponible"
    db.session.commit()
    flash("Contrato rescindido. El inmueble quedó disponible; el historial de pagos se conserva.", "ok")
    return redirect(url_for("contratos.ver", cid=c.id))


@contratos_bp.route("/<int:cid>/eliminar", methods=["POST"])
@login_required
def eliminar(cid):
    c = db.session.get(Contrato, cid) or abort(404)
    if c.pagos:
        flash("No se puede eliminar: el contrato tiene pagos registrados. Usá “Rescindir”.", "error")
        return redirect(url_for("contratos.ver", cid=c.id))
    if c.inmueble and c.inmueble.estado == "Alquilado":
        c.inmueble.estado = "Disponible"
    db.session.delete(c)
    db.session.commit()
    flash("Contrato eliminado.", "ok")
    return redirect(url_for("contratos.listar"))


def _validar(c: Contrato):
    if not c.inmueble_id:
        return "Elegí un inmueble."
    if not c.inquilino_id:
        return "Elegí un inquilino."
    if not c.fecha_inicio:
        return "La fecha de inicio es obligatoria."
    if not c.precio_inicial or c.precio_inicial <= 0:
        return "El precio inicial debe ser mayor a 0."
    if c.metodo_ajuste == "indice" and not c.indice_tipo:
        return "Elegí el índice para el método por índice."
    if c.metodo_ajuste == "porcentaje" and not c.porcentaje_ajuste:
        return "Indicá el porcentaje de ajuste."
    # Fechas coherentes.
    if c.fecha_fin and c.fecha_inicio and c.fecha_fin <= c.fecha_inicio:
        return "La fecha de fin debe ser posterior a la de inicio."
    if c.dia_vencimiento is not None and not (1 <= c.dia_vencimiento <= 31):
        return "El día de vencimiento debe estar entre 1 y 31."
    # Un solo contrato Vigente por inmueble.
    if c.estado == "Vigente" and c.inmueble_id:
        q = Contrato.query.filter(Contrato.inmueble_id == c.inmueble_id,
                                  Contrato.estado == "Vigente")
        if c.id:
            q = q.filter(Contrato.id != c.id)
        otro = q.first()
        if otro:
            inq = otro.inquilino.nombre if otro.inquilino else "otro inquilino"
            return (f"Ese inmueble ya tiene un contrato vigente (con {inq}). "
                    "Finalizá o rescindí el anterior antes de cargar uno nuevo.")
    # Número de contrato único (si se cargó).
    if c.numero:
        q = Contrato.query.filter(Contrato.numero == c.numero)
        if c.id:
            q = q.filter(Contrato.id != c.id)
        if q.first():
            return f"Ya existe un contrato con el número {c.numero}. Usá otro."
    return None


# --------------------------------------------------------------------------- #
#  Integración con el generador de contratos
# --------------------------------------------------------------------------- #
def _generador_html():
    """Lee el generador original y le inyecta la barra + botón de guardado."""
    ruta = Path(__file__).resolve().parents[2] / "app" / "generador_base.html"
    html = ruta.read_text(encoding="utf-8")

    save_url = url_for("contratos.desde_generador")
    volver_url = url_for("contratos.listar")
    api_url = url_for("contratos.api_personas")
    api_inm = url_for("contratos.api_inmuebles")
    barra = f"""
    <div style="position:sticky;top:0;z-index:50;display:flex;gap:10px;align-items:center;
                background:#12263f;color:#fff;padding:9px 16px">
      <a href="{volver_url}" style="color:#cfe0f5;text-decoration:none;font-size:14px">← Volver al sistema</a>
      <span style="flex:1"></span>
      <button onclick="guardarEnSistema()" style="background:#1f9d55;color:#fff;border:0;
              border-radius:8px;padding:9px 16px;font-size:14px;font-weight:600;cursor:pointer">
        💾 Guardar contrato en el sistema</button>
    </div>
    <div id="sysMsg" style="display:none;padding:10px 16px;font-size:14px"></div>
    """

    script = """
    <script>
    const SAVE_URL = "%s";
    function guardarEnSistema(){
      // Si el documento no fue generado, avisar y ofrecer generarlo primero.
      const cont = document.getElementById('contrato');
      const generado = cont && cont.querySelector('ol');
      if(!generado){
        const r = confirm('Todavía no generaste el documento. Sin él, el contrato se guarda pero no vas a poder verlo/imprimirlo después.\n\nAceptar: generar y guardar ahora.\nCancelar: guardar igual (sin documento).');
        if(r){ generar(); }
      }
      const g = id => (document.getElementById(id)?.value || '').trim();
      const fiadores = [...document.querySelectorAll('#fiadores .card')].map(c=>({
        nombre:c.querySelector('.f-nombre')?.value.trim(),
        dni:c.querySelector('.f-dni')?.value.trim(),
        dom:c.querySelector('.f-dom')?.value.trim(),
        email:c.querySelector('.f-email')?.value.trim(),
        tel:c.querySelector('.f-tel')?.value.trim(),
      })).filter(f=>f.nombre);
      const data = {
        loc:{nombre:g('locNombre'),dni:g('locDni'),dom:g('locDom'),email:g('locEmail')},
        lat:{nombre:g('latNombre'),dni:g('latDni'),cuil:g('latCuil'),dom:g('latDom'),
             email:g('latEmail'),genero:g('latGenero')},
        coLoc:(typeof getCoLoc==='function'?getCoLoc():[]),
        coLat:(typeof getCoLat==='function'?getCoLat():[]),
        inm:{dir:g('inmDir'),cochera:g('inmCochera'),ciudad:g('inmCiudad'),
             provincia:g('inmProvincia'),desc:g('inmDesc')},
        econ:{plazo:g('plazo'),canon:g('canon'),ajusteMeses:g('ajusteMeses'),
              ajusteIdx:g('ajusteIdx'),pagoDesde:g('pagoDesde'),pagoHasta:g('pagoHasta'),
              punitorio:g('punitorio'),fechaFirma:g('fechaFirma')},
        fiadores:fiadores,
        documento:(document.getElementById('contrato')?.innerHTML||''),
        pagares:(document.getElementById('pagares')?.innerHTML||'')
      };
      const box = document.getElementById('sysMsg');
      box.style.display='block'; box.style.background='#fff8e6'; box.style.color='#8a5a00';
      box.textContent='Guardando en el sistema…';
      fetch(SAVE_URL,{method:'POST',headers:{'Content-Type':'application/json'},
            credentials:'same-origin',body:JSON.stringify(data)})
        .then(r=>r.json()).then(d=>{
          if(d.ok){ box.style.background='#eefaf1'; box.style.color='#14663a';
            box.innerHTML = '✅ '+d.mensaje+' <a href="'+d.ver_url+'" style="color:#14663a;font-weight:700">Ver contrato ▸</a>';
          } else { box.style.background='#fdecec'; box.style.color='#9c2020';
            box.textContent = '⚠️ '+(d.mensaje||'No se pudo guardar.'); }
        }).catch(e=>{ box.style.background='#fdecec'; box.style.color='#9c2020';
          box.textContent='⚠️ Error de conexión: '+e.message; });
    }
    </script>
    """ % save_url

    autocomplete = """
    <style>
      .ac-box{position:fixed;background:#fff;border:1px solid #cfd8e3;border-radius:8px;
        box-shadow:0 8px 20px rgba(0,0,0,.14);z-index:99999;max-height:250px;overflow:auto;font-size:13px}
      .ac-item{padding:8px 11px;cursor:pointer;border-bottom:1px solid #f0f3f8}
      .ac-item:hover{background:#eef3fb}
      .ac-item small{color:#6b7890}
      .ac-empty{padding:8px 11px;color:#8a5a00}
      .ac-hint{font-size:11px;color:#2f6fed;margin-top:3px}
    </style>
    <script>
    const API_PER = "%s";
    const API_INM = "%s";
    (function(){
      function deb(fn,ms){let t;return function(){clearTimeout(t);t=setTimeout(fn,ms);};}
      function setv(id,v){const e=document.getElementById(id);if(e)e.value=v||'';}
      function fillLoc(p){setv('locNombre',p.nombre);setv('locDni',p.dni);setv('locDom',p.domicilio);setv('locEmail',p.email);}
      function fillLat(p){setv('latNombre',p.nombre);setv('latDni',p.dni);setv('latCuil',p.cuit);setv('latDom',p.domicilio);setv('latEmail',p.email);}
      function fillInm(p){setv('inmDir',p.direccion);setv('inmCiudad',p.localidad);setv('inmProvincia',p.provincia);setv('inmDesc',p.descripcion);}
      function renderPer(p){return '<b>'+p.nombre+'</b>'+(p.dni?' <small>DNI '+p.dni+'</small>':'');}
      function renderInm(p){return '<b>'+(p.codigo?p.codigo+' · ':'')+p.direccion+'</b>'+(p.localidad?' <small>'+p.localidad+'</small>':'');}
      let box=null;
      function cerrar(){if(box){box.remove();box=null;}}
      function pos(inp){const r=inp.getBoundingClientRect();box.style.left=r.left+'px';
        box.style.top=(r.bottom+2)+'px';box.style.width=Math.max(r.width,260)+'px';}
      function attach(id,url,filler,render,rotulo){
        const inp=document.getElementById(id);if(!inp)return;
        inp.setAttribute('autocomplete','off');
        inp.addEventListener('input',deb(function(){
          const q=inp.value.trim();cerrar();
          if(q.length<2)return;
          fetch(url+'?q='+encodeURIComponent(q),{credentials:'same-origin'})
            .then(r=>r.json()).then(list=>{
              cerrar();box=document.createElement('div');box.className='ac-box';
              if(!list.length){
                const d=document.createElement('div');d.className='ac-empty';
                d.textContent='Sin coincidencias — cargá los datos del nuevo '+rotulo;
                box.appendChild(d);
              }else{
                list.forEach(p=>{
                  const d=document.createElement('div');d.className='ac-item';
                  d.innerHTML=render(p);
                  d.addEventListener('mousedown',function(ev){ev.preventDefault();filler(p);cerrar();});
                  box.appendChild(d);
                });
              }
              document.body.appendChild(box);pos(inp);
            }).catch(function(){});
        },250));
        inp.addEventListener('blur',function(){setTimeout(cerrar,150);});
      }
      function hint(id,txt){const fs=document.getElementById(id);
        if(fs){const h=document.createElement('div');h.className='ac-hint';h.textContent=txt;
          fs.parentNode.insertBefore(h,fs.nextSibling);}}
      function init(){
        attach('locNombre',API_PER,fillLoc,renderPer,'locador');
        attach('locDni',API_PER,fillLoc,renderPer,'locador');
        attach('latNombre',API_PER,fillLat,renderPer,'locatario');
        attach('latDni',API_PER,fillLat,renderPer,'locatario');
        attach('inmDir',API_INM,fillInm,renderInm,'inmueble');
        hint('locNombre','Escribí nombre, apellido o DNI: si el locador ya existe, se completa solo.');
        hint('latNombre','Escribí nombre, apellido o DNI: si el locatario ya existe, se completa solo.');
        hint('inmDir','Escribí la dirección o el código: si el inmueble ya existe, trae sus datos y descripción.');
      }
      if(document.readyState!=='loading')init();else document.addEventListener('DOMContentLoaded',init);
    })();
    </script>
    """ % (api_url, api_inm)

    html = html.replace("<body>", "<body>\n" + barra, 1)
    html = html.replace("</body>", script + autocomplete + "\n</body>", 1)
    return html


@contratos_bp.route("/generador")
@login_required
def generador():
    return Response(_generador_html(), mimetype="text/html")


@contratos_bp.route("/api/personas")
@login_required
def api_personas():
    """Busca personas por nombre/apellido o DNI para autocompletar el generador."""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    like = f"%{q}%"
    res = (Persona.query
           .filter(db.or_(Persona.nombre.ilike(like), Persona.dni.ilike(like)))
           .order_by(Persona.nombre).limit(8).all())
    return jsonify([{"nombre": p.nombre, "dni": p.dni or "", "cuit": p.cuit or "",
                     "domicilio": p.domicilio or "", "email": p.email or "",
                     "localidad": p.localidad or "", "telefono": p.telefono or ""}
                    for p in res])


@contratos_bp.route("/api/inmuebles")
@login_required
def api_inmuebles():
    """Busca inmuebles por código o dirección para autocompletar el generador."""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    like = f"%{q}%"
    res = (Inmueble.query
           .filter(db.or_(Inmueble.codigo.ilike(like), Inmueble.direccion.ilike(like)))
           .order_by(Inmueble.codigo).limit(8).all())
    return jsonify([{"codigo": i.codigo or "", "direccion": i.direccion or "",
                     "localidad": i.localidad or "", "provincia": i.provincia or "",
                     "descripcion": i.descripcion or ""}
                    for i in res])


def _upsert_persona(datos, *, propietario=False, inquilino=False):
    """Busca por DNI (o nombre) y actualiza; si no existe, crea."""
    nombre = (datos.get("nombre") or "").strip()
    if not nombre:
        return None
    dni = (datos.get("dni") or "").strip()
    persona = None
    if dni:
        persona = Persona.query.filter_by(dni=dni).first()
    if not persona:
        persona = Persona.query.filter(db.func.lower(Persona.nombre) == nombre.lower()).first()
    if not persona:
        persona = Persona(nombre=nombre)
        db.session.add(persona)
    persona.nombre = nombre
    if dni:
        persona.dni = dni
    if datos.get("cuil"):
        persona.cuit = datos["cuil"].strip()
    if datos.get("dom"):
        persona.domicilio = datos["dom"].strip()
    if datos.get("email"):
        persona.email = datos["email"].strip()
    if propietario:
        persona.es_propietario = True
    if inquilino:
        persona.es_inquilino = True
    return persona


@contratos_bp.route("/desde-generador", methods=["POST"])
@login_required
def desde_generador():
    d = request.get_json(silent=True) or {}
    loc, lat, inm, econ = d.get("loc", {}), d.get("lat", {}), d.get("inm", {}), d.get("econ", {})

    if not (lat.get("nombre") and inm.get("dir") and econ.get("canon")):
        return jsonify(ok=False, mensaje="Faltan datos: inquilino, inmueble o canon.")

    propietario = _upsert_persona(loc, propietario=True)
    inquilino = _upsert_persona(lat, inquilino=True)
    db.session.flush()

    # Inmueble: buscar por dirección; si no existe, crear.
    direccion = inm["dir"].strip()
    inmueble = Inmueble.query.filter(db.func.lower(Inmueble.direccion) == direccion.lower()).first()
    if not inmueble:
        inmueble = Inmueble(direccion=direccion, tipo="Departamento")
        db.session.add(inmueble)
    inmueble.localidad = inm.get("ciudad") or inmueble.localidad
    inmueble.provincia = inm.get("provincia") or inmueble.provincia
    inmueble.descripcion = inm.get("desc") or inmueble.descripcion
    if propietario:
        inmueble.propietario_id = propietario.id
    inmueble.estado = "Alquilado"
    db.session.flush()

    canon = parse_num(econ.get("canon"))
    plazo = parse_num(econ.get("plazo"), entero=True) or 0
    fecha_inicio = parse_fecha(econ.get("fechaFirma")) or date.today()
    idx = INDICE_MAP.get(econ.get("ajusteIdx"), None)
    metodo = "sin_ajuste" if econ.get("ajusteIdx") == "Sin ajuste" else "indice"

    contrato = Contrato(
        inmueble_id=inmueble.id,
        inquilino_id=inquilino.id if inquilino else None,
        propietario_id=propietario.id if propietario else None,
        fecha_inicio=fecha_inicio,
        duracion_meses=plazo,
        fecha_fin=add_months(fecha_inicio, plazo) if plazo else None,
        precio_inicial=canon,
        precio_actual=canon,
        moneda="Pesos",
        dia_vencimiento=parse_num(econ.get("pagoHasta"), entero=True) or 10,
        mora_diaria_pct=parse_num(econ.get("punitorio")) or 0,
        metodo_ajuste=metodo,
        indice_tipo=idx,
        ajuste_cada_meses=parse_num(econ.get("ajusteMeses"), entero=True) or 6,
        estado="Vigente",
        origen="generador",
    )
    # Guardar el documento generado (contrato + pagarés) para reimprimirlo luego.
    doc = (d.get("documento") or "").strip()
    pag = (d.get("pagares") or "").strip()
    if doc:
        contrato.documento_html = doc + (
            '<div style="page-break-before:always"></div>' + pag if pag else "")
    db.session.add(contrato)
    db.session.flush()

    for f in d.get("fiadores", []):
        if f.get("nombre"):
            contrato.fiadores.append(Fiador(
                nombre=f["nombre"], dni=f.get("dni", ""), domicilio=f.get("dom", ""),
                telefono=f.get("tel", ""), email=f.get("email", ""),
                solvencia=f.get("solvencia", "")))

    # Co-locadores y co-locatarios (personas adicionales de cada lado).
    prop_id = propietario.id if propietario else None
    inq_id = inquilino.id if inquilino else None
    for cl in (d.get("coLoc") or []):
        per = _upsert_persona(cl, propietario=True)
        if per:
            db.session.flush()
            if per.id != prop_id and per not in contrato.colocadores:
                contrato.colocadores.append(per)
    for cl in (d.get("coLat") or []):
        per = _upsert_persona(cl, inquilino=True)
        if per:
            db.session.flush()
            if per.id != inq_id and per not in contrato.colocatarios:
                contrato.colocatarios.append(per)

    db.session.commit()
    return jsonify(ok=True, contrato_id=contrato.id,
                   ver_url=url_for("contratos.ver", cid=contrato.id),
                   mensaje="Contrato dado de alta desde el generador.")
