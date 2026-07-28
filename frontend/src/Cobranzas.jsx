import React, { useState, useEffect, useCallback } from 'react'
import { getJSON, postJSON, money, sym, toast } from './api'

const WA_PATH = 'M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.372-.025-.521-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51l-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.71.306 1.263.489 1.694.625.712.227 1.36.195 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884'

function WaIcon({ href }) {
  if (!href) return <span style={{ width: 30, display: 'inline-block' }} />
  return (
    <a className="wa-ico" href={href} target="_blank" rel="noreferrer" title="Recordatorio por WhatsApp">
      <svg viewBox="0 0 32 32" width="30" height="30" aria-hidden="true">
        <circle cx="16" cy="16" r="16" fill="#25d366" />
        <path fill="#fff" transform="translate(4.2 4.2) scale(0.983)" d={WA_PATH} />
      </svg>
    </a>
  )
}

function Badge({ estado, saldo }) {
  if (estado === 'Pagado') return <span className="badge pagado">✓ Pagado</span>
  if (estado === 'Parcial') return <span className="badge parcial">◐ Parcial · falta {money(saldo)}</span>
  return <span className="badge pendiente">● Sin cobrar</span>
}

function ModalCobro({ fila, mes, anio, formas, onClose, onListo }) {
  const [precio, setPrecio] = useState(fila.esperado)
  const [mora, setMora] = useState(0)
  const [forma, setForma] = useState(formas[0] || 'Efectivo')
  const [obs, setObs] = useState('')
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10))
  const [pagado, setPagado] = useState(fila.esperado)
  const [pagadoTocado, setPagadoTocado] = useState(false)
  const [guardando, setGuardando] = useState(false)

  const total = Math.round(((+precio || 0) + (+mora || 0)) * 100) / 100
  useEffect(() => { if (!pagadoTocado) setPagado(total) }, [total, pagadoTocado])
  const saldo = Math.round((total - (+pagado || 0)) * 100) / 100
  const cur = sym(fila.moneda)

  async function guardar(e) {
    e.preventDefault()
    setGuardando(true)
    const res = await postJSON('/cobros/rapido', {
      cid: fila.cid, mes, anio, precio: +precio, mora: +mora,
      forma_pago: forma, observaciones: obs, gastos: [], pagado: +pagado, fecha,
    })
    setGuardando(false)
    if (!res.ok || !res.data.ok) { toast(res.data.error || 'No se pudo registrar el pago.', 'error'); return }
    toast('Cobro registrado.', 'ok')
    onListo()
  }

  return (
    <div className="modal-ov" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal modal-pago">
        <div className="modal-head">
          <h3>Registrar pago</h3>
          <button type="button" className="modal-x" onClick={onClose}>✕</button>
        </div>
        <div className="pago-datos">
          <div className="pd-row"><span className="pd-k">Inmueble</span><span className="pd-v">{fila.codigo ? `(${fila.codigo}) ` : ''}{fila.inmueble}</span></div>
          <div className="pd-row"><span className="pd-k">Inquilino</span><span className="pd-v">{fila.inquilino || '—'}</span></div>
          <div className="pd-row"><span className="pd-k">Propietario</span><span className="pd-v">{fila.propietario || '—'}</span></div>
        </div>
        <form onSubmit={guardar} data-no-busy>
          <div className="grid2" style={{ marginTop: 12 }}>
            <div><label>Fecha de pago</label><input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} /></div>
            <div><label>Precio alquiler</label>
              <div className="cm-money"><span>{cur}</span>
                <input type="number" step="0.01" value={precio} onChange={(e) => setPrecio(e.target.value)} required /></div></div>
          </div>
          <div className="pago-mes">
            <div><label>N° de pago</label><input type="text" value={fila.prox_nro} readOnly /></div>
            <div><label>Correspondiente al mes de</label><input type="text" value={`${mes}/${anio}`} readOnly /></div>
          </div>
          <div className="grid2">
            <div><label>Forma de pago</label>
              <select value={forma} onChange={(e) => setForma(e.target.value)}>
                {formas.map((f) => <option key={f} value={f}>{f}</option>)}
              </select></div>
            <div><label>Mora</label>
              <input type="number" step="0.01" value={mora} onChange={(e) => setMora(e.target.value)} /></div>
          </div>
          <label style={{ marginTop: 12 }}>Observaciones</label>
          <input type="text" value={obs} onChange={(e) => setObs(e.target.value)} placeholder="Referencia, nota, etc." />
          <div className="pago-tot">
            <div className="pt-row"><span>Total a pagar</span><b>{cur} {money(total)}</b></div>
            <div className="pt-row"><span>Pagado</span>
              <input type="number" step="0.01" style={{ maxWidth: 150, textAlign: 'right' }}
                value={pagado} onChange={(e) => { setPagadoTocado(true); setPagado(e.target.value) }} /></div>
            {saldo > 0.005 && <div className="pt-hint" style={{ display: 'block' }}>Queda un saldo de {cur} {money(saldo)} (pago parcial).</div>}
          </div>
          <div className="modal-btns">
            <button type="submit" className="btn ok" disabled={guardando}>{guardando ? 'Guardando…' : 'Asentar pago'}</button>
            <button type="button" className="btn sec" onClick={onClose}>Cancelar</button>
            <a className="modal-link" href={`/cobros/contrato/${fila.cid}/nuevo?mes=${mes}&anio=${anio}`}>Cobro detallado</a>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function Cobranzas({ mesIni, anioIni }) {
  const [mes, setMes] = useState(mesIni)
  const [anio, setAnio] = useState(anioIni)
  const [data, setData] = useState(null)
  const [q, setQ] = useState('')
  const [fEstado, setFEstado] = useState('')
  const [cobrando, setCobrando] = useState(null)

  const cargar = useCallback(() => {
    setData(null)
    getJSON(`/api/cobranzas?mes=${mes}&anio=${anio}`).then(setData).catch(() => setData({ error: true }))
  }, [mes, anio])
  useEffect(() => { cargar() }, [cargar])

  if (!data) return <p className="hint">Cargando cobranzas…</p>
  if (data.error) return <p className="flash error">No se pudieron cargar las cobranzas.</p>

  const t = q.trim().toLowerCase()
  const filas = data.filas.filter((f) => {
    if (fEstado === 'pendiente' && f.estado === 'Pagado') return false
    if (fEstado === 'cobrado' && f.estado !== 'Pagado') return false
    if (!t) return true
    return `${f.inquilino} ${f.inmueble} ${f.propietario}`.toLowerCase().includes(t)
  })

  return (
    <div>
      <div className="pagehead">
        <div>
          <h1>Cobranzas del mes</h1>
          <p className="sub">Versión nueva (React). Cobrá cada alquiler sin recargar.</p>
        </div>
        <div className="quick">
          <a className="btn sec" href={`/cobros/exportar?mes=${mes}&anio=${anio}`}>⬇ Exportar a Excel</a>
          <a className="btn sec" href="/cobros/">Versión clásica</a>
        </div>
      </div>

      <div className="filters">
        <input placeholder="Buscar inquilino, propietario o inmueble" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" />
        <select value={mes} onChange={(e) => setMes(+e.target.value)}>
          {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => <option key={m} value={m}>{data.meses[m]}</option>)}
        </select>
        <select value={anio} onChange={(e) => setAnio(+e.target.value)}>
          {data.anios.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <select value={fEstado} onChange={(e) => setFEstado(e.target.value)}>
          <option value="">Todos</option>
          <option value="pendiente">Solo pendientes</option>
          <option value="cobrado">Solo cobrados</option>
        </select>
      </div>

      <div className="cards" style={{ gridTemplateColumns: 'repeat(3,1fr)' }}>
        <div className="card"><div className="num" style={{ fontSize: 22 }}>$ {money(data.totales.esperado)}</div><div className="lbl">Esperado del mes</div></div>
        <div className="card"><div className="num" style={{ fontSize: 22, color: 'var(--ok)' }}>$ {money(data.totales.cobrado)}</div><div className="lbl">Cobrado</div></div>
        <div className="card"><div className="num" style={{ fontSize: 22, color: 'var(--err)' }}>$ {money(data.totales.pendiente)}</div><div className="lbl">Pendiente de cobro</div></div>
      </div>

      {filas.length === 0 ? (
        <div className="empty-state"><div className="em">📅</div><h3>No hay resultados</h3><p>Probá con otro mes o quitá el filtro.</p></div>
      ) : (
        <div className="table-wrap">
          <table className="grid">
            <thead><tr><th>Inquilino</th><th>Inmueble</th><th className="r">A cobrar</th><th className="r">Cobrado</th><th>Estado</th><th></th><th className="wa-col"></th></tr></thead>
            <tbody>
              {filas.map((f) => (
                <tr key={f.cid}>
                  <td><b>{f.inquilino || '—'}</b></td>
                  <td>{f.inmueble}{f.localidad && <div className="hint" style={{ margin: 0 }}>{f.localidad}</div>}</td>
                  <td className="r">{sym(f.moneda)} {money(f.esperado)}</td>
                  <td className="r">{f.pago_id ? money(f.cobrado) : '—'}</td>
                  <td><Badge estado={f.estado} saldo={f.saldo} /></td>
                  <td className="actions cob-actions">
                    {f.estado === 'Pagado' ? (
                      <>
                        <a className="btn sec sm" href={`/cobros/contrato/${f.cid}`}>Ver</a>
                        <a className="btn sec sm" href={f.recibo_url} target="_blank" rel="noreferrer">Recibo</a>
                      </>
                    ) : f.estado === 'Parcial' ? (
                      <>
                        <a className="btn ok sm" href={`/cobros/pago/${f.pago_id}/abonar`}>Completar</a>
                        <a className="btn sec sm" href={f.recibo_url} target="_blank" rel="noreferrer">Recibo</a>
                      </>
                    ) : (
                      <button type="button" className="btn ok sm" onClick={() => setCobrando(f)}>Cobrar</button>
                    )}
                  </td>
                  <td className="wa-col">{f.estado !== 'Pagado' && <WaIcon href={f.wa} />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {cobrando && (
        <ModalCobro fila={cobrando} mes={mes} anio={anio} formas={data.formas}
          onClose={() => setCobrando(null)}
          onListo={() => { setCobrando(null); cargar() }} />
      )}
    </div>
  )
}
