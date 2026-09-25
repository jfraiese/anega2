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
  assert.strictEqual(s, 'Con 120 mm en un día de lluvia: hasta 15 cm en un tercio del lote (probable), con agua ~6 h. Una lluvia así pasa cada ~10 años.');
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
test('frase con un solo modelo', () => {
  assert.match(Lib.frase({ P: 100, dur: 24, hmaxCm: 8, pct: 10, horasConAgua: 2, nivel: 'poco', soloUnModelo: true, Tera5: 5 }),
    /\(incierto: sólo 1 de 3 modelos de terreno\)/);
});
