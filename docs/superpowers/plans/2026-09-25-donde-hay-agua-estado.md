# «¿Dónde hay agua?» · estado de ejecución y cómo retomar

Fecha del corte: 2026-09-25 · Rama: `feat/donde-hay-agua` (base `93e2d64` en `main`) ·
Plan: `docs/superpowers/plans/2026-09-25-donde-hay-agua.md` · Spec: `docs/superpowers/specs/2026-09-25-donde-hay-agua-design.md`

La ejecución fue por subagentes (implementador + revisor por tarea). El registro detallado (commits por tarea,
rondas de corrección, observaciones menores diferidas) está en `.superpowers/sdd/2026-09-25-donde-hay-agua/progress.md`
(ignorado por git; local). Este documento es la copia versionada de lo necesario para retomar.

## Estado por tarea

| Tarea | Estado | Commits |
|---|---|---|
| 0 · pyproject + pytest | ✅ revisada | 93e2d64..b9fab4c |
| 1 · clima: cálculos | ✅ revisada | ..2b09fd3 |
| 2 · clima: fuentes ERA5/CHIRPS | ✅ revisada (1 corrección) | ..49b3888 |
| 3 · clima: fase + CLI | ✅ revisada (1 corrección) | ..dd197dd |
| 4 · sar automático + informe | ✅ revisada | ..a36a621 |
| 5 · grilla de 60 escenarios | ✅ revisada | ..b16816b |
| 6 · cuadros horarios + paralelo | ✅ revisada (1 corrección) | ..a821dbe |
| 7 · ensamble de DEM | ✅ revisada (1 corrección) | ..ca29c4b |
| 8 · websim (3857 + certeza) | ✅ revisada (1 corrección) | ..4d00eb3 |
| 9 · veredicto.json | ✅ revisada (1 corrección) | ..3cfed0b |
| 10 · paleta HAND + error | ✅ revisada (1 corrección) | ..bd5f5d3 |
| 11 · ficha (paleta, banda, escenarios) | ✅ hecho (cambios del autor commiteados a pedido, más el crash de `sar.eventos: auto` y el filtro a `lluvia.ficha`) | 222fea0..ded7771 |
| 12 · lib.js + tests node | ✅ revisada (1 corrección) | ..5631022 |
| 13 · visor Resumen | ✅ revisada · **verificado en Chrome** (paso 7, lista completa del plan) | ..b828007 |
| 14 · corrida completa, README, SOURCES | ✅ hecho | docs + ejemplo regenerado (este commit) |
| Revisión final de la rama | ⏳ pendiente | — |

Tests: `conda run -n giles-flood python -m pytest -q` (65 pasan) y `node --test webapp/test/*.test.js` (21 pasan).
Ojo: node 26 no acepta una carpeta en `node --test webapp/test/`; usar el glob.

## Simulación del ejemplo (fase lluvia) — completada

**Actualización (task 14): la corrida se retomó y se completó** (68 corridas: 60 de la grilla + 8 del
ensamble). Balance de agua |error| ≤ 0,52 % en todos los escenarios; `P100_24h` da 9,1 cm en el lote (8 % del
lote con más de 5 cm); veredicto global MEDIO. `out/` y `web/` quedaron regenerados con el código final
(incluye `out/clima*`, `out/rog_ensamble.json`, `out/veredicto.json` y `web/sim/`, ~30 MB en este ejemplo).
El resto de esta sección es el registro histórico del corte original, para referencia.

Se lanzó `anega2 run ejemplo-bajo-giles --fase lluvia --si` (68 corridas: 60 de la grilla + 8 del ensamble,
16 en paralelo) y se cortó a las ~14:02 para seguir después. **Cada escenario terminado queda guardado**
(`data/proc/rog/<id>_{hmax_dom.tif,dur5cm_dom.tif,frames.npz,meta.json}`; el meta se escribe último, así que un
escenario a medio escribir no cuenta como hecho). Los que estaban en curso se recalculan desde cero.

**Al corte (14:02): 45 de 60 escenarios de la grilla terminados; 0 de 8 del ensamble.** Faltan:
`P150_72h_sat P175_72h_sat P200_24h_sat P200_72h P200_72h_sat P225_24h P225_24h_sat P225_72h P225_72h_sat
P250_3h P250_3h_sat P250_24h P250_24h_sat P250_72h P250_72h_sat` + ensamble (`P050/P100/P150/P200_24h` × glo30, ign30).
Estimación para terminar: ~1-1,5 h con 16 procesos.

