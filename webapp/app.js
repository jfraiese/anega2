/* anega2 · arranque del visor: proyecto, mapa único y cambio de vista (Resumen / Detalle técnico). Datos en ../projects/<nombre>/web/. */
const S = { map: null, manifest: null, stats: null, grid: null, figures: [], layers: {}, opacity: 0.8, scene: null, scenario: null, charts: {}, project: null, base: '', projects: [], veredicto: null };
const PROJECTS_INDEX = '../projects/index.json';

async function loadProjects() {
  try { S.projects = await (await fetch(PROJECTS_INDEX)).json(); } catch (e) { S.projects = []; }
  const want = new URLSearchParams(location.search).get('project');
  S.project = (want && (S.projects.some(p => p.nombre === want) || !S.projects.length)) ? want : (S.projects[0]?.nombre || null);
  const sel = document.getElementById('project'); sel.innerHTML = '';
  const list = S.projects.length ? S.projects : (S.project ? [{ nombre: S.project, titulo: S.project }] : []);
  list.forEach(p => { const o = document.createElement('option'); o.value = p.nombre; o.textContent = p.titulo || p.nombre; if (p.nombre === S.project) o.selected = true; sel.appendChild(o); });
  sel.onchange = () => { location.search = '?project=' + encodeURIComponent(sel.value); };
  if (!S.project) throw new Error('no hay proyectos con datos del visor (corré: anega2 run <nombre> --fase web)');
  S.base = `../projects/${encodeURIComponent(S.project)}/web/`;
}

function initMap(center) {
  const base = {
    'Esri satelital': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19, attribution: 'Esri, Maxar, Earthstar Geographics' }),
    'Esri topo': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19, attribution: 'Esri, HERE, Garmin, © OpenStreetMap contributors' }),
    'OpenStreetMap': L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap contributors' }),
  };
  S.map = L.map('map', { layers: [base['Esri satelital']], zoomControl: true }).setView(center, 15);
  S.map.createPane('rasters'); S.map.getPane('rasters').style.zIndex = 350;
  L.control.layers(base, null, { position: 'topright', collapsed: true }).addTo(S.map);
  L.control.scale({ imperial: false }).addTo(S.map);
  // el click lo registra cada vista en su show()
}

let vistaActual = null;
function vista(v) {
  if (v === vistaActual) return;
  document.querySelectorAll('#vista button').forEach(b => b.classList.toggle('on', b.dataset.v === v));
  document.getElementById('panel-tecnico').hidden = v !== 'tecnico';
  if (v === 'tecnico') { Resumen.hide(); Tecnico.show(); } else { Tecnico.hide(); Resumen.show(); }
  vistaActual = v;
  S.map.invalidateSize();
}

async function init() {
  await loadProjects();
  const get = u => fetch(S.base + u).then(r => (r.ok ? r.json() : null)).catch(() => null);
  [S.manifest, S.stats, S.grid, S.figures, S.veredicto] = await Promise.all(['layers.json', 'stats.json', 'grid.json', 'figures.json', 'veredicto.json'].map(get));
  if (!S.manifest) throw new Error('layers.json: falta (corré anega2 run <proyecto> --fase web)');
  if (!S.stats) throw new Error('stats.json: falta (corré anega2 run <proyecto> --fase web)');
  S.figures = S.figures || [];
  initMap(S.manifest.center);
  await Tecnico.init(S.map, S);
  const hayResumen = await Resumen.init(S.map, S).catch(e => { console.error('vista Resumen:', e); return false; });
  document.querySelectorAll('#vista button').forEach(b => (b.onclick = () => { if (!b.disabled) vista(b.dataset.v); }));
  document.getElementById('r-tecnico').onclick = e => { e.preventDefault(); vista('tecnico'); };
  if (!hayResumen) { const b = document.querySelector('#vista [data-v="resumen"]'); b.disabled = true; b.title = `falta la simulación: corré anega2 run ${S.project} --fase lluvia web`; }
  vista(hayResumen ? 'resumen' : 'tecnico');
  if (S.layers.lote) S.map.fitBounds(S.layers.lote.layer.getBounds().pad(4));
}
init().catch(e => { console.error(e); document.getElementById('subtitle').textContent = 'Error cargando datos: ' + e.message; });
