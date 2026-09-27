const test = require('node:test');
const assert = require('node:assert');
const Lib = require('../lib.js');

test('pickNeighbors interior y exacto', () => {
  assert.deepStrictEqual(Lib.pickNeighbors([25, 50, 75], 60), { lo: 50, hi: 75, w: 0.4 });
  assert.deepStrictEqual(Lib.pickNeighbors([25, 50, 75], 50), { lo: 50, hi: 50, w: 0 });
});
test('pickNeighbors extremos', () => {
  assert.deepStrictEqual(Lib.pickNeighbors([25, 50], 10), { lo: 25, hi: 25, w: 0 });
  assert.deepStrictEqual(Lib.pickNeighbors([25, 50], 300), { lo: 50, hi: 50, w: 0 });
});
test('lerp redondea', () => {
  assert.deepStrictEqual(Array.from(Lib.lerp(new Uint8Array([0, 10]), new Uint8Array([10, 20]), 0.25)), [3, 13]);
});
test('loteSerie', () => {
  const f = [new Uint8Array([0, 0, 0]), new Uint8Array([8, 2, 99]), new Uint8Array([30, 6, 0])];
  const s = Lib.loteSerie(f, [0, 1], 5);
  assert.deepStrictEqual(s.hmax, [0, 8, 30]);
  assert.deepStrictEqual(s.pct, [0, 50, 100]);
  assert.strictEqual(s.horasConAgua, 2); assert.strictEqual(s.horaPico, 2);
});
test('loteSerie lote vacío', () => {
  const f = [new Uint8Array([0, 0, 0]), new Uint8Array([8, 2, 99]), new Uint8Array([30, 6, 0])];
  const s = Lib.loteSerie(f, [], 5);
  assert.deepStrictEqual(s.hmax, [0, 0, 0]);
  assert.deepStrictEqual(s.pct, [0, 0, 0]);
  assert.strictEqual(s.horasConAgua, 0);
});
test('loteSerieNativa lerpea entre escenarios (w=0.5)', () => {
  const a = { hmax_cm: [0, 10, 4], pct5: [0, 40, 20], pct20: [0, 5, 0] };
  const b = { hmax_cm: [0, 20, 8], pct5: [0, 60, 40], pct20: [0, 15, 10] };
  const s = Lib.loteSerieNativa(a, b, 0.5, 5);
  assert.deepStrictEqual(s.hmax, [0, 15, 6]);
  assert.deepStrictEqual(s.pct, [0, 50, 30]);
  assert.strictEqual(s.horasConAgua, 2); assert.strictEqual(s.horaPico, 1);
});
test('loteSerieNativa w=0 usa sólo A (aunque haya B)', () => {
  const a = { hmax_cm: [0, 9], pct5: [0, 100], pct20: [0, 0] };
  const b = { hmax_cm: [0, 90], pct5: [0, 100], pct20: [0, 100] };
  const s = Lib.loteSerieNativa(a, b, 0, 5);
  assert.deepStrictEqual(s.hmax, [0, 9]);
  assert.deepStrictEqual(s.pct, [0, 100]);
});
test('loteSerieNativa sin B (missing) usa A', () => {
  const a = { hmax_cm: [0, 9, 3], pct5: [0, 100, 10], pct20: [0, 0, 0] };
  const s = Lib.loteSerieNativa(a, null, 0, 5);
  assert.deepStrictEqual(s.hmax, [0, 9, 3]);
  assert.strictEqual(s.horaPico, 1);
});
test('loteSerieNativa umbral 20 usa pct20', () => {
  const a = { hmax_cm: [0, 25], pct5: [0, 80], pct20: [0, 30] };
  const s = Lib.loteSerieNativa(a, null, 0, 20);
  assert.deepStrictEqual(s.pct, [0, 30]);
  assert.strictEqual(s.horasConAgua, 1);
});
test('nivelCerteza', () => {
  assert.deepStrictEqual([80, 70, 50, 10, 4].map(Lib.nivelCerteza), ['probable', 'probable', 'posible', 'poco', null]);
});
test('retornoAnios', () => {
  const g = { mu: 80, beta: 20 };
  assert.ok(Math.abs(Lib.retornoAnios(80 - 20 * Math.log(-Math.log(0.9)), g) - 10) < 1e-6);
  assert.strictEqual(Lib.retornoAnios(1e5, g), Infinity);
});
test('frase con agua', () => {
  const s = Lib.frase({ P: 120, dur: 24, hmaxCm: 15, pct: 33, horasConAgua: 6, nivel: 'probable', Tera5: 10.4, Tchirps: 12 });
  assert.strictEqual(s, 'Con 120 mm en un día de lluvia: hasta 15 cm en un tercio del lote (probable), queda con agua ~6 h. Una lluvia así pasa cada ~10 años.');
});
test('frase sin agua', () => {
  const s = Lib.frase({ P: 25, dur: 3, hmaxCm: 3, pct: 0, horasConAgua: 0, nivel: null, Tera5: 1.2 });
  assert.strictEqual(s, 'Con 25 mm en un chaparrón de 3 h: el lote no junta agua (menos de 5 cm). Una lluvia así pasa casi todos los años.');
});
test('frase fuera de registro y fuentes que difieren', () => {
  assert.match(Lib.frase({ P: 250, dur: 24, hmaxCm: 40, pct: 90, horasConAgua: 20, nivel: 'posible', Tera5: Infinity, maxHistorico: 180, desde: 1940 }),
    /Más de lo que llovió en cualquier día desde 1940\.$/);
  assert.match(Lib.frase({ P: 150, dur: 24, hmaxCm: 20, pct: 50, horasConAgua: 8, nivel: 'probable', Tera5: 10, Tchirps: 30 }),
    /pasa cada 10 a 30 años según la fuente\.$/);
});
test('frase con nivel poco', () => {
  assert.match(Lib.frase({ P: 100, dur: 24, hmaxCm: 8, pct: 10, horasConAgua: 2, nivel: 'poco', Tera5: 5 }),
    /\(poco probable\)/);
});

