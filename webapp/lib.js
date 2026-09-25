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

  const nivelCerteza = c => (c >= 70 ? 'probable' : c >= 30 ? 'posible' : c >= 5 ? 'poco' : null);

  function retornoAnios(mm, g) {
    const pExc = 1 - Math.exp(-Math.exp(-(mm - g.mu) / g.beta));
    return pExc <= 0 ? Infinity : 1 / pExc;
  }

  const durTexto = dur => (dur <= 3 ? 'un chaparrón de 3 h' : dur <= 24 ? 'un día de lluvia' : 'un temporal de 3 días');
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
    const unDia = o.dur <= 24 ? 'día' : 'temporal';
    if (!Number.isFinite(o.Tera5)) return o.maxHistorico != null ? `Más de lo que llovió en cualquier ${unDia} desde ${o.desde || 1940}.` : '';
    if (o.Tera5 < 1.5) return 'Una lluvia así pasa casi todos los años.';
    const a = Math.round(o.Tera5);
    if (o.Tchirps && Number.isFinite(o.Tchirps) && (o.Tchirps / o.Tera5 > 2 || o.Tera5 / o.Tchirps > 2)) {
      const [x, y] = [a, Math.round(o.Tchirps)].sort((m, n) => m - n);
      return `Una lluvia así pasa cada ${x} a ${y} años según la fuente.`;
    }
    return `Una lluvia así pasa cada ~${a} años.`;
  }

  function frase(o) {
    const cab = `Con ${fmt(o.P)} mm en ${durTexto(o.dur)}: `;
    let cuerpo;
    if (o.hmaxCm < 5) cuerpo = 'el lote no junta agua (menos de 5 cm).';
    else {
      const cert = o.soloUnModelo ? ' (incierto: sólo 1 de 3 modelos de terreno)' : o.nivel ? ` (${NIVEL_TXT[o.nivel]}${o.certezaSoloVecindad ? ', certeza sólo por vecindad' : ''})` : '';
      cuerpo = `hasta ${fmt(o.hmaxCm)} cm en ${fraccion(o.pct)}${cert}, queda con agua ~${fmt(o.horasConAgua)} h.`;
    }
    const fr = frecuencia(o);
    return cab + cuerpo + (fr ? ' ' + fr : '');
  }

  const Lib = { fmt, pickNeighbors, lerp, loteSerie, nivelCerteza, retornoAnios, durTexto, frase };
  if (typeof module !== 'undefined' && module.exports) module.exports = Lib; else root.Lib = Lib;
})(this);
