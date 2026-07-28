import React, { useState, useEffect } from 'react'
import { getJSON, postJSON, toast } from './api'
import Tabla from './Tabla'

export default function ListaInmuebles() {
  const [data, setData] = useState(null)
  const [q, setQ] = useState('')
  const [estado, setEstado] = useState('')

  function cargar() {
    getJSON('/api/inmuebles').then(setData).catch(() => setData('error'))
  }
  useEffect(cargar, [])

  async function eliminar(i) {
    if (!window.confirm('¿Eliminar este inmueble?')) return
    const r = await postJSON(`/api/inmuebles/${i.id}/eliminar`, {})
    if (!r.ok || !r.data.ok) { toast(r.data.error || 'No se pudo eliminar.', 'error'); return }
    toast('Inmueble eliminado.', 'ok')
    setData((d) => ({ ...d, filas: d.filas.filter((x) => x.id !== i.id) }))
  }

  if (data === null) return <p className="hint">Cargando inmuebles…</p>
  if (data === 'error') return <p className="flash error">No se pudieron cargar los inmuebles.</p>

  const t = q.trim().toLowerCase()
  const rows = data.filas.filter((i) => {
    if (estado && i.estado !== estado) return false
    if (!t) return true
    return `${i.codigo} ${i.direccion} ${i.localidad} ${i.propietario}`.toLowerCase().includes(t)
  })

  const columns = [
    { key: 'direccion', label: 'Dirección', render: (i) => <a href={`/inmuebles/react/${i.id}/editar`}><b>{i.direccion}</b></a> },
    { key: 'tipo', label: 'Tipo', render: (i) => i.tipo || '—' },
    { key: 'localidad', label: 'Localidad', render: (i) => i.localidad || '—' },
    { key: 'estado', label: 'Estado', render: (i) => <span className={`badge ${i.estado.toLowerCase()}`}>{i.estado}</span> },
    { key: 'propietario', label: 'Propietario', render: (i) => i.propietario || '—' },
    { key: 'precio', label: 'Precio ref.', cls: 'r', sortValue: (i) => i.precio, render: (i) => i.precio_txt },
    {
      key: 'acc', label: '', cls: 'actions', sortable: false, render: (i) => (
        <>
          <a href={`/inmuebles/react/${i.id}/editar`}>Editar</a>
          <button className="link-danger" type="button" onClick={() => eliminar(i)}>Eliminar</button>
        </>
      ),
    },
  ]

  return (
    <div>
      <div className="pagehead">
        <div><h1>Inmuebles</h1><p className="sub">Versión nueva (React).</p></div>
        <div className="quick">
          <a className="btn" href="/inmuebles/react/nuevo">+ Nuevo inmueble</a>
          <a className="btn sec" href="/inmuebles/">Versión clásica</a>
        </div>
      </div>

      <div className="filters">
        <input placeholder="Buscar por dirección, localidad o propietario" value={q}
          onChange={(e) => setQ(e.target.value)} autoComplete="off" />
        <select value={estado} onChange={(e) => setEstado(e.target.value)}>
          <option value="">Todos los estados</option>
          {data.estados.map((e) => <option key={e} value={e}>{e}</option>)}
        </select>
      </div>

      <Tabla columns={columns} rows={rows} initialSort="direccion"
        empty={<div className="empty-state"><div className="em">🏠</div><h3>Sin resultados</h3><p>Probá con otra búsqueda.</p></div>} />
    </div>
  )
}
