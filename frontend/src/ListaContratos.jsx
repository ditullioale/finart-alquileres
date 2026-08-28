import React, { useState, useEffect } from 'react'
import { getJSON, postJSON, toast } from './api'
import Tabla, { RowMenu } from './Tabla'

export default function ListaContratos() {
  const [data, setData] = useState(null)
  const [q, setQ] = useState('')
  const [estado, setEstado] = useState('')

  function cargar() {
    getJSON('/api/contratos').then(setData).catch(() => setData('error'))
  }
  useEffect(cargar, [])

  async function eliminar(c) {
    if (!window.confirm('¿Eliminar definitivamente este contrato? Solo se permite si no tiene pagos.')) return
    const r = await postJSON(`/api/contratos/${c.id}/eliminar`, {})
    if (!r.ok || !r.data.ok) { toast(r.data.error || 'No se pudo eliminar.', 'error'); return }
    toast('Contrato eliminado.', 'ok')
    setData((d) => ({ ...d, filas: d.filas.filter((x) => x.id !== c.id) }))
  }

  async function rescindir(c) {
    if (!window.confirm(`¿Rescindir el contrato de ${c.inquilino || ''}? El inmueble queda disponible y se conserva el historial.`)) return
    const r = await postJSON(`/api/contratos/${c.id}/rescindir`, {})
    if (!r.ok || !r.data.ok) { toast(r.data.error || 'No se pudo rescindir.', 'error'); return }
    toast('Contrato rescindido.', 'ok')
    setData((d) => ({ ...d, filas: d.filas.map((x) => x.id === c.id ? { ...x, estado: 'Rescindido', vigente: false } : x) }))
  }

  if (data === null) return <p className="hint">Cargando contratos…</p>
  if (data === 'error') return <p className="flash error">No se pudieron cargar los contratos.</p>

  const t = q.trim().toLowerCase()
  const rows = data.filas.filter((c) => {
    if (estado && c.estado !== estado) return false
    if (!t) return true
    return `${c.inquilino} ${c.propietario} ${c.inmueble} ${c.codigo} ${c.numero}`.toLowerCase().includes(t)
  })

  const columns = [
    { key: 'inquilino', label: 'Inquilino', render: (c) => <a href={c.ver_url}><b>{c.inquilino || '—'}</b></a> },
    { key: 'propietario', label: 'Propietario', render: (c) => c.propietario || '—' },
    {
      key: 'inmueble', label: 'Inmueble', render: (c) => (
        <>{c.inmueble}{c.localidad && <div className="hint" style={{ margin: 0 }}>{c.localidad}</div>}</>
      ),
    },
    { key: 'precio', label: 'Precio actual', cls: 'r', sortValue: (c) => c.precio, render: (c) => c.precio_txt },
    { key: 'ajuste', label: 'Ajuste', sortable: false },
    { key: 'estado', label: 'Estado', render: (c) => <span className={`badge ${c.estado.toLowerCase()}`}>{c.estado}</span> },
    {
      key: 'acc', label: '', cls: 'actions', sortable: false, render: (c) => (
        <>
          <a className="btn ok sm" href={c.cobrar_url}>💵 Cobrar</a>
          <RowMenu>
            <a href={c.ver_url}>👁 Ver</a>
            {c.tiene_documento && <a href={c.documento_url} target="_blank" rel="noreferrer">📄 Ver contrato</a>}
            {c.wa && <a href={c.wa} target="_blank" rel="noreferrer">🟢 Contactar por WhatsApp</a>}
            {c.notificar_url && <a href={c.notificar_url}>✉️ Enviar comunicación</a>}
            {c.vigente && <button className="warn" type="button" onClick={() => rescindir(c)}>⛔ Rescindir</button>}
            <button className="danger" type="button" onClick={() => eliminar(c)}>🗑 Eliminar</button>
          </RowMenu>
        </>
      ),
    },
  ]

  return (
    <div>
      <div className="pagehead">
        <div><h1>Contratos</h1><p className="sub">Versión nueva (React). Desde acá registrás cobros y aumentos.</p></div>
        <div className="quick">
          <a className="btn" href="/contratos/nuevo">+ Alta directa</a>
          <a className="btn sec" href="/contratos/generador">📝 Generar contrato</a>
          <a className="btn sec" href="/contratos/">Versión clásica</a>
        </div>
      </div>

      <div className="filters">
        <input placeholder="Buscar por inquilino, propietario, inmueble o código" value={q}
          onChange={(e) => setQ(e.target.value)} autoComplete="off" />
        <select value={estado} onChange={(e) => setEstado(e.target.value)}>
          <option value="">Todos los estados</option>
          {data.estados.map((e) => <option key={e} value={e}>{e}</option>)}
        </select>
      </div>

      <Tabla columns={columns} rows={rows}
        empty={<div className="empty-state"><div className="em">📄</div><h3>No hay contratos con ese filtro</h3><p>Cargá un alquiler con “Alta directa” o generá uno nuevo.</p></div>} />
    </div>
  )
}