Tiempos medidos: 200 mm/72 h solo = 34 min; en paralelo, 3 h ≈ 2-25 min, 24 h ≈ 3-36 min, 72 h ≈ 7-46 min.

**Vista previa parcial:** con esos 45 se corrió `--fase web` y la vista Resumen funciona en Chrome con datos
reales (100 mm/24 h: el lote no junta agua; 150 mm/24 h: hasta 35 cm en la mitad del lote, ~6 h). Los archivos de
`projects/ejemplo-bajo-giles/web/` que cambió esa corrida parcial (grid.json, layers.json, stats.json, img/,
veredicto.json) **no se commitearon a propósito**: se regeneran al terminar (paso 2 de abajo). `web/sim/` queda
ignorado por git.

Para retomar (sólo calcula lo que falta; al final regenera `out/rog_stats.csv`, PNG de la ficha y `out/rog_ensamble.json`):

```bash
conda run --no-capture-output -n giles-flood anega2 run ejemplo-bajo-giles --fase lluvia --si
```

Para ver cuántos hay listos: `ls projects/ejemplo-bajo-giles/data/proc/rog/*_frames.npz | wc -l` (grilla, meta 60)
y `ls projects/ejemplo-bajo-giles/data/proc/rog/ens/*_frames.npz | wc -l` (ensamble, meta 8).

## Pasos que faltan, en orden

1. ✅ Fase lluvia terminada (68 corridas). `out/rog_stats.csv` tiene 60 filas; `P100_24h` `hmax_lote_m` = 0,091
   (9,1 cm); `|balance.error_pct| < 1` en todos los `*_meta.json` (máximo observado 0,52 %); sin `cortado: true`.
2. ✅ `anega2 run ejemplo-bajo-giles --fase sar informe kml web --si` corrido (sar con la nueva regla de pasada
   0-3 días; el ejemplo mantiene su lista manual de eventos).
3. ✅ Tarea 13, paso 7: verificado en Chrome contra `http://localhost:8000/webapp/?project=ejemplo-bajo-giles`,
   la lista completa del plan (mapa Resumen sólo con lote y agua, barra de hora, línea de hora en el gráfico,
   dimensionado de gráficos técnicos, sincronización de checkboxes Resumen ↔ Técnico, chip de riesgo, ▶ sin
   errores de consola, tarjeta 2 con eventos enlazados a su escena de radar).
4. ✅ Tarea 11 (ficha): cambios del autor en `anega2/ficha.py` commiteados (`222fea0`, `ded7771`), PDF del
   ejemplo regenerado.
5. ✅ Tarea 14: `SOURCES.md` (ERA5 vía Open-Meteo, CC BY 4.0; CHIRPS v2.0, dominio público, Funk et al. 2015),
   README.md/README.en.md (fase `clima`, grilla de 60 escenarios + ensamble, certeza, tiempos, vista Resumen,
   instalación/tests, limitaciones), captura nueva `docs/visor.jpg`, commit del ejemplo regenerado (incluye
   `out/clima*`, `out/rog_ensamble.json`, `out/veredicto.json`, `web/veredicto.json` y `web/sim/`).
6. ⏳ Pendiente: revisión final de toda la rama (modelo más capaz) con las observaciones diferidas del
   registro, y cierre (merge/PR a decidir por el autor).

## Correcciones posteriores al checkpoint (entre el corte y la tarea 14)

Encontradas y corregidas durante la corrida completa y su verificación, antes del commit final:

- **Piso de infiltración del balance** (`802ce9c`, posterior a R8): con `steep_slopes=True`, `OverlandFlow`
  resetea al final de cada paso toda lámina por debajo de `h_init` (1e-5 m) a `h_init·1e-3` (1e-8 m), pero
  Green-Ampt sólo infiltraba hasta `H_FILM` (1e-5 m); la lluvia liviana y prolongada nunca llegaba a
  infiltrarse antes de ese piso y Landlab la borraba sin contarla — hasta 48 % de error de balance en el
  dominio real (peor cuanto más liviana y larga la lluvia), encima del bug de R8 (salida por bordes no
  medida). Se agregó `H_PISO = H_FILM·1e-3` e infiltra hasta ahí. Con ambos fixes, el error de balance quedó
  en ≤ 0,52 % en las 68 corridas del ejemplo; las láminas (`hmax`, `dur5cm`) ya eran correctas antes, sólo
  `escurrido_pct`/`almacenado_final_pct` no eran confiables.