const SAR = [
  { evento: 'referencia_seca', escena: 'S1A_ref', fecha: '2015-01-05', momento: null, dias_desde_evento: null },
  { evento: '2015-08_agosto2015', escena: 'S1A_pre', fecha: '2015-08-06', momento: 'pre', dias_desde_evento: -4 },
  { evento: '2015-08_agosto2015', escena: 'S1A_post', fecha: '2015-08-18', momento: 'post', dias_desde_evento: 8, pct_agua_lote: 3 },
  { evento: '2016-04_abril2016', escena: 'SIN PASADA A TIEMPO', fecha: null, momento: 'post' },
  { evento: '2017-02_febrero2017', escena: 'SIN COBERTURA', fecha: null, fecha_evento: '2017-02-10' },
];
test('matchRadar por id', () => {
  const m = Lib.matchRadar({ id: '2016-04_abril2016', fecha: '2016-04-02' }, SAR);
  assert.strictEqual(m.evento, '2016-04_abril2016'); assert.strictEqual(m.filas.length, 1);
});
test('matchRadar por fecha de tormenta (escena − días)', () => {
  const m = Lib.matchRadar({ id: '2015-08-10_era5', fecha: '2015-08-10' }, SAR);
  assert.strictEqual(m.evento, '2015-08_agosto2015'); assert.strictEqual(m.filas.length, 2);
  assert.strictEqual(Lib.matchRadar({ id: 'x', fecha: '2015-08-13' }, SAR).evento, '2015-08_agosto2015');
});
test('matchRadar no empareja a más de 3 días', () => {
  assert.strictEqual(Lib.matchRadar({ id: '2015-08-14_era5', fecha: '2015-08-14' }, SAR), null);
  assert.strictEqual(Lib.matchRadar({ id: '2015-01-05_era5', fecha: '2015-01-05' }, SAR), null);
});
test('matchRadar: fila SIN PASADA sin fecha sólo por id', () => {
  assert.strictEqual(Lib.matchRadar({ id: '2016-04-01_era5', fecha: '2016-04-01' }, SAR), null);
  assert.strictEqual(Lib.matchRadar({ id: 'y' }, []), null);
});
test('matchRadar por fecha_evento: fila SIN COBERTURA sin fecha de escena', () => {
  const m = Lib.matchRadar({ id: 'x', fecha: '2017-02-12' }, SAR);
  assert.strictEqual(m.evento, '2017-02_febrero2017');
  assert.strictEqual(m.filas.length, 1);
  assert.strictEqual(m.filas[0].escena, 'SIN COBERTURA');
});
test('matchRadar por fecha_evento: límite de ±3 días', () => {
  assert.strictEqual(Lib.matchRadar({ id: 'y', fecha: '2017-02-13' }, SAR).evento, '2017-02_febrero2017');
  assert.strictEqual(Lib.matchRadar({ id: 'z', fecha: '2017-02-14' }, SAR), null);
});

