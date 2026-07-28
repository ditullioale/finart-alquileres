import React, { useState, useEffect } from 'react'
import { getJSON, postJSON, toast } from './api'

export default function FormInmueble({ iid }) {
  const [d, setD] = useState(null)
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    const url = iid ? `/api/inmuebles/${iid}` : '/api/inmuebles/nuevo'
    getJSON(url).then(setD).catch(() => setD('error'))
  }, [iid])

  if (d === null) return <p className="hint">Cargando…</p>
  if (d === 'error') return <p className="flash error">No se pudo cargar el inmueble.</p>

  const i = d.inmueble
  const set = (k) => (e) => setD({ ...d, inmueble: { ...i, [k]: e.target.value } })

  async function guardar(e) {
    e.preventDefault()
    if (!i.direccion.trim()) { toast('La dirección es obligatoria.', 'error'); return }
    setGuardando(true)
    const url = iid ? `/api/inmuebles/${iid}/guardar` : '/api/inmuebles/guardar'
    const r = await postJSON(url, i)
    setGuardando(false)
    if (!r.ok || !r.data.ok) { toast(r.data.error || 'No se pudo guardar.', 'error'); return }
    toast('Inmueble guardado.', 'ok')
    window.location.href = r.data.redirect
  }

  return (
    <div>
      <div className="pagehead"><h1>{iid ? 'Editar' : 'Nuevo'} inmueble</h1></div>
      <form className="cardform" onSubmit={guardar} data-no-busy>
        <div className="grid2">
          <div><label>Código</label><input value={i.codigo} onChange={set('codigo')} placeholder="DE17" /></div>
          <div><label>Tipo</label>
            <select value={i.tipo} onChange={set('tipo')}>
              <option value="">—</option>
              {d.tipos.map((t) => <option key={t} value={t}>{t}</option>)}
            </select></div>
          <div className="full"><label>Dirección *</label><input value={i.direccion} onChange={set('direccion')} required /></div>
          <div><label>Localidad</label><input value={i.localidad} onChange={set('localidad')} /></div>
          <div><label>Provincia</label><input value={i.provincia} onChange={set('provincia')} /></div>
          <div><label>Barrio</label><input value={i.barrio} onChange={set('barrio')} /></div>
          <div><label>Estado</label>
            <select value={i.estado} onChange={set('estado')}>
              {d.estados.map((e) => <option key={e} value={e}>{e}</option>)}
            </select></div>
          <div><label>Dormitorios</label><input value={i.dormitorios} onChange={set('dormitorios')} /></div>
          <div><label>Baños</label><input value={i.banos} onChange={set('banos')} /></div>
          <div><label>Propietario</label>
            <select value={i.propietario_id} onChange={set('propietario_id')}>
              <option value="">—</option>
              {d.propietarios.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
            </select>
            <span className="hint">¿No aparece? Marcalo como propietario en Personas.</span></div>
          <div><label>Moneda</label>
            <select value={i.moneda} onChange={set('moneda')}>
              <option>Pesos</option><option>Dólares</option>
            </select></div>
          <div><label>Precio de referencia</label><input value={i.precio_referencia} onChange={set('precio_referencia')} /></div>
          <div><label>% Comisión al propietario</label><input value={i.comision_pct} onChange={set('comision_pct')} /></div>
          <div><label>N° de cuenta Litoral Gas</label>
            <input value={i.cuenta_gas} onChange={set('cuenta_gas')} placeholder="Ej: 962500/01" />
            <span className="hint">El N° de cliente que figura en Litoral Gas. Sirve para el control de gas.</span></div>
        </div>

        <label>Descripción</label>
        <textarea rows="3" value={i.descripcion} onChange={set('descripcion')} />
        <label>Observaciones</label>
        <textarea rows="2" value={i.observaciones} onChange={set('observaciones')} />

        <div className="formbtns">
          <button className="btn" type="submit" disabled={guardando}>{guardando ? 'Guardando…' : 'Guardar'}</button>
          <a className="btn sec" href="/inmuebles/">Cancelar</a>
        </div>
      </form>
    </div>
  )
}
