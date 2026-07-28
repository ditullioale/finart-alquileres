import React, { useState, useEffect } from 'react'
import { getJSON } from './api'

function Card({ href, num, lbl }) {
  return (
    <a className="card ci" href={href}>
      <div className="num">{num}</div>
      <div className="lbl">{lbl}</div>
    </a>
  )
}

export default function Dashboard() {
  const [d, setD] = useState(null)
  useEffect(() => { getJSON('/api/dashboard').then(setD).catch(() => setD('error')) }, [])

  if (d === null) return <p className="hint">Cargando panel…</p>
  if (d === 'error') return <p className="flash error">No se pudo cargar el panel.</p>

  const { stats, pendientes: pend, por_vencer, links } = d

  return (
    <div>
      <div className="pagehead">
        <h1>Panel principal</h1>
        <a className="btn sec" href="/">Versión clásica</a>
      </div>

      <div className="cards">
        <Card href={links.inmuebles} num={stats.inmuebles} lbl="Inmuebles" />
        <Card href={links.alquilados} num={stats.alquilados} lbl="Alquilados" />
        <Card href={links.contratos} num={stats.contratos_vigentes} lbl="Contratos vigentes" />
        <Card href={links.propietarios} num={stats.propietarios} lbl="Propietarios" />
        <Card href={links.inquilinos} num={stats.inquilinos} lbl="Inquilinos" />
      </div>

      <div className="home-grid">
        <div className="panel">
          <h2>Accesos rápidos</h2>
          <div className="quick">
            <a className="btn" href={links.nuevo_contrato}>+ Nuevo contrato</a>
            <a className="btn" href={links.generar_contrato}>📝 Generar contrato</a>
            <a className="btn sec" href={links.nuevo_inmueble}>+ Nuevo inmueble</a>
          </div>
        </div>

        <div className="panel">
          <h2>Pendientes</h2>
          <div className="pend" style={{ gridTemplateColumns: '1fr 1fr 1fr' }}>
            <a className={'pend-item' + (pend.deuda > 0 ? ' alert' : '')} href={links.deuda}>
              <div className="pv">$ {pend.deuda_txt}</div>
              <div className="pl">Deuda registrada</div>
            </a>
            <a className={'pend-item' + (pend.aumentos > 0 ? ' alert' : '')} href={links.aumentos}>
              <div className="pv">{pend.aumentos}</div>
              <div className="pl">Aumentos por aplicar</div>
            </a>
            <a className={'pend-item' + (pend.vencen > 0 ? ' alert' : '')} href="#vencen">
              <div className="pv">{pend.vencen}</div>
              <div className="pl">Contratos por vencer (60 días)</div>
            </a>
          </div>
        </div>
      </div>

      {por_vencer.length > 0 && (
        <div className="panel" style={{ marginTop: 16 }} id="vencen">
          <h2>🕐 Contratos que vencen pronto</h2>
          <div className="table-wrap">
            <table className="grid">
              <thead><tr><th>Vence</th><th>Inquilino</th><th>Inmueble</th><th className="r">Precio actual</th><th></th></tr></thead>
              <tbody>
                {por_vencer.map((c) => (
                  <tr key={c.id}>
                    <td><b className={c.dias <= 30 ? 'txt-danger' : ''}>{c.fecha_fin}</b>
                      <div className="hint" style={{ margin: 0 }}>en {c.dias} días</div></td>
                    <td>{c.inquilino || '—'}</td>
                    <td>{c.inmueble}</td>
                    <td className="r">{c.precio_txt}</td>
                    <td className="actions"><a href={c.ver_url}>Ver contrato</a></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
