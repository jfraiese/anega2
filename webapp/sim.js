/* anega2 · datos de simulación de la vista Resumen: descarga, descompresión, caché, interpolación y pintado. */
const Sim = (() => {
  let base = '', idx = null; const cache = new Map(), CACHE_MAX = 6;   // ~6 escenarios en memoria
  async function gunzip(url) {
    const r = await fetch(base + url); if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    const raw = new Uint8Array(await r.arrayBuffer());
    // si el servidor ya lo mandó con Content-Encoding: gzip, el navegador lo descomprimió: no hay cabecera 1f 8b
    if (raw[0] !== 0x1f || raw[1] !== 0x8b) return raw;
    return new Uint8Array(await new Response(new Blob([raw]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
  }
  async function load(b) {
    base = b;
    try { const r = await fetch(base + 'sim/index.json'); if (!r.ok) return null; idx = await r.json(); } catch (e) { console.warn('sim/index.json:', e); return null; }
    return idx && Object.keys(idx.escenarios || {}).length ? idx : null;
  }
  const n = () => idx.grid.rows * idx.grid.cols;
  function partir(buf, k) { const out = []; for (let i = 0; i < k; i++) out.push(buf.subarray(i * n(), (i + 1) * n())); return out; }
  async function frames(id) {
    if (!idx.escenarios[id]) throw new Error(`escenario ${id}: no está en sim/index.json`);
    if (cache.has(id)) { const p = cache.get(id); cache.delete(id); cache.set(id, p); return p; }   // LRU: al final = más reciente
    const p = (async () => {
      const e = idx.escenarios[id]; const [h, c] = await Promise.all([gunzip(e.url), gunzip(e.cert_url)]);
      const cc = partir(c, 2 * e.horas);
      return { h: partir(h, e.horas), c5: cc.slice(0, e.horas), c20: cc.slice(e.horas) };
    })();
    cache.set(id, p); p.catch(() => { if (cache.get(id) === p) cache.delete(id); });   // no cachear un fallo de red
    while (cache.size > CACHE_MAX) cache.delete(cache.keys().next().value);             // desalojar el más viejo
    return p;
  }
  const idDe = (P, dur, suelo) => `P${String(P).padStart(3, '0')}_${dur}h${suelo === 'saturado' ? '_sat' : ''}`;
  async function mezcla(P, dur, suelo, Ps) {           // Ps: valores de P calculados para (dur, suelo); si falta, los de todo el índice
    const lista = Ps || idx.P_mm; if (!lista.length) throw new Error(`sin escenarios de ${dur} h con suelo ${suelo}`);
    const { lo, hi, w } = Lib.pickNeighbors(lista, P);
    const [a, b] = await Promise.all([frames(idDe(lo, dur, suelo)), frames(idDe(hi, dur, suelo))]);
    // una simulación cortada puede tener menos horas que su vecina: se mezcla hasta la más corta
    const H = w === 0 ? a.h.length : Math.min(a.h.length, b.h.length);
    const mix = k => a[k].slice(0, H).map((f, t) => (w === 0 ? f : Lib.lerp(f, b[k][t], w)));
    const eLo = idx.escenarios[idDe(lo, dur, suelo)], eHi = idx.escenarios[idDe(hi, dur, suelo)];
    return { h: mix('h'), c5: mix('c5'), c20: mix('c20'), lo, hi, w, ensamble: eLo.ensamble, cortado: !!(eLo.cortado || (w > 0 && eHi.cortado)),
             loteLo: eLo.lote, loteHi: eHi.lote };
  }
  // azules por profundidad; alpha por nivel de certeza; < 2 cm transparente
  const STOPS = [[2, [134, 182, 239]], [5, [57, 135, 229]], [20, [28, 92, 171]], [50, [13, 54, 107]]];
  function color(cm) { let c = STOPS[0][1]; for (const [v, col] of STOPS) if (cm >= v) c = col; return c; }
  const ALPHA = { probable: 242, posible: 140, poco: 51 };
  function pintar(canvas, h, cert) {
    const { cols, rows } = idx.grid; canvas.width = cols; canvas.height = rows;
    const ctx = canvas.getContext('2d'); const img = ctx.createImageData(cols, rows); const d = img.data;
    for (let i = 0; i < h.length; i++) {
      const v = h[i]; if (v < 2) continue; const nv = Lib.nivelCerteza(cert[i]); if (!nv) continue;
      const [r, g, b] = color(v); d[4 * i] = r; d[4 * i + 1] = g; d[4 * i + 2] = b; d[4 * i + 3] = ALPHA[nv];
    }
    ctx.putImageData(img, 0, 0);
  }
  function celda(latlng) {
    const p = L.CRS.EPSG3857.project(latlng); const [a, , c, , e, f] = idx.grid.transform;
    const col = Math.floor((p.x - c) / a), row = Math.floor((p.y - f) / e);
    return row < 0 || col < 0 || row >= idx.grid.rows || col >= idx.grid.cols ? null : row * idx.grid.cols + col;
  }
  return { load, frames, mezcla, pintar, celda, idDe, color, get idx() { return idx; } };
})();
