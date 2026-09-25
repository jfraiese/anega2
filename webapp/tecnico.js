/* anega2 · vista «Detalle técnico» del visor: pestañas, capas, click con valores de la grilla. Usa el S global de app.js. */
const Tecnico = (() => {
const dataUrl = rel => S.base + rel;
const GROUPS = ['Referencia', 'Terreno', 'Histórico', 'Simulación'];
const GRID_LABELS = { dem: 'Cota (m snm)', hand: 'HAND · altura sobre drenaje (m)', slope_pct: 'Pendiente (%)', twi: 'TWI', sink_m: 'Depresión cerrada (m)',
  facc_ha: 'Área de aporte (ha)', dist_m: 'Dist. de flujo al drenaje (m)', jrc_occ: 'JRC ocurrencia 1984-2021 (%)' };

const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, attrs = {}, html = '') => { const e = document.createElement(tag); Object.entries(attrs).forEach(([k, v]) => k === 'class' ? e.className = v : e.setAttribute(k, v)); e.innerHTML = html; return e; };
const fmt = (v, d = 2) => {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Number(v))) v = Number(v);
  if (typeof v === 'number') return Number.isNaN(v) ? '—' : v.toLocaleString('es-AR', { maximumFractionDigits: d, minimumFractionDigits: 0 });
  return String(v);
};
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');

function md(text) {
  // une líneas envueltas (continuaciones indentadas) con la línea lógica anterior
  const logical = [];
  for (const raw of (text || '').split('\n')) {
    if (/^\s+\S/.test(raw) && logical.length && logical[logical.length - 1].trim() !== '') logical[logical.length - 1] += ' ' + raw.trim();
    else logical.push(raw);
  }
  text = logical.join('\n');
  let html = '', list = null;
  const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`(.+?)`/g, '<code>$1</code>').replace(/\{\{[A-Z_]+\}\}/g, '<em class="muted">(sección de simulación en preparación)</em>');
  const close = () => { if (list) { html += `</${list}>`; list = null; } };
  for (const raw of (text || '').split('\n')) {
    const line = raw.trimEnd();
    if (/^\s*[-*] /.test(line)) { if (list !== 'ul') { close(); html += '<ul>'; list = 'ul'; } html += '<li>' + inline(line.replace(/^\s*[-*] /, '')) + '</li>'; }
    else if (/^\d+\. /.test(line)) { if (list !== 'ol') { close(); html += '<ol>'; list = 'ol'; } html += '<li>' + inline(line.replace(/^\d+\. /, '')) + '</li>'; }
    else if (/^\s+\S/.test(raw) && list) { html = html.replace(/<\/li>$/, ' ' + inline(line.trim()) + '</li>'); }
    else if (line.trim() === '---') { close(); }
    else if (line.trim()) { close(); html += '<p>' + inline(line) + '</p>'; }
  }
  close(); return html;
}

function table(columns, rows, opts = {}) {
  const t = el('table');
  const cols = opts.columns || columns;
  t.appendChild(el('thead', {}, '<tr>' + cols.map(c => `<th>${esc(opts.rename?.[c] ?? c)}</th>`).join('') + '</tr>'));
  const tb = el('tbody');
  rows.forEach((r, i) => {
    const obj = Array.isArray(r) ? Object.fromEntries(columns.map((c, j) => [c, r[j]])) : r;
    const tr = el('tr', opts.rowClass ? { class: opts.rowClass(obj, i) } : {});
    tr.innerHTML = cols.map(c => `<td>${fmt(obj[c], opts.digits ?? 2)}</td>`).join('');
    if (opts.onClick) { tr.style.cursor = 'pointer'; tr.onclick = () => opts.onClick(obj, tr); }
    tb.appendChild(tr);
  });
  t.appendChild(tb); return t;
}