- **Plausibilidad del umbral de Otsu en SAR** (`7eab5be`): Otsu podía aceptar un umbral ≤ −13 dB que igual
  marcaba una fracción grande del buffer hidrológico como agua (caso real: 2016-12-16, Otsu = −13,1 dB, 55 % del
  buffer — suelo húmedo/cultivos, no agua abierta). Se agregó un chequeo (`FRAC_AGUA_MAX = 0.20`): si el umbral
  de Otsu marca más del 20 % del buffer, se cae al umbral fijo (−18 dB).
- **Serie nativa del lote en el visor** (`675ce79`): la vista Resumen recalculaba el máximo/porcentaje del lote
  a partir de los cuadros ya reproyectados a EPSG:3857 (vecino más cercano), lo que podía perder la celda de
  borde con el pico nativo (bug real: P100_24h daba 3 cm en el visor vs. 9 cm en el informe). `websim.py` ahora
  copia `hmax_lote_cm`/`pct_lote_gt5cm`/`pct_lote_gt20cm` del meta nativo de `rog` a `index.json`, y el visor los
  usa para la frase, la curva y la hora pico (con fallback a la serie recalculada para `index.json` viejos).
- **Radar emparejado por `fecha_evento`** (`81ac5bd`): `sar.run` ahora escribe `fecha_evento` en toda fila de
  evento (con o sin escena: pre, post, sin pasada a tiempo, sin cobertura), y `Lib.matchRadar` la usa de
  respaldo cuando el id no matchea. `resumen.js` distingue "no hubo pasadas cerca de esa fecha" (sin cobertura)
  de "no pasó a tiempo" (sin pasada), y sólo dice "no se analizó con radar" cuando no hay ninguna fila.
- **Frase de certeza sin sustento** (mismo commit `81ac5bd`): se quitó `soloUnModelo` de `Lib.frase`/`resumen.js`
  — el visor no tiene cómo saber cuántos de los 3 DEM ven agua en un píxel (la certeza combinada es vecindad ×
  promedio de DEMs), así que esa frase de incertidumbre no estaba sustentada por los datos disponibles.

## Decisiones tomadas durante la ejecución (a revisar por el autor)

- **R1-R3** · No se tocaron los cambios sin commitear del autor; la tarea 11 y el README quedan para cuando estén commiteados.
- **R4** · Las corridas largas/red (clima real, lluvia completa) las corre el controlador, no los implementadores.
- **R5** · El plan asumía que no había `pyproject.toml`; existía. Se restauró el original y sólo se agregó la config de pytest.
- **R6** · ERA5: ante falla de red ya no se pierde el último día de la caché. CHIRPS: prueba el primer día faltante y, si no responde, sigue sin CHIRPS con aviso (en vez de horas de timeouts).
- **R7** · Corridas cortadas por tiempo: se completan repitiendo el último cuadro y quedan marcadas `cortado: true`; `presupuesto_min` pasó de 60 a 180.
- **R8** · Balance de agua: la salida por los bordes se mide por flujo en los bordes (antes el control no podía fallar). **Además se corrigió un error previo**: el balance original tenía 17-51 % de error porque no medía la salida por los bordes; los `escurrido_pct`/`almacenado_final_pct` informados antes no eran confiables (las láminas sí).
- **R9** · Las corridas del ensamble conservan sus .tif (los usa la caché; ~0,4 MB c/u).
- **R10** · Si falla la generación de la vista Resumen, la fase web sigue y avisa.
- **R11** · Los cortes de la paleta HAND se leen de `rules.yml`.
- **R12** · La frase dice «queda con agua ~N h» (horas con agua en el lote), no «se va en».
- **R13** · Tarea 13 dividida: código ahora, verificación en Chrome con datos reales después.
- **R14** · Tarjeta «¿Pasó alguna vez?»: une tormentas históricas y recientes y enlaza con el radar por id o por fecha (±3 días), porque los ids del ejemplo (manuales) no coinciden con los de clima.

## Resultados reales ya obtenidos (fase clima, ejemplo)

ERA5 1940-2026 (87 años) y CHIRPS 1981-2026 (103 días sin dato, se reintentan). 24 h: T10 = 98 mm (ERA5) / 101 mm
(CHIRPS); T100 = 132 / 146 mm. Mayor tormenta desde 2014: 2019-10-12 (154 mm en 72 h, ERA5). Archivos en
`projects/ejemplo-bajo-giles/out/clima*`.
