import React, { useState, useEffect } from 'react'
import { getJSON, postJSON, toast } from './api'

// Réplica en JS de normalizar_whatsapp() (app/utils.py) para feedback inmediato.
function normalizarWhatsapp(tel) {
  let d = (tel || '').trim().replace(/\.0+$/, '').replace(/\D/g, '')
  if (!d) return null
  if (d.startsWith('549')) d = d.slice(3)
  else if (d.startsWith('54')) d = d.slice(2)
  if (d.startsWith('0')) d = d.slice(1)
  if (d.length === 12) {
    for (const i of [2, 3, 4]) {
      if (d.slice(i, i + 2) === '15') { d = d.slice(0, i) + d.slice(i + 2); break }
    }
  }
  if (d.length === 11 && d.startsWith('9')) d = d.slice(1)
  if (d.length !== 10) return null
  return '549' + d
}

export default function FormPersona({ pid }) {
  const [p, setP] = useState(null)
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    const url = pid ? `/api/personas/${pid}` : '/api/personas/nueva'
    getJSON(url).then((d) => setP(d.persona)).catch(() => setP('error'))
  }, [pid])

  if (p === null) return <p className="hint">Cargando…</p>
  if (p === 'error') return <p className="flash error">No se pudo cargar la persona.</p>

  const set = (k) => (e) => setP({ ...p, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const tel = p.telefono.trim()
  const wa = tel ? normalizarWhatsapp(tel) : null

  async function guardar(e) {
    e.preventDefault()
    if (!p.nombre.trim()) { toast('El nombre es obligatorio.', 'error'); return }
    setGuardando(true)
    const url = pid ? `/api/personas/${pid}/guardar` : '/api/personas/guardar'
    const r = await postJSON(url, p)
    setGuardando(false)
    if (!r.ok || !r.data.ok) { toast(r.data.error || 'No se pudo guardar.', 'error'); return }
    toast('Persona guardada.', 'ok')
    window.location.href = r.data.redirect
  }

  return (
    <div>
      <div className="pagehead"><h1>{pid ? 'Editar' : 'Nueva'} persona</h1></div>
      <form className="cardform" onSubmit={guardar} data-no-busy>
        <div className="grid2">
          <div className="full"><label>Nombre y apellido *</label>
            <input value={p.nombre} onChange={set('nombre')} required autoFocus /></div>
          <div><label>DNI</label><input value={p.dni} onChange={set('dni')} /></div>
          <div><label>CUIT / CUIL</label><input value={p.cuit} onChange={set('cuit')} /></div>
          <div className="full"><label>Domicilio</label><input value={p.domicilio} onChange={set('domicilio')} /></div>
          <div><label>Localidad</label><input value={p.localidad} onChange={set('localidad')} /></div>
          <div><label>Condición IVA</label><input value={p.cond_iva} onChange={set('cond_iva')} /></div>
          <div><label>Teléfono</label>
            <input value={p.telefono} onChange={set('telefono')} placeholder="Ej: 11 2345-6789" />
            {tel && (wa
              ? <span className="hint" style={{ color: 'var(--ok)' }}>✅ Válido para WhatsApp (+{wa})</span>
              : <span className="hint" style={{ color: 'var(--err)' }}>⚠️ Falta el código de área o el número está incompleto</span>)}
          </div>
          <div><label>Email</label><input value={p.email} onChange={set('email')} /></div>
        </div>

        <div className="checks">
          <label className="chk"><input type="checkbox" checked={p.es_propietario} onChange={set('es_propietario')} /> Es propietario</label>
          <label className="chk"><input type="checkbox" checked={p.es_inquilino} onChange={set('es_inquilino')} /> Es inquilino</label>
        </div>

        <label>Observaciones</label>
        <textarea rows="3" value={p.observaciones} onChange={set('observaciones')} />

        <div className="formbtns">
          <button className="btn" type="submit" disabled={guardando}>{guardando ? 'Guardando…' : 'Guardar'}</button>
          <a className="btn sec" href="/personas/">Cancelar</a>
        </div>
      </form>
    </div>
  )
}