/* ---------------- mapa y capas ---------------- */
async function buildLayers() {
  for (const def of S.manifest.layers) {
    let layer;
    if (def.type === 'geojson') {
      const gj = await (await fetch(dataUrl(def.url))).json();
      layer = L.geoJSON(gj, {
        style: () => def.style, pointToLayer: (f, ll) => L.circleMarker(ll, def.style),
        onEachFeature: (f, l) => { const n = f.properties && (f.properties.Name || f.properties.name); if (n) l.bindTooltip(String(n), { sticky: true }); },
      });
    } else {
      layer = L.imageOverlay(dataUrl(def.url), def.bounds, { opacity: S.opacity, interactive: false, pane: 'rasters' });
    }
    S.layers[def.id] = { def, layer, on: false };
  }
  S.manifest.layers.filter(d => d.visible).forEach(d => show_(d.id, false));
  S.scenario = S.manifest.scenarios.find(s => s.id === 'P100_24h')?.id || S.manifest.scenarios[0]?.id || null;
  S.scene = null;
  refresh();
}
const exclusiveKey = def => def.type === 'image' ? (def.subgroup || def.group) : null;
function show_(id, doRefresh = true) {
  const L_ = S.layers[id]; if (!L_ || L_.on) return;
  const k = exclusiveKey(L_.def);
  if (k) Object.values(S.layers).forEach(o => { if (o.on && exclusiveKey(o.def) === k) hide_(o.def.id, false); });
  L_.layer.addTo(S.map); L_.on = true;
  if (L_.def.type === 'geojson') L_.layer.bringToFront();
  if (doRefresh) refresh();
}
function hide_(id, doRefresh = true) { const L_ = S.layers[id]; if (!L_ || !L_.on) return; S.map.removeLayer(L_.layer); L_.on = false; if (doRefresh) refresh(); }
function toggle(id, on) { on ? show_(id) : hide_(id); }
function refresh() { renderLayerPanel(); renderLegend(); }

function renderLayerPanel() {
  const root = $('#layer-panel'); root.innerHTML = '';
  const sc = S.manifest.scenarios.find(s => s.id === S.scenario); const sn = S.manifest.scenes.find(s => s.id === S.scene);
  const hiddenIds = new Set();
  S.manifest.scenes.forEach(s => { if (s.id !== S.scene) { hiddenIds.add(s.db_layer); if (s.w_layer) hiddenIds.add(s.w_layer); } });
  S.manifest.scenarios.forEach(s => { if (s.id !== S.scenario) { hiddenIds.add(s.h_layer); hiddenIds.add(s.d_layer); if (s.v_layer) hiddenIds.add(s.v_layer); } });
  for (const g of GROUPS) {
    const defs = S.manifest.layers.filter(d => d.group === g && !hiddenIds.has(d.id));
    if (!defs.length) continue;
    const box = el('div', { class: 'group' }); box.appendChild(el('h4', {}, g));
    if (g === 'Histórico') box.appendChild(el('div', { class: 'muted' }, sn ? `Escena Sentinel-1 activa: ${esc(sn.label)} (cambiar en la pestaña Histórico)` : 'Elegí una escena Sentinel-1 en la pestaña Histórico.'));
    if (g === 'Simulación') box.appendChild(el('div', { class: 'muted' }, sc ? `Escenario activo: ${esc(sc.label)} (cambiar en la pestaña Simulación)` : ''));
    for (const d of defs) {
      const o = S.layers[d.id];
      const lab = el('label');
      const cb = el('input', { type: 'checkbox' }); cb.checked = o.on; cb.onchange = () => toggle(d.id, cb.checked);
      lab.appendChild(cb);
      const color = d.type === 'geojson' ? (d.style.color || '#333') : (d.legend.type === 'gradient' ? `linear-gradient(90deg, ${d.legend.stops.join(',')})` : d.legend.classes[0].color);
      const sw = el('span', { class: 'swatch' }); sw.style.background = color; lab.appendChild(sw);
      lab.appendChild(el('span', {}, esc(d.title) + (d.type === 'image' ? ' <span class="muted">(raster)</span>' : '')));
      if (d.description) lab.title = d.description;
      box.appendChild(lab);
    }
    root.appendChild(box);
  }
}
function renderLegend() {
  const root = $('#legend'); root.innerHTML = '';
  Object.values(S.layers).filter(o => o.on && o.def.type === 'image').forEach(o => {
    const lg = o.def.legend; const it = el('div', { class: 'item' }, `<div><b>${esc(o.def.title)}</b></div>`);
    if (lg.type === 'gradient') {
      it.appendChild(el('div', { class: 'bar', style: `background:linear-gradient(90deg, ${lg.stops.join(',')})` }));
      it.appendChild(el('div', { class: 'ticks' }, `<span>${fmt(lg.vmin)}</span><span>${esc(lg.unit || '')}</span><span>${fmt(lg.vmax)}</span>`));
    } else {
      lg.classes.forEach(c => it.appendChild(el('div', { class: 'cls' }, `<span class="swatch" style="background:${c.color}"></span>${esc(c.label)}`)));
    }
    root.appendChild(it);
  });
}
function setOpacity(v) { S.opacity = v; Object.values(S.layers).forEach(o => { if (o.def.type === 'image') o.layer.setOpacity(v); }); }

