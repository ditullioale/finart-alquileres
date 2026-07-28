import React from 'react'
import { createRoot } from 'react-dom/client'
import Cobranzas from './Cobranzas'

function mount(id, element) {
  const el = document.getElementById(id)
  if (el) createRoot(el).render(<React.StrictMode>{element}</React.StrictMode>)
}

function HolaSprint0() {
  return (
    <div style={{
      padding: '12px 16px', background: '#eaf0fb', border: '1px solid #b9cdf0',
      borderRadius: 10, color: '#274b8f', fontFamily: 'Inter, sans-serif',
    }}>
      ✅ React está funcionando (Sprint 0). Esta caja la renderizó React sobre la app Flask.
    </div>
  )
}

mount('react-root', <HolaSprint0 />)

// Sprint 1: isla de Cobranzas. Lee el mes/año inicial del div contenedor.
const cob = document.getElementById('react-cobranzas')
if (cob) {
  const hoy = new Date()
  const mesIni = Number(cob.dataset.mes) || hoy.getMonth() + 1
  const anioIni = Number(cob.dataset.anio) || hoy.getFullYear()
  createRoot(cob).render(
    <React.StrictMode><Cobranzas mesIni={mesIni} anioIni={anioIni} /></React.StrictMode>
  )
}
