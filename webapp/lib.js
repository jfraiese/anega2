/* anega2 · funciones puras del visor (interpolación, estadísticas del lote, certeza, frase). Sin DOM: testeadas con node --test. */
(function (root) {
  const fmt = (v, d = 0) => Number(v).toLocaleString('es-AR', { maximumFractionDigits: d, minimumFractionDigits: 0 });

  function pickNeighbors(Ps, P) {
    const p = Math.min(Math.max(P, Ps[0]), Ps[Ps.length - 1]);
    for (let i = 0; i < Ps.length; i++) {
      if (Ps[i] === p) return { lo: p, hi: p, w: 0 };
      if (Ps[i] > p) { const lo = Ps[i - 1], hi = Ps[i]; return { lo, hi, w: Math.round(((p - lo) / (hi - lo)) * 1e6) / 1e6 }; }
    }
    return { lo: p, hi: p, w: 0 };
  }

  function lerp(a, b, w) {
    const out = new Uint8Array(a.length);
    for (let i = 0; i < a.length; i++) out[i] = Math.round(a[i] + (b[i] - a[i]) * w);
    return out;
  }

  function loteSerie(frames, loteIdx, u) {
    const hmax = [], pct = [];
    for (const f of frames) {
      let m = 0, n = 0;
      for (const i of loteIdx) { const v = f[i]; if (v > m) m = v; if (v > u) n++; }
      hmax.push(m); pct.push(loteIdx.length === 0 ? 0 : Math.round((1000 * n) / loteIdx.length) / 10);
    }
    const horasConAgua = hmax.filter(v => v > u).length;
    return { hmax, pct, horasConAgua, horaPico: hmax.indexOf(Math.max(...hmax)) };
  }

  // estadísticas del lote en la grilla nativa (30 m), desde data/proc/rog/<id>_meta.json vía index.json
  // ("lote": {hmax_cm, pct5, pct20}); evita el recorte de la reproyección a 3857 (ver ruling en el bug).
  function loteSerieNativa(loteA, loteB, w, u) {
    const key = u === 20 ? 'pct20' : 'pct5';
    const n = Math.min(loteA.hmax_cm.length, loteB ? loteB.hmax_cm.length : Infinity);   // una corrida cortada puede ser más corta
    const hmax = [], pct = [];
    for (let t = 0; t < n; t++) {
      const ha = loteA.hmax_cm[t], pa = loteA[key][t];
      if (w === 0 || !loteB) { hmax.push(ha); pct.push(pa); }
      else { hmax.push(ha + (loteB.hmax_cm[t] - ha) * w); pct.push(pa + (loteB[key][t] - pa) * w); }
    }
    const horasConAgua = hmax.filter(v => v > u).length;
    return { hmax, pct, horasConAgua, horaPico: hmax.length ? hmax.indexOf(Math.max(...hmax)) : 0 };
  }

  // valores de P calculados para una (duración, suelo), desde index.json escenarios (formato viejo o grilla propia)
  const pDisponibles = (esc, dur, suelo) => [...new Set(Object.values(esc || {}).filter(e => e.dur_h === dur && e.suelo === suelo).map(e => e.P_mm))].sort((a, b) => a - b);
  function grillaRegular(Ps) {                           // equiespaciada con ≥ 2 valores: el deslizador interpola cada 5 mm
    if (Ps.length < 2) return false;
    const d = Ps[1] - Ps[0]; return d > 0 && Ps.every((p, i) => i === 0 || Math.abs(p - Ps[i - 1] - d) < 1e-9);
  }
  function ajustarP(Ps, P) {                             // P que se muestra de verdad: acotado y en paso 5 (regular) o al calculado más cercano
    if (!Ps.length) return P;
    const lo = Ps[0], hi = Ps[Ps.length - 1];
    if (grillaRegular(Ps)) return Math.min(hi, Math.max(lo, lo + Math.round((P - lo) / 5) * 5));
    return Ps.reduce((m, p) => (Math.abs(p - P) < Math.abs(m - P) ? p : m), Ps[0]);
  }

  const nivelCerteza = c => (c >= 70 ? 'probable' : c >= 30 ? 'posible' : c >= 5 ? 'poco' : null);

  function retornoAnios(mm, g) {
    if (!g || !Number.isFinite(mm) || !Number.isFinite(g.mu) || !Number.isFinite(g.beta) || g.beta <= 0) return NaN;
    const pExc = 1 - Math.exp(-Math.exp(-(mm - g.mu) / g.beta));
    return pExc <= 0 ? Infinity : 1 / pExc;
  }

  const durTexto = dur => (dur <= 3 ? 'un chaparrón de 3 h' : dur <= 24 ? 'un día de lluvia' : 'un temporal de 3 días');
  const durUnidad = dur => (dur <= 3 ? 'chaparrón de 3 h' : dur <= 24 ? 'día' : 'temporal de 3 días');
  const T_MAX = 100;                                     // más allá de 100 años el ajuste de Gumbel con ~85 años de datos no dice nada
  const aniosTxt = T => (T > T_MAX ? `más de ${T_MAX}` : fmt(Math.round(T)));
  const NIVEL_TXT = { probable: 'probable', posible: 'posible', poco: 'poco probable' };

  function fraccion(pct) {
    if (pct >= 95) return 'todo el lote';
    if (pct >= 60) return 'la mayor parte del lote';
    if (pct >= 40) return 'la mitad del lote';
    if (pct >= 25) return 'un tercio del lote';
    if (pct >= 10) return 'una parte del lote';
    return 'una esquina del lote';
  }

  function frecuencia(o) {
    if (o.maxHistorico != null && o.P > o.maxHistorico) return `Más de lo que llovió en cualquier ${durUnidad(o.dur)} desde ${o.desde || 1940}.`;
    if (Number.isNaN(o.Tera5) || o.Tera5 == null) return '';
    if (o.Tera5 > T_MAX) return `Una lluvia así es más rara que una vez cada ${T_MAX} años.`;
    if (o.Tera5 < 1.5) return 'Una lluvia así pasa casi todos los años.';
    const tc = o.Tchirps;
    if (tc > 0 && (tc / o.Tera5 > 2 || o.Tera5 / tc > 2)) {   // NaN/null/0 no entran; Infinity sí (se muestra "más de 100")
      const [x, y] = [o.Tera5, tc].sort((m, n) => m - n);
      return `Una lluvia así pasa cada ${aniosTxt(x)} a ${aniosTxt(y)} años según la fuente.`;
    }
    return `Una lluvia así pasa cada ~${aniosTxt(o.Tera5)} años.`;
  }

  function frase(o) {
    const cab = `Con ${fmt(o.P)} mm en ${durTexto(o.dur)}: `;
    let cuerpo;
    if (o.hmaxCm < 5) cuerpo = 'el lote no junta agua (menos de 5 cm).';
    else {
      const cert = o.nivel ? ` (${NIVEL_TXT[o.nivel]}${o.certezaSoloVecindad ? ', certeza sólo por vecindad' : ''})` : '';
      cuerpo = `hasta ${fmt(o.hmaxCm)} cm en ${fraccion(o.pct)}${cert}, queda con agua ~${fmt(o.horasConAgua)} h.`;
    }
    const fr = frecuencia(o);
    return cab + cuerpo + (fr ? ' ' + fr : '');
  }

  // evento de lluvia → filas SAR del mismo evento: primero por id; si no, por fecha_evento (fecha configurada
  // del evento que buscó el radar) o, si falta, por fecha de tormenta (fecha de la escena − dias_desde_evento),
  // a ±3 días de ev.fecha. fecha_evento se prefiere porque está en todas las filas, incluidas SIN COBERTURA/SIN PASADA.
  const dia = f => Date.parse(String(f).slice(0, 10) + 'T00:00:00Z') / 864e5;
  function matchRadar(ev, rows) {
    const rs = (rows || []).filter(r => r && r.evento && r.evento !== 'referencia_seca');
    let evento = rs.some(r => r.evento === ev.id) ? ev.id : null;
    if (!evento && ev.fecha) {
      let mejor = Infinity;
      for (const r of rs) {
        let dd;
        if (r.fecha_evento) dd = Math.abs(dia(r.fecha_evento) - dia(ev.fecha));
        else if (r.fecha && typeof r.dias_desde_evento === 'number' && Number.isFinite(r.dias_desde_evento)) dd = Math.abs(dia(r.fecha) - r.dias_desde_evento - dia(ev.fecha));
        else continue;
        if (dd <= 3 && dd < mejor) { mejor = dd; evento = r.evento; }
      }
    }
    return evento ? { evento, filas: rs.filter(r => r.evento === evento) } : null;
  }

  const Lib = { fmt, pickNeighbors, pDisponibles, grillaRegular, ajustarP, lerp, loteSerie, loteSerieNativa, nivelCerteza, retornoAnios, durTexto, frase, matchRadar };
  if (typeof module !== 'undefined' && module.exports) module.exports = Lib; else root.Lib = Lib;
})(this);
