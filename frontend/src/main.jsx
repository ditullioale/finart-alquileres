import React from 'react'
import { createRoot } from 'react-dom/client'
import Cobranzas from './Cobranzas'
import ListaPersonas from './ListaPersonas'
import ListaInmuebles from './ListaInmuebles'
import ListaContratos from './ListaContratos'
import Dashboard from './Dashboard'
import Gas from './Gas'
import FormPersona from './FormPersona'
import FormInmueble from './FormInmueble'

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

// Sprint 2: islas de listados.
mount('react-personas', <ListaPersonas />)
mount('react-inmuebles', <ListaInmuebles />)
mount('react-contratos', <ListaContratos />)

// Sprint 3: inicio y gas.
mount('react-dashboard', <Dashboard />)
mount('react-gas', <Gas />)

// Sprint 4: formularios. Leen el id (para editar) del data-id del contenedor.
const fp = document.getElementById('react-form-persona')
if (fp) createRoot(fp).render(<React.StrictMode><FormPersona pid={fp.dataset.id ? Number(fp.dataset.id) : null} /></React.StrictMode>)
const fi = document.getElementById('react-form-inmueble')
if (fi) createRoot(fi).render(<React.StrictMode><FormInmueble iid={fi.dataset.id ? Number(fi.dataset.id) : null} /></React.StrictMode>)