function onMapClick(e) {
  const g = S.grid; if (!g) return;
  const [x, y] = proj4('WGS84', g.proj4, [e.latlng.lng, e.latlng.lat]);
  const [a, , c, , e_, f] = g.transform;
  const col = Math.floor((x - c) / a), row = Math.floor((y - f) / e_);
  let html = `<div class="muted">${e.latlng.lat.toFixed(6)}, ${e.latlng.lng.toFixed(6)} · E ${x.toFixed(0)} N ${y.toFixed(0)}</div>`;
  if (row < 0 || col < 0 || row >= g.nrows || col >= g.ncols) {
    html += '<p>Fuera de la grilla de valores (±2 km del lote).</p>';
  } else {
    const i = row * g.ncols + col; const rows = [];
    for (const [k, arr] of Object.entries(g.layers)) {
      let label = GRID_LABELS[k];
      if (!label) { const m = k.match(/^(hmax|dur)_(.+)$/); if (m) { const sc = S.manifest.scenarios.find(s => s.id === m[2]); label = (m[1] === 'hmax' ? 'Lámina máx. ' : 'Duración >5 cm ') + (sc ? sc.label : m[2]) + (m[1] === 'hmax' ? ' (m)' : ' (h)'); } else label = k; }
      const v = arr[i]; rows.push(`<tr><td>${esc(label)}</td><td><b>${v === null ? '—' : fmt(v, 3)}</b></td></tr>`);
    }
    html += `<table>${rows.join('')}</table>`;
  }
  L.popup({ maxWidth: 360 }).setLatLng(e.latlng).setContent(html).openOn(S.map);
}

