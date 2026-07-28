import React, { useState } from 'react'

/**
 * Tabla reutilizable con orden por columnas.
 *
 * columns: [{ key, label, cls, sortable=true, sortValue(row), render(row) }]
 * rows:    array de objetos ya filtrados por el componente padre.
 * initialSort: key de la columna por la que ordenar al inicio (opcional).
 * empty:   nodo a mostrar cuando no hay filas.
 */
export default function Tabla({ columns, rows, initialSort = null, empty }) {
  const [sort, setSort] = useState(initialSort)
  const [dir, setDir] = useState('asc')

  function clickHeader(col) {
    if (col.sortable === false) return
    if (sort === col.key) setDir(dir === 'asc' ? 'desc' : 'asc')
    else { setSort(col.key); setDir('asc') }
  }

  let data = rows
  if (sort) {
    const col = columns.find((c) => c.key === sort)
    if (col) {
      const val = col.sortValue || ((r) => {
        const v = r[col.key]
        return typeof v === 'string' ? v.toLowerCase() : v
      })
      data = [...rows].sort((a, b) => {
        const va = val(a), vb = val(b)
        if (va < vb) return dir === 'asc' ? -1 : 1
        if (va > vb) return dir === 'asc' ? 1 : -1
        return 0
      })
    }
  }

  if (rows.length === 0 && empty) return empty

  return (
    <div className="table-wrap">
      <table className="grid">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={c.cls || ''}>
                {c.sortable === false ? (c.label || '') : (
                  <a className="sorth" href="#" onClick={(e) => { e.preventDefault(); clickHeader(c) }}>
                    {c.label}
                    <span className="arr">{sort === c.key ? (dir === 'asc' ? ' ▲' : ' ▼') : ''}</span>
                  </a>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={row.id}>
              {columns.map((c) => (
                <td key={c.key} className={c.cls || ''}>
                  {c.render ? c.render(row) : (row[c.key] || '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Menú "⋯ Más" por fila (para acciones secundarias). */
export function RowMenu({ children }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rowmenu"
      onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
      style={{ position: 'relative', display: 'inline-block' }}>
      <button className="menu-trigger" type="button" onClick={() => setOpen(!open)}>⋯ Más</button>
      {open && (
        <div className="menu-pop" style={{ display: 'block', position: 'absolute', right: 0, top: '100%', marginTop: 4 }}
          onClick={() => setOpen(false)}>
          {children}
        </div>
      )}
    </div>
  )
}
