// Helpers de llamadas a la API. El token CSRF lo agrega automáticamente el
// parche global de fetch (en base.html); acá solo aseguramos credenciales y JSON.
export async function getJSON(url) {
  const r = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
  if (!r.ok) throw new Error('HTTP ' + r.status)
  return r.json()
}

export async function postJSON(url, body) {
  const r = await fetch(url, {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  let data = {}
  try { data = await r.json() } catch (e) { /* sin cuerpo */ }
  return { ok: r.ok, status: r.status, data }
}

export const money = (n) =>
  Number(n || 0).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&X').replace('.', ',').replace(/X/g, '.')

export const sym = (m) => (m === 'Dólares' ? 'US$' : '$')

export function toast(msg, type) {
  if (window.showToast) window.showToast(msg, type)
}
