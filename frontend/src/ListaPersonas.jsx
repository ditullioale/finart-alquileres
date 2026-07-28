import React, { useState, useEffect } from 'react'
import { getJSON, postJSON, toast } from './api'
import Tabla from './Tabla'
import WaIcon from './WaIcon'

export default function ListaPersonas() {
  const [filas, setFilas] = useState(null)
  const [q, setQ] = useState('')
  const [rol, setRol] = useState('')

  function cargar() {
    getJSON('/api/personas').then((d) => setFilas(d.filas)).catch(() => setFilas('error'))
  }
  useEffect(cargar, [])

  async function eliminar(p) {
    if (!window.confirm(`¿Eliminar a ${p.nombre}?`)) return
    const r = await postJSON(`/api/personas/${p.id}/eliminar`, {})
    if (!r.ok || !r.data.ok) { toast(r.data.error || 'No se pudo eliminar.', 'error'); return }
    toast('Persona eliminada.', 'ok')
    setFilas((fs) => fs.filter((x) => x.id !== p.id))
  }

  if (filas === null) return <p className="hint">Cargando personas…</p>
  if (filas === 'error') return <p className="flash error">No se pudieron cargar las personas.</p>

  const t = q.trim().toLowerCase()
  const rows = filas.filter((p) => {
    if (rol === 'propietario' && !p.es_propietario) return false
    if (rol === 'inquilino' && !p.es_inquilino) return false
    if (!t) return true
    return `${p.nombre} ${p.dni} ${p.cuit} ${p.email}`.toLowerCase().includes(t)
  })

  const columns = [
    { key: 'nombre', label: 'Nombre', render: (p) => <a href={`/personas/react/${p.id}/editar`}><b>{p.nombre}</b></a> },
    { key: 'dni', label: 'DNI', render: (p) => p.dni || '—' },
    { key: 'cuit', label: 'CUIT', render: (p) => p.cuit || '—' },
    { key: 'roles', label: 'Rol', sortable: false },
    { key: 'telefono', label: 'Teléfono', render: (p) => p.telefono || '—' },
    { key: 'email', label: 'Email', render: (p) => p.email || '—' },
    {
      key: 'acc', label: '', cls: 'actions', sortable: false, render: (p) => (
        <>
          <a href={`/personas/react/${p.id}/editar`}>Editar</a>
          <WaIcon href={p.wa} title={`Hola ${p.nombre}`} />
          <button className="link-danger" type="button" onClick={() => eliminar(p)}>Eliminar</button>
        </>
      ),
    },
  ]

  return (
    <div>
      <div className="pagehead">
        <div><h1>Personas</h1><p className="sub">Versión nueva (React).</p></div>
        <div className="quick">
          <a className="btn sec" href="/personas/telefonos">Revisar teléfonos</a>
          <a className="btn" href="/personas/react/nueva">+ Nueva persona</a>
          <a className="btn sec" href="/personas/">Versión clásica</a>
        </div>
      </div>

      <div className="filters">
        <input placeholder="Buscar por nombre, DNI, CUIT o email" value={q}
          onChange={(e) => setQ(e.target.value)} autoComplete="off" />
        <select value={rol} onChange={(e) => setRol(e.target.value)}>
          <option value="">Todos</option>
          <option value="propietario">Propietarios</option>
          <option value="inquilino">Inquilinos</option>
        </select>
      </div>

      <Tabla columns={columns} rows={rows} initialSort="nombre"
        empty={<div className="empty-state"><div className="em">👤</div><h3>Sin resultados</h3><p>Probá con otra búsqueda.</p></div>} />
    </div>
  )
}