/* ---------------- panel ---------------- */
function renderVerdict() {
  const k = S.stats.key || {}, hi = S.stats.hand_incert; const sc = S.manifest.scenarios; const P100 = sc.find(s => s.id === 'P100_24h'); const P100s = sc.find(s => s.id === 'P100_24h_sat');
  const aoiLab = `${fmt(S.manifest.aoi_m, 0)} m`;
  const anyWater = (S.manifest.scenes || []).some(s => (s.pct_agua_lote ?? 0) > 0) || (S.stats.jrc.rows[0] && Number(S.stats.jrc.rows[0][2]) > 0);
  const cards = [
    ['Cota del lote', `${fmt(k.z_min_lote)} – ${fmt(k.z_max_lote)} m`],
    ['HAND · altura sobre el drenaje', `${fmt(k.hand_min_lote)} – ${fmt(k.hand_max_lote)} m` + (hi ? ` · ± ${fmt(hi.sigma)} m<div class="k">prob. de &lt; 1 m: ${fmt(hi.p_lt1, 0)} %</div>` : '')],
    ['Pendiente media', `${fmt(k.slope_mean_lote_pct)} %`],
    ['Drenaje ≥ 0,5 km² más cercano', `${fmt(k.dist_euclid_red_05km2_m, 0)} m`],
    ['Cuenca aportante', `${fmt(k.cuenca_celda_mas_baja_ha)} – ${fmt(k.cuenca_todo_el_lote_ha)} ha`],
    ['Depresión cerrada en el lote', String(k.lote_intersecta_depresion) === 'True' ? 'Sí' : 'No'],
    ['Agua histórica (Landsat 1984-2021, Sentinel-1)', anyWater ? 'hay detecciones (ver Histórico)' : `0 % en lote y ${aoiLab}`],
    ['Lámina máx. 100 mm/24 h', P100 && P100.hmax_lote_m != null ? `${fmt(P100.hmax_lote_m * 100, 0)} cm` + (P100s && P100s.hmax_lote_m != null ? ` · saturado ${fmt(P100s.hmax_lote_m * 100, 0)} cm` : '') : 'pendiente'],
  ];
  $('#key-cards').innerHTML = cards.map(([kk, v]) => `<div class="card"><div class="v">${v}</div><div class="k">${kk}</div></div>`).join('');
  $('#verdict').innerHTML = md(S.stats.verdict_md);
  $('#field').innerHTML = md(S.stats.field_md);
  $('#title').textContent = S.manifest.titulo || S.manifest.nombre;
  document.title = `anega2 · ${S.manifest.titulo || S.manifest.nombre}`;
  $('#subtitle').textContent = `Lote ${fmt(S.stats.lote.area_m2, 0)} m² · centroide ${S.stats.lote.centroide_wgs84.map(v => v.toFixed(6)).join(', ')} · ${S.manifest.crs} · DEM primario ${S.stats.primary}${S.manifest.res_m ? ` (${fmt(S.manifest.res_m, 0)} m)` : ''} · buffer ${aoiLab} · generado ${(S.manifest.generado || '').slice(0, 16).replace('T', ' ')}`;
  $('#dep-title').textContent = `Depresiones cerradas dentro de los ${aoiLab}`;
  $('#sim-intro').textContent = `Landlab OverlandFlow + Green-Ampt sobre el DEM primario${S.manifest.res_m ? ` (${fmt(S.manifest.res_m, 0)} m)` : ''}. Elegí un escenario: cambia la lámina máxima en el mapa.`;
}
function renderTerrain() {
  const t = S.stats.terrain;
  $('#terrain-table').appendChild(table(t.columns, t.rows, { rowClass: (o) => /hand|z_min_lote|z_max_lote|cuenca|dist_euclid_red_05|depresion/.test(o.variable) ? 'hl' : '' }));
  const d = S.stats.depresiones; $('#dep-table').appendChild(d.rows.length ? table(d.columns, d.rows) : el('p', { class: 'muted' }, 'Sin depresiones cerradas en el buffer.'));
}
function renderHistorico() {
  const j = S.stats.jrc; $('#jrc-table').appendChild(table(j.columns, j.rows)); $('#jrc-extra').textContent = S.stats.jrc_extra || '';
  const list = $('#scene-list');
  const none = el('label'); const r0 = el('input', { type: 'radio', name: 'scene' }); r0.checked = !S.scene; r0.onchange = () => selectScene(null); none.append(r0, el('span', {}, 'ninguna escena en el mapa')); list.appendChild(none);
  S.manifest.scenes.forEach(s => {
    const lab = el('label', { 'data-id': s.id }); const r = el('input', { type: 'radio', name: 'scene' }); r.onchange = () => selectScene(s.id);
    lab.append(r, el('span', {}, esc(s.label))); list.appendChild(lab);
  });
  const aoiLab = `${fmt(S.manifest.aoi_m, 0)} m`, hidroLab = `${fmt(S.manifest.hidro_m / 1000, 1)} km`;
  const cols = ['evento', 'fecha', 'momento', 'umbral_dB', 'pct_agua_lote', 'pct_agua_aoi', 'pct_agua_500m', 'pct_agua_hidro', 'pct_agua_10km', 'pct_aoi_caida_3dB', 'pct_500m_caida_3dB'];
  const sar = S.stats.sar;
  $('#sar-table').appendChild(table(sar.columns, sar.rows, { columns: cols.filter(c => sar.columns.includes(c)),
    rename: { pct_agua_lote: 'agua lote %', pct_agua_aoi: `agua ${aoiLab} %`, pct_agua_500m: `agua ${aoiLab} %`, pct_agua_hidro: `agua ${hidroLab} %`, pct_agua_10km: `agua ${hidroLab} %`, pct_aoi_caida_3dB: `${aoiLab} con caída >3 dB %`, pct_500m_caida_3dB: `${aoiLab} con caída >3 dB %`, umbral_dB: 'umbral dB' },
    onClick: (o) => { const s = S.manifest.scenes.find(x => x.escena === o.escena); if (s) { selectScene(s.id); $(`#scene-list label[data-id="${s.id}"] input`).checked = true; } } }));
}
function selectScene(id) {
  const prev = S.manifest.scenes.find(s => s.id === S.scene);
  if (prev) { hide_(prev.db_layer, false); if (prev.w_layer) hide_(prev.w_layer, false); }
  S.scene = id; const s = S.manifest.scenes.find(x => x.id === id);
  if (s) { show_(s.db_layer, false); if (s.w_layer) show_(s.w_layer, false); }
  document.querySelectorAll('#scene-list label').forEach(l => l.classList.toggle('active', l.dataset.id === id));
  refresh();
}
function renderSimulacion() {
  const list = $('#scenario-list');
  S.manifest.scenarios.forEach(s => {
    const lab = el('label', { 'data-id': s.id }); const r = el('input', { type: 'radio', name: 'scenario' }); r.checked = s.id === S.scenario; r.onchange = () => selectScenario(s.id);
    lab.append(r, el('span', {}, `${esc(s.label)} <span class="muted">${s.hmax_lote_m != null ? `· lote h máx ${fmt(s.hmax_lote_m * 100, 0)} cm · ${fmt(s.pct_lote_gt5cm, 0)} % > 5 cm` : '· estadísticas pendientes'}</span>`)); list.appendChild(lab);
  });
  const aoiLab = `${fmt(S.manifest.aoi_m, 0)} m`;
  const rg = S.stats.rog; const cols = ['escenario', 'P_mm', 'dur_h', 'Ks_mm_h', 'hmax_lote_m', 'hmedia_lote_m', 'pct_lote_gt5cm', 'pct_lote_gt20cm', 'dur_max_lote_h', 'pct_aoi_gt5cm', 'pct_aoi_gt20cm', 'pct_500m_gt5cm', 'pct_500m_gt20cm', 'infil_media_mm', 'escurrido_pct'];
  $('#rog-table').appendChild(table(rg.columns, rg.rows, { columns: cols.filter(c => rg.columns.includes(c)), digits: 3,
    rename: { hmax_lote_m: 'h máx lote (m)', hmedia_lote_m: 'h media lote (m)', pct_lote_gt5cm: 'lote >5 cm %', pct_lote_gt20cm: 'lote >20 cm %', dur_max_lote_h: 'anegado máx (h)', pct_aoi_gt5cm: `${aoiLab} >5 cm %`, pct_aoi_gt20cm: `${aoiLab} >20 cm %`, pct_500m_gt5cm: `${aoiLab} >5 cm %`, pct_500m_gt20cm: `${aoiLab} >20 cm %`, infil_media_mm: 'infiltrado (mm)', escurrido_pct: 'escurrido %' },
    rowClass: (o) => o.escenario === S.scenario ? 'hl' : '' }));
  $('#rog-params').textContent = JSON.stringify(S.stats.rog_params, null, 1);
  S.charts.compare = new Chart($('#scen-compare'), { type: 'bar', data: { labels: S.manifest.scenarios.map(s => s.label.replace(/ · suelo saturado.*$/, ' sat.')),
    datasets: [{ label: 'h máx en el lote (cm)', data: S.manifest.scenarios.map(s => (s.hmax_lote_m ?? 0) * 100), backgroundColor: '#1565c0' },
               { label: '% del lote con > 5 cm', data: S.manifest.scenarios.map(s => s.pct_lote_gt5cm ?? 0), backgroundColor: '#90caf9' }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { title: { display: true, text: 'Efecto en el lote por escenario' } }, scales: { x: { ticks: { font: { size: 10 } } } } } });
  drawHyeto();
}
function drawHyeto() {
  const s = S.manifest.scenarios.find(x => x.id === S.scenario); if (!s) return;
  const n = s.hyetograph_mm.length; const dt = s.dur_h / n;
  const labels = s.hyetograph_mm.map((_, i) => (dt >= 1 ? `${i + 1} h` : `${Math.round((i + 1) * dt * 60)} min`));
  if (S.charts.hyeto) S.charts.hyeto.destroy();
  S.charts.hyeto = new Chart($('#hyeto'), { type: 'bar', data: { labels, datasets: [{ label: `mm por intervalo (${dt >= 1 ? dt + ' h' : Math.round(dt * 60) + ' min'})`, data: s.hyetograph_mm, backgroundColor: '#42a5f5' }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { title: { display: true, text: `Hietograma · ${s.label} · Ks ${fmt(s.Ks_mm_h)} mm/h · infiltrado ${fmt(s.infil_media_mm, 0)} mm` } }, scales: { x: { ticks: { maxTicksLimit: 12, font: { size: 10 } } } } } });
}
function selectScenario(id) {
  const prev = S.manifest.scenarios.find(s => s.id === S.scenario);
  const wasH = prev && S.layers[prev.h_layer]?.on, wasD = prev && S.layers[prev.d_layer]?.on, wasV = prev && prev.v_layer && S.layers[prev.v_layer]?.on;
  if (prev) { hide_(prev.h_layer, false); hide_(prev.d_layer, false); if (prev.v_layer) hide_(prev.v_layer, false); }
  S.scenario = id; const s = S.manifest.scenarios.find(x => x.id === id);
  if (s) { if (wasH || (!wasH && !wasD)) show_(s.h_layer, false); if (wasD) show_(s.d_layer, false); if (wasV && s.v_layer) show_(s.v_layer, false); }
  document.querySelectorAll('#scenario-list label').forEach(l => l.classList.toggle('active', l.dataset.id === id));
  document.querySelectorAll('#rog-table tr').forEach(tr => tr.classList.toggle('hl', tr.firstChild && tr.firstChild.textContent === id));
  drawHyeto(); refresh();
}
function renderFigures() {
  const g = $('#gallery');
  (S.figures || []).forEach(f => { const fig = el('figure'); fig.innerHTML = `<a href="${dataUrl(f.file)}" target="_blank"><img loading="lazy" src="${dataUrl(f.file)}" alt="${esc(f.caption)}"></a><figcaption>${esc(f.caption)}</figcaption>`; g.appendChild(fig); });
}
function initTabs() {
  document.querySelectorAll('.tabs button').forEach(b => b.onclick = () => {
    document.querySelectorAll('.tabs button').forEach(x => x.classList.toggle('active', x === b));
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.id === 'tab-' + b.dataset.tab));
    if (b.dataset.tab === 'simulacion') Object.values(S.charts).forEach(c => c.resize());
  });
}

let prendidas = [];
async function init() {
  initTabs();
  await buildLayers();
  renderVerdict(); renderTerrain(); renderHistorico(); renderSimulacion(); renderFigures();
  document.querySelectorAll('#scenario-list label').forEach(l => l.classList.toggle('active', l.dataset.id === S.scenario));
  $('#opacity').oninput = e => setOpacity(parseFloat(e.target.value));
  $('#btn-fit').onclick = () => { const o = S.layers.lote; if (o) S.map.fitBounds(o.layer.getBounds().pad(4)); };
}
// al salir se apaga todo lo prendido salvo el lote (queda como referencia en la vista Resumen); show() lo restaura
function hide() { prendidas = Object.values(S.layers).filter(o => o.on && o.def.id !== 'lote').map(o => o.def.id); prendidas.forEach(id => hide_(id, false)); show_('lote', false); S.map.off('click', onMapClick); $('#legend').innerHTML = ''; }
function show() { prendidas.forEach(id => show_(id, false)); prendidas = []; S.map.on('click', onMapClick); refresh(); }
return { init, show, hide };
})();
