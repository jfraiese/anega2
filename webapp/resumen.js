/* anega2 · vista «Resumen» (¿Dónde hay agua?): lluvia → agua en el mapa hora a hora, certeza entre DEMs e historia de lluvias. */
const Resumen = (() => {
  let map, S, R = { dur: 24, suelo: 'normal', u: 5, t: 0, P: 100 }, overlay = null, canvas = document.createElement('canvas'), grilla = null, updGrilla = () => {}, charts = {}, s1layer = null, seq = 0, seqEv = 0, debounce = null;
  const $ = s => document.querySelector(s);
  const DUR = [[3, 'Chaparrón 3 h'], [24, 'Día de lluvia'], [72, 'Temporal 3 días']];
  const SUELO = [['normal', 'Suelo normal'], ['saturado', 'Saturado']];
  const UMB = [[5, 'más de 5 cm'], [20, 'más de 20 cm']];
  const visible = () => !$('#panel-resumen').hidden;

  function pills(el, opts, cur, fn, sinDatos = () => false) {
    el.innerHTML = ''; opts.forEach(([v, lab]) => { const b = document.createElement('button'); b.textContent = lab; b.className = v === cur ? 'on' : ''; b.disabled = v !== cur && sinDatos(v); b.onclick = () => fn(v); el.appendChild(b); });
  }
  // valores de P calculados para la combinación actual: la grilla nueva es regular (paso 5, interpola);
  // el formato viejo o una grilla propia puede no serlo (el deslizador salta entre los calculados)
  const Ps = (dur = R.dur, suelo = R.suelo) => Lib.pDisponibles(Sim.idx.escenarios, dur, suelo);
  function deslizador() {
    const ps = Ps(), el = $('#r-mm'), reg = Lib.grillaRegular(ps);
    if (ps.length) { el.min = ps[0]; el.max = ps[ps.length - 1]; el.step = reg ? 5 : 1; R.P = Lib.ajustarP(ps, R.P); }
    el.disabled = ps.length < 2; el.value = R.P; $('#r-mm-v').textContent = `${R.P} mm`; $('#r-nota').hidden = reg || ps.length < 2;
  }
  const clima = () => Sim.idx.clima || { disponible: false };
  function gumbel(fuente) { const c = clima(); return c.disponible && c.gumbel && c.gumbel[fuente] ? c.gumbel[fuente][String(R.dur)] : null; }
  function pInicial() {                                  // tormenta de ~10 años (ERA5, 24 h), redondeada a 5 mm y acotada
    const g = gumbel('era5'); if (!g || !(g.beta > 0)) return 100;
    const mm = g.mu - g.beta * Math.log(-Math.log(0.9)); return Math.round(mm / 5) * 5;   // deslizador() lo acota a lo calculado
  }
  // estadísticas del lote: serie nativa (30 m, desde <id>_meta.json vía index.json) si está disponible;
  // si no (datos generados antes de este cambio), se cae a la serie recalculada de los cuadros 3857.
  const serieLote = (m, u) => (m.loteLo ? Lib.loteSerieNativa(m.loteLo, m.loteHi, m.w, u) : Lib.loteSerie(m.h, Sim.idx.lote_idx, u));
  async function actualizar(mantenerHora = true) {
    const mio = ++seq;                                   // el deslizador dispara muchas llamadas: sólo vale la última
    let m;
    try { m = await Sim.mezcla(R.P, R.dur, R.suelo, Ps()); } catch (e) {
      if (mio !== seq) return; console.error(e); $('#r-frase').textContent = `No hay simulación para esta combinación (${e.message}): corré anega2 run ${S.project} --fase lluvia web.`; return;
    }
    if (mio !== seq) return;
    R.mezcla = m;
    const H = R.mezcla.h.length; $('#r-t').max = H - 1;
    const serie = serieLote(R.mezcla, R.u);
    if (!mantenerHora || R.t >= H) R.t = serie.horaPico;
    $('#r-t').value = R.t; $('#r-cortado').hidden = !R.mezcla.cortado;
    pintarHora(); frase(serie); curva(serie); maximos();
  }
  function pintarHora() {
    if (!R.mezcla) return;
    const t = R.t, cert = R.u === 5 ? R.mezcla.c5[t] : R.mezcla.c20[t];
    Sim.pintar(canvas, R.mezcla.h[t], cert);
    canvas.toBlob(b => {
      const url = URL.createObjectURL(b);
      if (!overlay) { overlay = L.imageOverlay(url, Sim.idx.grid.bounds_wgs84, { pane: 'rasters', className: 'sim-overlay', interactive: false }); if (visible()) overlay.addTo(map); }
      else { URL.revokeObjectURL(overlay._url); overlay.setUrl(url); }
    });
    const e = Sim.idx.escenarios[Sim.idDe(R.mezcla.lo, R.dur, R.suelo)];
    const acum = e.lluvia_acum_mm[Math.min(t, e.lluvia_acum_mm.length - 1)] * (R.P / R.mezcla.lo);
    $('#r-t-v').textContent = `hora ${t} · llovieron ${Lib.fmt(Math.min(acum, R.P))} mm`;
    if (charts.curva) charts.curva.draw();
  }
  function frase(serie) {
    const loteCert = Sim.idx.lote_idx.map(i => (R.u === 5 ? R.mezcla.c5 : R.mezcla.c20)[serie.horaPico][i]).filter((_, k) => R.mezcla.h[serie.horaPico][Sim.idx.lote_idx[k]] > R.u).sort((a, b) => a - b);
    const med = loteCert.length ? loteCert[Math.floor(loteCert.length / 2)] : 0;
    const ens = R.mezcla.ensamble || [];
    const ge = gumbel('era5'), gc = gumbel('chirps');
    const mx = clima().disponible ? ((clima().maximos || {}).era5 || {})[String(R.dur)] : null;   // máximos anuales de ESTA duración
    const maxH = mx && mx.length ? Math.max(...mx.map(r => r[1])) : null, desde = mx && mx.length ? mx[0][0] : null;
    $('#r-frase').textContent = Lib.frase({ P: R.P, dur: R.dur, hmaxCm: serie.hmax[serie.horaPico], pct: serie.pct[serie.horaPico], horasConAgua: serie.horasConAgua,
      nivel: Lib.nivelCerteza(med), certezaSoloVecindad: ens.length < 2,
      Tera5: ge ? Lib.retornoAnios(R.P, ge) : NaN, Tchirps: gc ? Lib.retornoAnios(R.P, gc) : null, maxHistorico: maxH, desde });
  }
  const horaActual = { id: 'horaActual', afterDraw(c) {
    const x = c.scales.x.getPixelForValue(R.t), { top, bottom } = c.chartArea, g = c.ctx;
    g.save(); g.strokeStyle = '#e65100'; g.lineWidth = 1.5; g.beginPath(); g.moveTo(x, top); g.lineTo(x, bottom); g.stroke(); g.restore(); } };
  function curva(serie) {
    const e = Sim.idx.escenarios[Sim.idDe(R.mezcla.lo, R.dur, R.suelo)], k = R.P / R.mezcla.lo;
    const lluvia = serie.hmax.map((_, i) => (i === 0 || i >= e.lluvia_acum_mm.length ? 0 : (e.lluvia_acum_mm[i] - e.lluvia_acum_mm[i - 1]) * k));
    if (charts.curva) charts.curva.destroy();
    charts.curva = new Chart($('#r-curva'), { type: 'bar', data: { labels: serie.hmax.map((_, i) => i), datasets: [
      { type: 'bar', label: 'lluvia (mm por hora)', data: lluvia, backgroundColor: '#90caf9', yAxisID: 'y1' },
      { type: 'line', label: 'agua en el lote (cm)', data: serie.hmax, borderColor: '#0d47a1', pointRadius: 0, yAxisID: 'y' }] },
      options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { labels: { boxWidth: 10, font: { size: 10 } } } },
        scales: { x: { title: { display: true, text: 'hora' }, ticks: { maxTicksLimit: 8 } }, y: { beginAtZero: true, title: { display: true, text: 'cm' } },
                  y1: { position: 'right', beginAtZero: true, grid: { drawOnChartArea: false }, title: { display: true, text: 'mm/h' } } } },
      plugins: [horaActual] });
  }
  const DUR_LAB = { 3: '3 h', 24: '24 h', 72: '72 h' };
  function maximos() {
    const c = clima(), el = $('#r-veces');
    if (charts.max) { charts.max.destroy(); charts.max = null; }
    if (!c.disponible) { el.textContent = `Sin datos de lluvia histórica: corré anega2 run ${S.project} --fase clima.`; return; }
    const mx = c.maximos || {}, e5 = (mx.era5 || {})[String(R.dur)] || [], ch = (mx.chirps || {})[String(R.dur)] || [];
    if (!e5.length) { el.textContent = `ERA5 no tiene máximos de ${DUR_LAB[R.dur]}.`; return; }
    const anios = e5.map(r => r[0]), chMap = Object.fromEntries(ch.map(r => [r[0], r[1]])), sup = e5.filter(r => r[1] >= R.P);
    charts.max = new Chart($('#r-maximos'), { type: 'bar', data: { labels: anios, datasets: [
      { type: 'bar', label: 'ERA5', data: e5.map(r => r[1]), backgroundColor: e5.map(r => (r[1] >= R.P ? '#e65100' : '#b0bec5')) },
      { type: 'line', label: 'CHIRPS', data: anios.map(a => chMap[a] ?? null), showLine: false, pointRadius: 2, borderColor: '#6d4c41', backgroundColor: '#6d4c41' },
      { type: 'line', label: `${R.P} mm`, data: anios.map(() => R.P), borderColor: '#1565c0', borderDash: [5, 4], pointRadius: 0 }] },
      options: { responsive: true, maintainAspectRatio: false, animation: false,
        plugins: { legend: { labels: { boxWidth: 10, font: { size: 10 } } }, title: { display: true, text: `Lluvia máxima en ${DUR_LAB[R.dur]} de cada año` } },
        scales: { x: { ticks: { maxTicksLimit: 8 } }, y: { beginAtZero: true, title: { display: true, text: 'mm' } } } } });
    el.textContent = sup.length
      ? `${R.P} mm en ${DUR_LAB[R.dur]} se superó ${sup.length} ${sup.length === 1 ? 'vez' : 'veces'} desde ${anios[0]} (ERA5): ${sup.slice(-4).map(r => r[0]).join(', ')}${sup.length > 4 ? '…' : ''}.`
      : `Desde ${anios[0]} nunca llovió ${R.P} mm en ${DUR_LAB[R.dur]} (ERA5).`;
  }
  function eventos() {
    const c = clima(), box = $('#r-eventos'); box.innerHTML = '';
    if (!c.disponible || !c.eventos) return;
    const todos = new Map();                            // históricos ∪ era Sentinel-1, sin repetir, más reciente primero
    [...(c.eventos.historicos || []), ...(c.eventos.sentinel || [])].forEach(ev => { if (ev && ev.id && !todos.has(ev.id)) todos.set(ev.id, ev); });
    [...todos.values()].filter(ev => ev.era5_72 != null).sort((a, b) => (a.fecha < b.fecha ? 1 : a.fecha > b.fecha ? -1 : 0)).forEach(ev => {
      const b = document.createElement('button'); b.className = 'ev'; b.textContent = `${ev.fecha} · ${Lib.fmt(ev.era5_72)} mm en 72 h`;
      b.onclick = () => { box.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); detalleEvento(ev); }; box.appendChild(b);
    });
  }
  function sarFilas() {                                 // stats.sar {columns, rows[][]} → objetos planos para Lib.matchRadar
    const t = S.stats.sar || { columns: [], rows: [] };
    return (t.rows || []).map(r => (Array.isArray(r) ? Object.fromEntries(t.columns.map((c, j) => [c, r[j]])) : r));
  }
  function radar(ev, m) {
    if (!m) return ev.fecha < '2014-10-03' ? 'No había radar Sentinel-1 en esa fecha.' : 'Esa fecha no se analizó con radar.';
    const filas = m.filas;
    if (filas.every(r => r.escena === 'SIN COBERTURA')) return 'No hubo pasadas del radar cerca de esa fecha.';
    if (filas.some(r => r.escena === 'SIN PASADA A TIEMPO')) return 'El radar no pasó a tiempo: no se puede saber si hubo agua.';
    const post = filas.find(r => r.momento === 'post'); if (!post) return 'No hay escena del radar después de la tormenta.';
    const d = post.dias_desde_evento, pct = post.pct_agua_lote;
    return pct > 0 ? `El radar pasó ${d} días después y vio agua en el ${Lib.fmt(pct)} % del lote.` : `El radar pasó ${d} días después y no vio agua en el lote.`;
  }
  async function detalleEvento(ev) {
    const mio = ++seqEv, box = $('#r-evento');
    const ps = Ps(72, 'normal'), P = Lib.ajustarP(ps, Math.round(ev.era5_72 / 5) * 5);
    let modelo;
    try {
      const m = await Sim.mezcla(P, 72, 'normal', ps), s = serieLote(m, 5), hp = s.horaPico;
      modelo = s.hmax[hp] < 5 ? 'el modelo no pone agua en el lote' : `el modelo pone hasta ${s.hmax[hp]} cm en el ${Lib.fmt(s.pct[hp])} % del lote`;
    } catch (e) { console.error(e); modelo = 'no hay simulación de 72 h para compararla'; }
    if (mio !== seqEv) return;                           // llegó tarde: ya se eligió otro evento
    const m = Lib.matchRadar(ev, sarFilas());
    box.innerHTML = `<b>${ev.fecha}</b>: ${Lib.fmt(ev.era5_72)} mm en 72 h según ERA5` + (ev.chirps_72 != null ? `, ${Lib.fmt(ev.chirps_72)} mm según CHIRPS` : '')
      + `. Con esa lluvia ${modelo}. ${radar(ev, m)}`;
    if (s1layer) { map.removeLayer(s1layer); s1layer = null; }
    const sc = m && (S.manifest.scenes || []).find(x => x.evento === m.evento && x.momento === 'post');
    if (sc && sc.w_layer && S.layers[sc.w_layer]) {
      const b = document.createElement('button'); b.textContent = 'Ver en el mapa lo que vio el radar';
      b.onclick = () => { if (s1layer) map.removeLayer(s1layer); s1layer = S.layers[sc.w_layer].layer.addTo(map); };
      box.appendChild(b);
    }
  }
  function leyenda() {
    const sw = (css, lab) => `<div class="cls"><span class="swatch" style="background:${css}"></span>${lab}</div>`;
    $('#legend').innerHTML = '<div class="item"><b>Agua</b>'
      + [[2, '2 cm'], [5, '5 cm · cubre el pie'], [20, '20 cm · media pierna'], [50, '50 cm · rodilla']].map(([v, l]) => sw(`rgb(${Sim.color(v).join(',')})`, l)).join('')
      + sw('rgba(33,113,181,.95)', 'probable') + sw('rgba(33,113,181,.55)', 'posible') + sw('rgba(33,113,181,.2)', 'poco probable') + '</div>';
  }
  function click(e) {
    const i = Sim.celda(e.latlng); if (i == null || !R.mezcla) return;
    const col = R.mezcla.h.map(f => f[i]); const cert = (R.u === 5 ? R.mezcla.c5 : R.mezcla.c20)[R.t][i];
    const hrs = col.filter(v => v > R.u).length; const nv = Lib.nivelCerteza(cert);
    L.popup().setLatLng(e.latlng).setContent(col[R.t] < 2 && Math.max(...col) < 2 ? 'Acá no se junta agua con esta lluvia.' :
      `Acá: <b>${col[R.t]} cm</b> a la hora ${R.t} · máximo ${Math.max(...col)} cm · con agua ${hrs} h${nv ? ` · certeza: ${nv === 'poco' ? 'poco probable' : nv}` : ''}`).openOn(map);
  }
  function grillaPixeles() {                           // a zoom ≥ 17: celdas de ~30 m en ±300 m del lote
    const g = Sim.idx.grid, [a, , c, , e, f] = g.transform, i0 = Sim.idx.lote_idx[0];
    if (i0 == null) return;
    const r0 = Math.floor(i0 / g.cols), c0 = i0 % g.cols, k = Math.ceil(300 / g.res_m);
    const un = (x, y) => L.CRS.EPSG3857.unproject(L.point(x, y)), lines = [];
    for (let j = c0 - k; j <= c0 + k + 1; j++) lines.push([un(c + j * a, f + (r0 - k) * e), un(c + j * a, f + (r0 + k + 1) * e)]);
    for (let i = r0 - k; i <= r0 + k + 1; i++) lines.push([un(c + (c0 - k) * a, f + i * e), un(c + (c0 + k + 1) * a, f + i * e)]);
    grilla = L.polyline(lines, { color: '#fff', weight: 0.6, opacity: 0.45, interactive: false });
    updGrilla = () => { if (map.getZoom() >= 17 && visible()) grilla.addTo(map); else map.removeLayer(grilla); };
    map.on('zoomend', updGrilla); updGrilla();
  }
  let timer = null;
  function play() { if (timer) { clearInterval(timer); timer = null; $('#r-play').textContent = '▶'; return; }
    if (!R.mezcla) return;
    $('#r-play').textContent = '❚❚'; timer = setInterval(() => { R.t = (R.t + 1) % R.mezcla.h.length; $('#r-t').value = R.t; pintarHora(); }, 250); }
  function riesgo() {
    const v = S.veredicto || {}, el = $('#r-riesgo');
    const nivel = (v.veredicto && v.veredicto.global) || (v.etiqueta ? v.etiqueta.replace(/^Riesgo\s+/i, '').toUpperCase() : '');
    el.textContent = v.etiqueta ? `${v.etiqueta}${v.frase_nivel ? ' · ' + v.frase_nivel : ''}` : '';
    el.dataset.nivel = nivel; el.hidden = !v.etiqueta;
  }
  async function init(m, s) {
    map = m; S = s; const idx = await Sim.load(S.base); if (!idx) return false;
    const durs = DUR.filter(([d]) => (idx.duraciones || []).includes(d)), suelos = SUELO.filter(([x]) => (idx.suelos || []).includes(x));
    if (durs.length && !durs.some(([d]) => d === R.dur)) R.dur = durs[0][0];
    if (suelos.length && !suelos.some(([x]) => x === R.suelo)) R.suelo = suelos[0][0];
    if (!Ps().length) { const d = durs.flatMap(([x]) => suelos.map(([y]) => [x, y])).find(([x, y]) => Ps(x, y).length); if (d) [R.dur, R.suelo] = d; }
    R.P = pInicial();
    riesgo();
    const redraw = () => {
      pills($('#r-dur'), durs, R.dur, x => { R.dur = x; redraw(); actualizar(false); }, x => !Ps(x, R.suelo).length);
      pills($('#r-suelo'), suelos, R.suelo, x => { R.suelo = x; redraw(); actualizar(); }, x => !Ps(R.dur, x).length);
      pills($('#r-umbral'), UMB, R.u, x => { R.u = x; redraw(); actualizar(); }); deslizador();
    };
    redraw();
    $('#r-mm').oninput = e => { R.P = Lib.ajustarP(Ps(), +e.target.value); e.target.value = R.P; $('#r-mm-v').textContent = `${R.P} mm`; clearTimeout(debounce); debounce = setTimeout(() => actualizar(), 120); };
    $('#r-t').oninput = e => { R.t = +e.target.value; pintarHora(); };
    $('#r-play').onclick = play; eventos(); grillaPixeles();
    await actualizar(false); return true;
  }
  function show() { $('#panel-resumen').hidden = false; $('#r-hora').hidden = false; if (overlay) overlay.addTo(map); map.on('click', click); leyenda(); updGrilla(); }
  function hide() { $('#panel-resumen').hidden = true; $('#r-hora').hidden = true; if (overlay) map.removeLayer(overlay); if (s1layer) { map.removeLayer(s1layer); s1layer = null; }
    if (grilla) map.removeLayer(grilla); if (map) map.off('click', click); if (timer) play(); }
  return { init, show, hide };
})();
