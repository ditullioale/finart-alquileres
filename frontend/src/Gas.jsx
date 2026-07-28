import React, { useState, useEffect } from 'react'
import { getJSON, postJSON, money, toast } from './api'
import { RowMenu } from './Tabla'

function ModalFacturas({ cuenta, onClose }) {
  const [g, setG] = useState(null)
  useEffect(() => {
    getJSON(`/api/gas/estado?cuenta=${encodeURIComponent(cuenta)}`).then(setG).catch(() => setG({ ok: false }))
  }, [cuenta])

  return (
    <div className="modal-ov" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal">
        <div className="modal-head">
          <h3>Facturas de gas · {cuenta}</h3>
          <button type="button" className="modal-x" onClick={onClose}>✕</button>
        </div>
        {g === null ? <p className="hint">Cargando…</p> : !g.ok ? (
          <p className="hint">No hay datos para esta cuenta.</p>
        ) : (
          <>
            <p className="modal-sub">
              {g.titular ? `${g.titular} · ` : ''}
              Deuda total: <b className="txt-danger">$ {g.deuda_total_txt}</b>
              {g.actualizado ? ` · act. ${g.actualizado}` : ''}
            </p>
            {g.facturas && g.facturas.length > 0 ? (
              <div className="table-wrap">
                <table className="grid">
                  <thead><tr><th>Factura</th><th>Vence</th><th className="r">Importe</th><th className="r">Con recargo</th></tr></thead>
                  <tbody>
                    {g.facturas.map((f, k) => (
                      <tr key={k}>
                        <td>{f.numero || f.docnumber || '—'}</td>
                        <td>{f.vencimiento || f.docduedate || '—'}</td>
                        <td className="r">$ {money(f.importe ?? f.docamount)}</td>
                        <td className="r">$ {money(f.saldo ?? f.total ?? f.docdueinterwtax ?? f.importe)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="hint">Sin detalle de facturas.</p>}
          </>
        )}
        <div className="modal-btns">
          <button type="button" className="btn sec" onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  )
}

function FilaSinAsignar({ g, disponibles, onAsignada, onEliminar }) {
  const [sel, setSel] = useState('')
  const [busy, setBusy] = useState(false)
  async function asignar() {
    if (!sel) { toast('Elegí un inmueble primero.', 'error'); return }
    setBusy(true)
    const r = await postJSON('/api/gas/asignar', { cuenta: g.cuenta, inmueble_id: sel })
    setBusy(false)
    if (!r.ok || !r.data.ok) { toast(r.data.error || 'No se pudo asignar.', 'error'); return }
    toast(`Cuenta ${g.cuenta} vinculada a ${r.data.inmueble}.`, 'ok')
    onAsignada(g.gas_id)
  }
  return (
    <tr>
      <td><b>{g.cuenta}</b></td>
      <td>{g.titular || '—'}</td>
      <td>{g.direccion || '—'}</td>
      <td>{g.tiene_deuda ? <span className="badge pendiente">Debe</span> : <span className="badge pagado">Al día</span>}</td>
      <td className="actions" style={{ justifyContent: 'flex-start', gap: 8 }}>
        <select style={{ minWidth: 220 }} value={sel} onChange={(e) => setSel(e.target.value)}>
          <option value="">— Elegí inmueble —</option>
          {disponibles.map((i) => <option key={i.id} value={i.id}>{i.texto}</option>)}
        </select>
        <button type="button" className="btn ok sm" disabled={busy} onClick={asignar}>{busy ? 'Asignando…' : 'Asignar'}</button>
      </td>
      <td className="actions">
        <RowMenu><button className="danger" type="button" onClick={() => onEliminar(g.gas_id, g.cuenta)}>🗑 Eliminar suministro</button></RowMenu>
      </td>
    </tr>
  )
}

export default function Gas() {
  const [d, setD] = useState(null)
  const [ver, setVer] = useState(null)
  const [ayuda, setAyuda] = useState(false)

  function cargar() { getJSON('/api/gas').then(setD).catch(() => setD('error')) }
  useEffect(cargar, [])

  async function eliminar(gid, cuenta) {
    if (!window.confirm(`¿Eliminar el suministro ${cuenta} del panel? Si sigue existiendo en Litoral Gas, volverá a aparecer en la próxima actualización.`)) return
    const r = await postJSON(`/api/gas/${gid}/eliminar`, {})
    if (!r.ok || !r.data.ok) { toast(r.data.error || 'No se pudo eliminar.', 'error'); return }
    toast('Suministro eliminado del panel.', 'ok')
    cargar()
  }

  if (d === null) return <p className="hint">Cargando control de gas…</p>
  if (d === 'error') return <p className="flash error">No se pudo cargar el control de gas.</p>

  return (
    <div>
      <div className="pagehead">
        <div>
          <h1>Control de gas</h1>
          <p className="sub">Estado de deuda de Litoral Gas por propiedad.
            {d.actualizado ? ` Última actualización: ${d.actualizado}.` : ''}</p>
        </div>
        <div className="quick">
          <button type="button" className="btn" onClick={() => setAyuda(true)}>⟳ Actualizar</button>
          <a className="btn sec" href="https://www.litoralgas.com.ar/ov/" target="_blank" rel="noreferrer">Abrir Litoral Gas</a>
          <a className="btn sec" href="/gas/">Versión clásica</a>
        </div>
      </div>

      <div className="cards" style={{ gridTemplateColumns: 'repeat(3,1fr)' }}>
        <div className="card"><div className="num" style={{ fontSize: 22 }}>{d.total}</div><div className="lbl">Propiedades con cuenta</div></div>
        <div className="card"><div className="num" style={{ fontSize: 22, color: 'var(--err)' }}>{d.con_deuda}</div><div className="lbl">Con deuda de gas</div></div>
        <div className="card"><div className="num" style={{ fontSize: 22, color: 'var(--err)' }}>$ {d.deuda_total_txt}</div><div className="lbl">Deuda total de gas</div></div>
      </div>

      {d.filas.length > 0 ? (
        <div className="table-wrap">
          <table className="grid">
            <thead><tr><th>Inmueble</th><th>Inquilino</th><th>Cuenta gas</th><th>Estado gas</th><th className="r">Deuda</th><th>Vencimiento</th><th></th></tr></thead>
            <tbody>
              {d.filas.map((f) => (
                <tr key={f.inmueble_id}>
                  <td><a href={f.editar_url}><b>{f.direccion}</b></a>
                    {f.codigo && <div className="hint" style={{ margin: 0 }}>{f.codigo}</div>}</td>
                  <td>{f.inquilino || '—'}</td>
                  <td>{f.cuenta}</td>
                  <td>
                    {!f.tiene_datos ? <span className="badge">Sin datos</span>
                      : f.tiene_deuda ? <span className="badge pendiente" style={{ cursor: 'pointer' }} title="Ver facturas" onClick={() => setVer(f.cuenta)}>Debe</span>
                        : <span className="badge pagado">Al día</span>}
                  </td>
                  <td className={'r' + (f.tiene_deuda ? ' txt-danger' : '')}>
                    {f.tiene_deuda ? <a style={{ cursor: 'pointer', color: 'var(--err)', fontWeight: 600 }} title="Ver facturas" onClick={() => setVer(f.cuenta)}>$ {f.deuda_txt}</a> : '—'}
                  </td>
                  <td>{f.vencimiento || '—'}</td>
                  <td className="actions">
                    {f.tiene_datos && <RowMenu><button className="danger" type="button" onClick={() => eliminar(f.gas_id, f.cuenta)}>🗑 Eliminar suministro</button></RowMenu>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty-state">
          <div className="em">🔥</div>
          <h3>Todavía no hay propiedades con cuenta de gas</h3>
          <p>Vinculá las cuentas de abajo con tus inmuebles, o cargá el N° de cuenta de Litoral Gas en la ficha de cada inmueble.</p>
        </div>
      )}

      {d.sin_asignar.length > 0 && (
        <div className="panel" style={{ marginTop: 16 }}>
          <h2>Cuentas sin asignar</h2>
          <p className="hint" style={{ margin: '0 0 10px' }}>El robot trajo estas cuentas pero no están vinculadas a ningún inmueble.
            Como el domicilio o el titular pueden no coincidir exactamente, elegí a mano el inmueble de tu base. El vínculo se hace por el N° de cuenta.</p>
          <div className="table-wrap">
            <table className="grid">
              <thead><tr><th>Cuenta</th><th>Titular (Litoral Gas)</th><th>Dirección (Litoral Gas)</th><th>Estado</th><th>Asignar a inmueble</th><th></th></tr></thead>
              <tbody>
                {d.sin_asignar.map((g) => (
                  <FilaSinAsignar key={g.gas_id} g={g} disponibles={d.disponibles}
                    onAsignada={() => cargar()} onEliminar={eliminar} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {ver && <ModalFacturas cuenta={ver} onClose={() => setVer(null)} />}

      {ayuda && (
        <div className="modal-ov" onClick={(e) => { if (e.target === e.currentTarget) setAyuda(false) }}>
          <div className="modal">
            <div className="modal-head">
              <h3>Actualizar el gas</h3>
              <button type="button" className="modal-x" onClick={() => setAyuda(false)}>✕</button>
            </div>
            <p className="modal-sub">Los datos de gas los trae el robot desde Litoral Gas. Se actualizan solos cada 15 días, pero si querés hacerlo ahora:</p>
            <p style={{ fontSize: 14, margin: '0 0 6px' }}><b>La forma fácil:</b> hacé doble clic en el ícono <b>"Actualizar Gas"</b> de tu escritorio. Tarda unos segundos y listo.</p>
            <p style={{ fontSize: 13, color: 'var(--muted)', margin: 0 }}>(El robot corre en tu PC porque necesita entrar a Litoral Gas con tu usuario; por eso se dispara desde ahí y no desde este botón.)</p>
            <div className="modal-btns"><button type="button" className="btn sec" onClick={() => setAyuda(false)}>Entendido</button></div>
          </div>
        </div>
      )}
    </div>
  )
}
