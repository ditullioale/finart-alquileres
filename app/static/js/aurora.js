/* Aurora — comportamiento común del diseño nuevo: panel lateral, paleta de
   comandos, atajos de teclado, tema y avisos. Sólo se carga con UI=nueva. */
(function () {
  'use strict';

  var $ = function (s, r) { return (r || document).querySelector(s); };

  function money(n) {
    return '$ ' + Math.round(Number(n) || 0).toLocaleString('es-AR');
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function ini(s) {
    return String(s || '?').split(' ').filter(Boolean).slice(0, 2)
      .map(function (w) { return w[0]; }).join('').toUpperCase();
  }
  // Lee un importe escrito como en Argentina ("1.234,56", "$ 1.234", "1234.56").
  function leerMonto(txt) {
    var s = String(txt || '').replace(/[^\d,.-]/g, '');
    if (s.indexOf(',') !== -1) s = s.replace(/\./g, '').replace(',', '.');
    else if ((s.match(/\./g) || []).length > 1) s = s.replace(/\./g, '');
    else if (/\.\d{3}$/.test(s)) s = s.replace(/\./g, '');
    return Number(s) || 0;
  }

  /* ---- avisos ---------------------------------------------------------- */
  function toast(titulo, detalle, tipo) {
    var cont = $('#toasts');
    if (!cont) return;
    var d = document.createElement('div');
    d.className = 'toast ' + (tipo || 'ok');
    d.innerHTML = '<div class="ic"></div><div><b>' + esc(titulo) + '</b>' +
      (detalle ? '<span>' + esc(detalle) + '</span>' : '') + '</div>';
    cont.appendChild(d);
    setTimeout(function () { d.classList.add('out'); setTimeout(function () { d.remove(); }, 300); }, 4200);
  }
  window.toast = toast;
  // La UI clásica usa showToast(msg, tipo): se respeta la firma.
  window.showToast = function (msg, tipo) { toast(msg, '', tipo === 'error' ? 'err' : 'ok'); };

  /* ---- tema ------------------------------------------------------------ */
  window.toggleTema = function () {
    var claro = document.documentElement.classList.toggle('light');
    document.body.classList.toggle('light', claro);
    try { localStorage.setItem('tema', claro ? 'claro' : 'oscuro'); } catch (e) {}
  };

  /* ---- panel lateral --------------------------------------------------- */
  var Peek = {
    open: function (titulo, cuerpo, pie) {
      $('#peek-t').innerHTML = titulo;
      $('#peek-b').innerHTML = cuerpo;
      $('#peek-f').innerHTML = pie || '';
      $('#peek').classList.add('on');
      $('#ov').classList.add('on');
      setTimeout(function () { var i = $('#peek-b input'); if (i) { i.focus(); i.select(); } }, 160);
    },
    close: function () {
      $('#peek').classList.remove('on');
      $('#ov').classList.remove('on');
    },
    // Cobro real contra /cobros/rapido. Si no se toca el campo Mora, el
    // servidor la recalcula solo; si se toca (por ej. para sacarla), se manda
    // el valor explícito y el servidor respeta ese override.
    cobro: function (r) {
      Peek._r = r;
      Peek.moraTocada = false;
      Peek.montoTocado = false;
      var mora = Number(r.mora) || 0;
      var total = (Number(r.monto) || 0) + mora;
      Peek.open('Registrar cobro',
        '<div class="split" style="margin-bottom:16px">' +
          '<div class="avatar" style="width:34px;height:34px">' + ini(r.quien) + '</div>' +
          '<div><div style="font-weight:550">' + esc(r.quien) + '</div>' +
          '<div class="mut" style="font-size:12px">' + esc(r.det || '') + '</div></div></div>' +
        '<div class="field"><label>Mora' +
          '<span style="float:right;display:flex;gap:6px">' +
          '<button type="button" class="btn ghost sm" style="padding:1px 9px" onclick="Peek.calcularMora()">↻ Calcular</button>' +
          '<button type="button" class="btn ghost sm" style="padding:1px 9px" onclick="Peek.sacarMora()">Sacar mora</button>' +
          '</span></label>' +
          '<div class="inp-money"><span class="cur">$</span>' +
          '<input class="inp num" id="cobro-mora" value="' + mora.toLocaleString('es-AR') + '" oninput="Peek.moraTocada=true;Peek.syncMonto();Peek.recalc()"></div>' +
          '<p class="hint" id="cobro-mora-hint">Se suma al importe recibido. Poné 0 (o tocá "Sacar mora" / "Calcular") si esta vez no la cobrás.</p></div>' +
        '<div class="field"><label>Importe recibido</label>' +
          '<div class="inp-money"><span class="cur">$</span>' +
          '<input class="inp num" id="cobro-monto" value="' + total.toLocaleString('es-AR') + '"></div>' +
          '<p class="hint">Podés escribirlo con puntos o sin ellos.</p></div>' +
        '<div class="field"><label>Medio de pago</label>' +
          '<div class="seg" id="cobro-forma">' +
          '<button type="button" class="on">Transferencia</button>' +
          '<button type="button">Efectivo</button>' +
          '<button type="button">Cheque</button></div></div>' +
        '<div class="field"><label>Fecha</label><input class="inp" type="date" id="cobro-fecha" value="' +
          (r.hoy || new Date().toISOString().slice(0, 10)) + '"></div>' +
        '<div class="field"><label>Gastos extra (opcional)</label>' +
          '<div id="cobro-gastos"></div>' +
          '<button type="button" class="btn ghost sm" onclick="Peek.agregarGasto()">+ Agregar gasto</button>' +
          '<p class="hint">Agua, expensas, seguro... "Trasladar" tildado = se suma a la liquidación del ' +
          'propietario (sin comisión); destildado = lo cobramos junto con el alquiler pero queda para la ' +
          'inmobiliaria (ej.: un seguro que pagamos nosotros).</p></div>' +
        '<div class="calc" id="cobro-calc"></div>' +
        '<div class="field" style="margin-top:14px"><label>Nota (opcional)</label>' +
          '<textarea class="inp" id="cobro-obs" placeholder="Ej.: paga con dos transferencias"></textarea></div>' +
        '<p class="hint">Este cobro lleva una clave única: si se reenvía, se registra una sola vez.</p>',
        '<button class="btn ghost" onclick="Peek.close()">Cancelar <kbd>Esc</kbd></button>' +
        '<div style="flex:1"></div>' +
        '<button class="btn pri" id="cobro-ok" onclick="Peek.guardarCobro()">Guardar cobro <kbd>↵</kbd></button>');
      var inp = $('#cobro-monto');
      inp.addEventListener('input', function () { Peek.montoTocado = true; Peek.recalc(); });
      inp.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); Peek.guardarCobro(); }
      });
      $('#cobro-forma').addEventListener('click', function (e) {
        var b = e.target.closest('button'); if (!b) return;
        Array.prototype.forEach.call(b.parentElement.children, function (x) { x.classList.remove('on'); });
        b.classList.add('on');
      });
      // Si cambian la fecha de pago y todavía no tocaron la mora a mano, la
      // recalculamos para esa fecha (igual que al abrir el modal).
      $('#cobro-fecha').addEventListener('change', function () {
        if (!Peek.moraTocada) Peek.calcularMora();
      });
      Peek.idem = 'cobro-' + (r.cid || '') + '-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
      Peek.recalc();
    },
    // Recalcula la mora para la fecha de pago elegida: gracia hasta el
    // vencimiento, y si se paga tarde los días cuentan desde el día 1 del mes
    // del vencimiento (misma regla que utils.calcular_mora en el servidor).
    calcularMora: function () {
      var r = Peek._r || {};
      var el = $('#cobro-mora'), hint = $('#cobro-mora-hint');
      if (!el) return;
      var pct = Number(r.morapct) || 0, precio = Number(r.monto) || 0;
      var fp = ($('#cobro-fecha') || {}).value;
      if (!r.venc || !fp || !precio || !pct) {
        if (hint) hint.textContent = '';
        return;
      }
      var dv = new Date(r.venc + 'T00:00:00'), dp = new Date(fp + 'T00:00:00');
      var dia1 = new Date(dv.getFullYear(), dv.getMonth(), 1);
      var dias = Math.floor((dp - dia1) / 86400000);
      var mora = (dp > dv && dias > 0) ? Math.round(precio * (pct / 100) * dias * 100) / 100 : 0;
      el.value = mora.toLocaleString('es-AR');
      Peek.moraTocada = false;
      if (hint) {
        hint.textContent = mora > 0
          ? (dias + ' día(s) desde el 1° del mes × ' + pct + '%/día sobre el alquiler')
          : 'Pagó dentro del vencimiento: mora 0';
        hint.style.color = mora > 0 ? 'var(--err)' : 'var(--muted)';
      }
      Peek.syncMonto();
      Peek.recalc();
    },
    // Pone la mora en 0 y refleja el cambio en "Importe recibido" (si el
    // usuario no lo tocó a mano todavía).
    sacarMora: function () {
      var el = $('#cobro-mora'); if (!el) return;
      el.value = 0;
      Peek.moraTocada = true;
      Peek.syncMonto();
      Peek.recalc();
    },
    // Mientras el usuario no haya editado "Importe recibido" a mano, lo
    // mantiene sincronizado con base + mora + gastos extra (para que al sacar
    // la mora, o al agregar un gasto, el importe sugerido se ajuste solo).
    syncMonto: function () {
      if (Peek.montoTocado) return;
      var r = Peek._r || {}, base = Number(r.monto) || 0;
      var mora = leerMonto(($('#cobro-mora') || {}).value);
      var gastos = Peek.gastosTotal();
      var el = $('#cobro-monto'); if (!el) return;
      el.value = (base + mora + gastos).toLocaleString('es-AR');
    },
    // Agrega una fila de "gasto extra" (desc + monto + trasladar al propietario).
    agregarGasto: function (desc, monto, trasladar) {
      trasladar = trasladar === undefined ? true : !!trasladar;
      var wrap = $('#cobro-gastos'); if (!wrap) return;
      var row = document.createElement('div');
      row.className = 'gasto-row';
      row.style.cssText = 'display:flex;gap:6px;align-items:center;margin-bottom:6px;flex-wrap:wrap';
      row.innerHTML =
        '<input class="inp g-desc" placeholder="Descripción" style="flex:2;min-width:110px" value="' + esc(desc || '') + '">' +
        '<input class="inp num g-monto" placeholder="Monto" style="flex:1;min-width:90px" value="' +
          (monto !== undefined && monto !== null ? monto : '') + '">' +
        '<label class="chk" style="font-size:12px;white-space:nowrap"><input type="checkbox" class="g-trasladar"' +
          (trasladar ? ' checked' : '') + '>Trasladar</label>' +
        '<button type="button" class="btn ghost sm" title="Quitar">✕</button>';
      row.querySelector('.g-monto').addEventListener('input', function () { Peek.syncMonto(); Peek.recalc(); });
      row.querySelector('button').addEventListener('click', function () {
        row.remove(); Peek.syncMonto(); Peek.recalc();
      });
      wrap.appendChild(row);
    },
    gastosTotal: function () {
      var t = 0;
      document.querySelectorAll('#cobro-gastos .gasto-row .g-monto').forEach(function (i) {
        t += leerMonto(i.value);
      });
      return t;
    },
    leerGastos: function () {
      var out = [];
      document.querySelectorAll('#cobro-gastos .gasto-row').forEach(function (row) {
        var desc = (row.querySelector('.g-desc').value || '').trim();
        var monto = leerMonto(row.querySelector('.g-monto').value);
        if (desc && monto) {
          out.push({ desc: desc, monto: monto, trasladar: row.querySelector('.g-trasladar').checked });
        }
      });
      return out;
    },
    recalc: function () {
      var r = Peek._r || {}, base = Number(r.monto) || 0;
      var mora = leerMonto(($('#cobro-mora') || {}).value);
      var gastos = Peek.gastosTotal();
      var v = leerMonto(($('#cobro-monto') || {}).value);
      var saldo = base + mora + gastos - v;
      var el = $('#cobro-calc'); if (!el) return;
      el.innerHTML =
        '<div class="l">' + esc(r.periodo || 'Alquiler') + ' <b>' + money(base) + '</b></div>' +
        (mora ? '<div class="l">Mora <b>' + money(mora) + '</b></div>' : '') +
        (gastos ? '<div class="l">Gastos extra <b>' + money(gastos) + '</b></div>' : '') +
        '<div class="l">Recibís <b>' + money(v) + '</b></div>' +
        '<div class="l tot">' + (saldo > 0 ? 'Queda debiendo' : 'Saldo') +
          ' <b style="color:' + (saldo > 0 ? 'var(--err)' : 'var(--ok)') + '">' +
          money(Math.abs(saldo)) + '</b></div>' +
        (saldo > 0 ? '<p class="hint">Se registra como <b>pago parcial</b>.</p>'
                   : '<p class="hint">Con esto el período queda <b>al día</b>.</p>');
    },
    guardarCobro: function () {
      var r = Peek._r || {}, btn = $('#cobro-ok');
      if (!btn || btn.disabled) return;
      var forma = ($('#cobro-forma .on') || {}).textContent || '';
      var body = {
        cid: r.cid, mes: r.mes, anio: r.anio, precio: r.monto,
        pagado: leerMonto($('#cobro-monto').value),
        mora: Peek.moraTocada ? leerMonto($('#cobro-mora').value) : null,
        gastos: Peek.leerGastos(),
        fecha: ($('#cobro-fecha') || {}).value || '',
        forma_pago: forma.trim(),
        observaciones: ($('#cobro-obs') || {}).value || '',
        idem: Peek.idem
      };
      btn.disabled = true; btn.innerHTML = '<span class="spin"></span> Guardando…';
      fetch('/cobros/rapido', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      }).then(function (resp) { return resp.json().then(function (j) { return { ok: resp.ok, j: j }; }); })
        .then(function (res) {
          if (!res.j.ok) {
            btn.disabled = false; btn.textContent = 'Guardar cobro';
            toast('No se registró el cobro', res.j.error || 'Probá de nuevo.', 'err');
            return;
          }
          toast('Cobro registrado', res.j.saldo > 0
            ? 'Queda un saldo de ' + money(res.j.saldo)
            : 'El período quedó al día', 'ok');
          // No recargamos de una: mostramos el pago guardado con las opciones de
          // recibo (imprimir / PDF / email / WhatsApp), igual que el flujo clásico.
          Peek.cobroOk(res.j);
        })
        .catch(function () {
          btn.disabled = false; btn.textContent = 'Guardar cobro';
          toast('Error de conexión', 'No se pudo registrar el cobro.', 'err');
        });
    },
    // Estado de éxito: el pago ya quedó guardado. Ofrecemos el recibo por los 4
    // canales y un acceso al detalle del contrato (donde el pago figura listado).
    cobroOk: function (j) {
      var saldo = Number(j.saldo) || 0;
      var wa = j.wa_url
        ? '<a class="btn ok" href="' + j.wa_url + '" target="_blank" rel="noopener">WhatsApp</a>'
        : '<button class="btn ghost" type="button" disabled title="El inquilino no tiene un teléfono válido cargado">WhatsApp</button>';
      Peek.open('Pago registrado &#10003;',
        '<div class="calc" style="margin-bottom:14px">' +
          '<div class="l">' + esc(j.quien || 'Inquilino') + '</div>' +
          '<div class="l tot">' + (saldo > 0 ? 'Queda debiendo' : 'Recibido') +
            ' <b style="color:' + (saldo > 0 ? 'var(--err)' : 'var(--ok)') + '">' +
            money(saldo > 0 ? saldo : (Number(j.pagado) || 0)) + '</b></div></div>' +
        '<p class="hint" style="margin-bottom:10px">Imprimí o enviá el recibo:</p>' +
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">' +
          '<a class="btn pri" href="' + j.recibo_url + '" target="_blank" rel="noopener">Abrir recibo</a>' +
          '<a class="btn" href="' + j.pdf_url + '">Descargar PDF</a>' +
          wa +
          '<button class="btn" type="button" id="cobro-email" ' +
            'onclick="Peek.emailRecibo(\'' + j.email_url + '\', \'' + j.recibo_url + '\')">Enviar por email</button>' +
        '</div>' +
        '<p class="hint" style="margin-top:10px">Para <b>WhatsApp</b>: descargá el PDF y adjuntalo ' +
          '(el botón deja el mensaje escrito). <b>Email</b> manda el recibo en PDF al inquilino.</p>',
        '<a class="btn ghost" href="' + j.detalle_url + '">Ver detalle del contrato</a>' +
        '<div style="flex:1"></div>' +
        '<button class="btn pri" type="button" onclick="location.reload()">Seguir cobrando <kbd>&#8629;</kbd></button>');
    },
    // Envía el recibo por email. Si el inquilino no tiene email, abre el recibo,
    // que tiene el campo para cargarlo y reenviar.
    emailRecibo: function (emailUrl, reciboUrl) {
      var btn = $('#cobro-email');
      if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spin"></span> Enviando...'; }
      var reset = function () { if (btn) { btn.disabled = false; btn.innerHTML = 'Enviar por email'; } };
      fetch(emailUrl, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}'
      }).then(function (r) { return r.json(); })
        .then(function (j) {
          if (j.ok) {
            toast('Recibo enviado', j.mensaje || '', 'ok');
            if (btn) { btn.disabled = true; btn.innerHTML = '&#10003; Enviado'; }
          } else if (j.need_email) {
            toast('Falta el email del inquilino', 'Cargalo en el recibo y reenviá.', 'err');
            window.open(reciboUrl, '_blank', 'noopener');
            reset();
          } else {
            toast('No se pudo enviar', j.error || 'Probá desde el recibo.', 'err');
            reset();
          }
        })
        .catch(function () { toast('Error de conexión', 'No se pudo enviar el email.', 'err'); reset(); });
    }
  };
  window.Peek = Peek;

  /* ---- paleta de comandos ---------------------------------------------- */
  var COMANDOS = (window.AURORA_COMANDOS || []);
  var Pal = {
    sel: 0, list: [], timer: null,
    open: function () {
      $('#pal-ov').classList.add('on');
      var q = $('#pal-q'); q.value = ''; q.focus();
      Pal.filtrar('');
    },
    close: function () { $('#pal-ov').classList.remove('on'); },
    abierta: function () { return $('#pal-ov').classList.contains('on'); },
    filtrar: function (q) {
      q = (q || '').trim().toLowerCase();
      var cmds = COMANDOS.filter(function (c) {
        return !q || c.t.toLowerCase().indexOf(q) !== -1 ||
          (c.k || []).some(function (k) { return k.indexOf(q) !== -1; });
      });
      Pal.list = cmds.slice();
      Pal.sel = 0; Pal.paint();
      clearTimeout(Pal.timer);
      if (q.length >= 2) {
        Pal.timer = setTimeout(function () { Pal.buscar(q, cmds); }, 180);
      }
    },
    buscar: function (q, cmds) {
      fetch('/api/buscar?q=' + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (!Pal.abierta()) return;
          var res = [];
          (j.grupos || []).forEach(function (gr) {
            (gr.items || []).forEach(function (it) {
              res.push({ g: gr.titulo, t: it.texto, s: it.sub, url: it.url });
            });
          });
          Pal.list = cmds.concat(res);
          Pal.sel = 0; Pal.paint();
        }).catch(function () {});
    },
    paint: function () {
      var html = '', g = null;
      Pal.list.forEach(function (c, i) {
        if (c.g !== g) { g = c.g; html += '<div class="pal-sec">' + esc(g) + '</div>'; }
        html += '<div class="pal-i ' + (i === Pal.sel ? 'on' : '') + '" data-i="' + i + '">' +
          '<div class="tx"><b>' + esc(c.t) + '</b>' + (c.s ? '<span>' + esc(c.s) + '</span>' : '') + '</div>' +
          (i === Pal.sel ? '<kbd>↵</kbd>' : '') + '</div>';
      });
      $('#pal-res').innerHTML = html ||
        '<div class="empty" style="padding:30px">Nada coincide con esa búsqueda.</div>';
    },
    mover: function (d) {
      if (!Pal.list.length) return;
      Pal.sel = (Pal.sel + d + Pal.list.length) % Pal.list.length;
      Pal.paint();
      var el = $('#pal-res').querySelectorAll('.pal-i')[Pal.sel];
      if (el) el.scrollIntoView({ block: 'nearest' });
    },
    run: function (i) {
      var c = Pal.list[i != null ? i : Pal.sel];
      if (!c) return;
      Pal.close();
      if (c.url) location.href = c.url;
      else if (c.run) c.run();
    }
  };
  window.Pal = Pal;

  document.addEventListener('DOMContentLoaded', function () {
    var q = $('#pal-q');
    if (q) q.addEventListener('input', function (e) { Pal.filtrar(e.target.value); });
    var res = $('#pal-res');
    if (res) {
      res.addEventListener('click', function (e) {
        var it = e.target.closest('.pal-i');
        if (it) Pal.run(Number(it.dataset.i));
      });
      res.addEventListener('mousemove', function (e) {
        var it = e.target.closest('.pal-i');
        if (it && Number(it.dataset.i) !== Pal.sel) { Pal.sel = Number(it.dataset.i); Pal.paint(); }
      });
    }
  });

  /* ---- teclado --------------------------------------------------------- */
  document.addEventListener('keydown', function (e) {
    if (!$('#pal-ov')) return;
    var enInput = /INPUT|TEXTAREA|SELECT/.test((document.activeElement || {}).tagName || '');
    if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault(); Pal.abierta() ? Pal.close() : Pal.open(); return;
    }
    if (Pal.abierta()) {
      if (e.key === 'Escape') Pal.close();
      if (e.key === 'ArrowDown') { e.preventDefault(); Pal.mover(1); }
      if (e.key === 'ArrowUp') { e.preventDefault(); Pal.mover(-1); }
      if (e.key === 'Enter') { e.preventDefault(); Pal.run(); }
      return;
    }
    if (e.key === 'Escape') { Peek.close(); return; }
    if (enInput || e.ctrlKey || e.metaKey || e.altKey) return;
    var atajos = window.AURORA_ATAJOS || {};
    var destino = atajos[e.key.toLowerCase()];
    if (destino) { e.preventDefault(); location.href = destino; }
  });
  /* ---- menús de fila (details.rmenu) ----------------------------------- */
  document.addEventListener('click', function (e) {
    var abierto = e.target.closest('details.rmenu[open]');
    Array.prototype.forEach.call(document.querySelectorAll('details.rmenu[open]'), function (d) {
      if (d !== abierto) d.removeAttribute('open');
    });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    Array.prototype.forEach.call(document.querySelectorAll('details.rmenu[open]'), function (d) {
      d.removeAttribute('open');
    });
  });
})();