// --- C1: frecuencias acotadas y sensibles a la duración
test('retornoAnios con beta <= 0 o no finita → NaN', () => {
  assert.ok(Number.isNaN(Lib.retornoAnios(100, { mu: 50, beta: 0 })));
  assert.ok(Number.isNaN(Lib.retornoAnios(100, { mu: 50, beta: -3 })));
  assert.ok(Number.isNaN(Lib.retornoAnios(100, { mu: 50, beta: NaN })));
  assert.ok(Number.isNaN(Lib.retornoAnios(100, { mu: NaN, beta: 10 })));
});
test('frase: sin frecuencia si T es NaN', () => {
  assert.strictEqual(Lib.frase({ P: 100, dur: 24, hmaxCm: 3, pct: 0, horasConAgua: 0, Tera5: NaN }), 'Con 100 mm en un día de lluvia: el lote no junta agua (menos de 5 cm).');
});
test('frase: por encima del máximo histórico, según la duración', () => {
  const b = { hmaxCm: 3, pct: 0, horasConAgua: 0, Tera5: 518548, desde: '1940' };
  assert.match(Lib.frase({ ...b, P: 100, dur: 3, maxHistorico: 55 }), /Más de lo que llovió en cualquier chaparrón de 3 h desde 1940\.$/);
  assert.match(Lib.frase({ ...b, P: 200, dur: 24, maxHistorico: 126 }), /Más de lo que llovió en cualquier día desde 1940\.$/);
  assert.match(Lib.frase({ ...b, P: 300, dur: 72, maxHistorico: 180, desde: '1941' }), /Más de lo que llovió en cualquier temporal de 3 días desde 1941\.$/);
});
test('frase: T > 100 dentro del registro → tope de 100 años', () => {
  const s = Lib.frase({ P: 120, dur: 24, hmaxCm: 3, pct: 0, horasConAgua: 0, Tera5: 1677, Tchirps: 9359, maxHistorico: 126, desde: '1940' });
  assert.match(s, /Una lluvia así es más rara que una vez cada 100 años\.$/);
  assert.doesNotMatch(s, /1677|9359/);
});
test('frase: rango ERA5-CHIRPS con valores acotados', () => {
  assert.match(Lib.frase({ P: 110, dur: 24, hmaxCm: 3, pct: 0, horasConAgua: 0, Tera5: 20, Tchirps: 500 }), /pasa cada 20 a más de 100 años según la fuente\.$/);
  assert.match(Lib.frase({ P: 110, dur: 24, hmaxCm: 3, pct: 0, horasConAgua: 0, Tera5: 60, Tchirps: 20 }), /pasa cada 20 a 60 años según la fuente\.$/);
});
test('frase: T con separador de miles vía fmt (P grande)', () => {
  assert.match(Lib.frase({ P: 1200, dur: 72, hmaxCm: 3, pct: 0, horasConAgua: 0, Tera5: 5 }), /^Con 1\.200 mm/);
});

// --- I2: serie nativa con largos distintos
test('loteSerieNativa acota al más corto y no devuelve horaPico −1', () => {
  const a = { hmax_cm: [0, 10, 4, 7], pct5: [0, 40, 20, 30], pct20: [0, 0, 0, 0] };
  const b = { hmax_cm: [0, 20], pct5: [0, 60], pct20: [0, 0] };
  const s = Lib.loteSerieNativa(a, b, 0.5, 5);
  assert.deepStrictEqual(s.hmax, [0, 15]); assert.deepStrictEqual(s.pct, [0, 50]);
  assert.ok(s.hmax.every(Number.isFinite));
  const v = Lib.loteSerieNativa({ hmax_cm: [], pct5: [], pct20: [] }, null, 0, 5);
  assert.strictEqual(v.horaPico, 0); assert.strictEqual(v.horasConAgua, 0);
});

// --- I7: valores de P por combinación (formato viejo / grillas propias)
const ESC = {
  P060_2h: { P_mm: 60, dur_h: 2, suelo: 'normal' }, P100_24h: { P_mm: 100, dur_h: 24, suelo: 'normal' },
  P150_24h: { P_mm: 150, dur_h: 24, suelo: 'normal' }, P200_24h: { P_mm: 200, dur_h: 24, suelo: 'normal' },
  P150_24h_sat: { P_mm: 150, dur_h: 24, suelo: 'saturado' }, P080_24h: { P_mm: 80, dur_h: 24, suelo: 'saturado' },
};
test('pDisponibles filtra por duración y suelo, ordenado y sin repetir', () => {
  assert.deepStrictEqual(Lib.pDisponibles(ESC, 24, 'normal'), [100, 150, 200]);
  assert.deepStrictEqual(Lib.pDisponibles(ESC, 24, 'saturado'), [80, 150]);
  assert.deepStrictEqual(Lib.pDisponibles(ESC, 72, 'normal'), []);
  assert.deepStrictEqual(Lib.pDisponibles({}, 24, 'normal'), []);
});
test('grillaRegular', () => {
  assert.strictEqual(Lib.grillaRegular([25, 50, 75, 100]), true);
  assert.strictEqual(Lib.grillaRegular([80, 150]), true);
  assert.strictEqual(Lib.grillaRegular([60, 100, 150, 200]), false);
  assert.strictEqual(Lib.grillaRegular([100]), false);
  assert.strictEqual(Lib.grillaRegular([]), false);
});
test('ajustarP: grilla regular → paso 5 dentro del rango', () => {
  assert.strictEqual(Lib.ajustarP([25, 50, 75], 62), 60);
  assert.strictEqual(Lib.ajustarP([25, 50, 75], 10), 25);
  assert.strictEqual(Lib.ajustarP([25, 50, 75], 300), 75);
});
test('ajustarP: grilla irregular → al valor calculado más cercano', () => {
  assert.strictEqual(Lib.ajustarP([60, 100, 150, 200], 115), 100);
  assert.strictEqual(Lib.ajustarP([60, 100, 150, 200], 130), 150);
  assert.strictEqual(Lib.ajustarP([60, 100, 150, 200], 20), 60);
  assert.strictEqual(Lib.ajustarP([100], 250), 100);
});
