# anega2 · «¿Dónde hay agua?»: lluvia histórica, simulación hora a hora, certeza y visor en lenguaje llano — diseño

Fecha: 2026-09-25 · Estado: diseño aprobado en chat por secciones, pendiente revisión de este documento · Alcance: uso local.

## Objetivo

Que un **cliente sin formación técnica** abra el visor y responda en menos de un minuto, sin tocar capas:
dónde se junta el agua con X mm de lluvia, cuánto tarda en irse, **qué tan seguro es** eso a 30 m de píxel,
cuántas veces llovió así en la historia del lugar y si el satélite lo vio. La capa técnica actual se conserva
en una vista aparte para el autor y para arquitectos/ingenieros.

Motivación (review del 2026-09-25): el visor abre en HAND con paleta azul = alto/seguro superpuesto a la lámina
azul = agua; seis pestañas para llegar a un escenario; la simulación guarda sólo máximos (no hay evolución horaria);
no hay lluvia real (eventos Sentinel-1 escritos a mano, del norte bonaerense, en `defaults.yml`); escenarios sin
recurrencia; el veredicto llega al visor parseando títulos del README (`webdata.py:332`); no hay tests.

## Decisiones

- **Visor estático, sólo local** (`anega2 serve`). Sin backend. Sin publicación por ahora; el peso no es restricción dura.
- **Audiencia de la vista principal**: cliente no técnico. Lenguaje llano. Vista «Detalle técnico» para autor/arquitecto.
- **Distribución**: mapa + columna de tres tarjetas (maqueta B): 1) Con esta lluvia, 2) ¿Pasó alguna vez?, 3) Detalle técnico ›.
- **Resultados de simulación**: cuadros horarios numéricos (cm, uint8) que el navegador colorea e interpola (enfoque 1).
  Cuadros del dominio completo ±`buffers.lluvia_m` (5 km).
- **Grilla de escenarios media**: P = 25…250 mm cada 25 × duración 3 / 24 / 72 h × suelo normal / saturado = 60 corridas.
- **Lluvia histórica**: ERA5 horaria vía Open-Meteo (principal) + CHIRPS v2 diaria (segunda serie). ERA5-Land queda
  descartado: Open-Meteo devuelve precipitación nula para ese modelo (probado en el ejemplo, 2026-09-25).
- **Precisión**: «certeza» = promedio, sobre los 3 DEM, de la fracción de vecinos 3×3 que superan el umbral (opción C).
- **Paleta HAND**: clases cálidas con los cortes de `rules.yml` (A). Azul reservado sólo para agua.
- **Fuera de alcance** (posible después): Sentinel-2, modelo rápido en el navegador, hietograma con forma de tormentas
  reales, Monte Carlo de error del DEM, publicación web, HTML autocontenido.

## Orden de construcción

1. Fase `clima` (sección 1) → 2. grilla + cuadros horarios (sección 2) → 3. ensamble de DEM y certeza (sección 5)
→ 4. vista Resumen (sección 3) → 5. vista técnica, paleta HAND, `verdict.json` (sección 4).
Cada paso deja el sistema funcionando (el visor viejo sigue andando hasta el paso 4).

---

## 1. Fase `clima`: lluvia histórica

Módulo `anega2/clima.py`, fase CLI `clima` entre `agua` y `sar` en `FASES` (`cli.py`), y en `cmd_list`.

**Fuentes** (punto = centroide del lote; caché y confirmación con `p.confirm` como `dem.py`):
- **ERA5 vía Open-Meteo** `https://archive-api.open-meteo.com/v1/archive`, `hourly=precipitation`, `models=era5`,
  desde 1940-01-01 hasta hoy − 6 días. Pedidos por décadas. Caché `data/raw/clima/era5_<lat>_<lon>.csv` (horaria, UTC);
  en corridas siguientes sólo se piden los días faltantes.
- **CHIRPS v2.0 diaria p05** (COG): `https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/cogs/p05/<YYYY>/chirps-v2.0.<YYYY>.<MM>.<DD>.cog`,
  lectura de un píxel por día vía `/vsicurl` (medido: ~1,5 s/día → ~25 min con 16 hilos para 1981-hoy, la primera vez).
  Caché compartida `cache/chirps/<lat>_<lon>.csv` (lat/lon del centro del píxel CHIRPS), incremental.
  Sin cobertura al sur de 50°S: se omite con aviso.
- Config nueva en `defaults.yml`:
  ```yaml
  clima:
    fuentes: [era5, chirps]
    hilos_chirps: 16
    eventos_n: 10              # tormentas mayores a listar
    separacion_d: 7            # días mínimos entre eventos (desagrupado)
  ```

**Cálculos** (funciones puras en `clima.py`, testeables):
- Series diaria (hora local Argentina) por fuente.
- **Máximos anuales** por ventana móvil de 3 h (sólo ERA5), 24 h y 72 h (ERA5: sobre horas; CHIRPS: 1 y 3 días),
  con fecha. Años con < 300 días válidos se descartan.
- **Período de retorno**: Gumbel por momentos sobre máximos anuales, por fuente y duración, T = 2, 5, 10, 25, 50, 100 años,
  intervalo 90 % por bootstrap (1000 remuestreos, semilla fija). Función inversa `retorno(P_mm, dur_h, fuente) -> T`.
- **Eventos**: tormentas desagrupadas (≥ `separacion_d` días) ordenadas por lluvia de 72 h de ERA5; se guardan
  las `eventos_n` mayores desde 1940 y las `eventos_n` mayores desde 2014-10-03 (inicio de Sentinel-1), con los mm
  de 24/72 h de ambas fuentes.

**Salidas** (`out/`): `clima_serie_diaria.csv` (fecha, era5_mm, chirps_mm), `clima_maximos_anuales.csv`,
`clima_retorno.csv`, `clima_eventos.csv`, `clima_stats.md`, `clima.json` (resumen para webdata y rog:
fuentes, años cubiertos, tabla de retorno, eventos).

**Cambio en `sar.py`**:
- `sar.eventos: auto` pasa a ser el default: toma los eventos post-2014 de `clima.json` (id `AAAA-MM-DD_era5`, fecha
  = fin de la ventana de 72 h). Una lista explícita en `project.yml` sigue funcionando igual que hoy. Los eventos
  del norte bonaerense se quitan de `defaults.yml` y quedan sólo en el `project.yml` del ejemplo.
- Escena «pre»: la última dentro de los 12 días previos. Escena «post»: **la primera pasada en 0-3 días** tras la fecha.
  Si no hay: fila con `nota = "sin pasada a tiempo"` y porcentajes vacíos (no 0 %).
- Si `auto` y no hay `clima.json`: aviso y se saltea la fase (no rompe `run`).

**Errores**: sin red o fuente caída → aviso, se usa lo que haya en caché, las demás fases siguen. Si ninguna fuente
tiene datos, `clima.json` registra `disponible: false` y el visor lo informa.

**Informe**: `report.py` agrega a los números clave «100 mm en 24 h ≈ cada N años (ERA5; CHIRPS: M)». Las reglas no cambian.

## 2. Simulación: grilla de escenarios y cuadros horarios

**Config** (`defaults.yml`, reemplaza `lluvia.escenarios` y `lluvia.saturado`):
```yaml
lluvia:
  grilla: {P_mm: [25, 50, 75, 100, 125, 150, 175, 200, 225, 250], dur_h: [3, 24, 72], suelo: [normal, saturado]}
  ficha: [P050_24h, P100_24h, P150_24h, P200_24h, P100_24h_sat, P150_24h_sat]
  drenaje_h: 24
  procesos: auto            # núcleos − 2
  ensamble: {P_mm: [50, 100, 150, 200], dur_h: [24], suelo: [normal]}   # ver sección 5
```
- Ids con el formato actual: `P<mmm>_<dur>h` y sufijo `_sat`. Las reglas (`hmax_lote_100mm_cm`, `pct_aoi_gt20cm_150mm`)
  siguen leyendo `P100_24h` y `P150_24h`.
- Compatibilidad: si un `project.yml` tiene `escenarios`/`saturado` (formato viejo), se usan tal cual y se avisa.
  El `project.yml` del ejemplo se migra a `grilla`.
- `ficha.py` y `kml.py` usan sólo `lluvia.ficha`.

**Ejecución**: `run_scenario` se reparte con `concurrent.futures.ProcessPoolExecutor(procesos)`; los escenarios ya
calculados (tif + meta + cuadros) se saltean. El tope `presupuesto_min` se mantiene por corrida.
Antes de planificar la implementación se mide una corrida de 200 mm / 72 h con drenaje 24 h para fijar la estimación
(las de 24 h tardan hoy 1-12 min con drenaje 6 h).

**Cuadros horarios**: en cada hora entera de simulación se copia `h` (m) del dominio:
- `data/proc/rog/<id>_frames.npz` en el CRS del proyecto: `h_cm` uint8 (0-255, satura en 2,55 m), `t_h`,
  `lluvia_acum_mm` por hora.
- En el mismo paso de la corrida se calculan por hora las estadísticas del lote: `hmax_lote_cm`, `pct_lote_gt5cm`,
  `pct_lote_gt20cm`, y al final `horas_con_agua_lote` (> 5 cm) y `hora_pico_lote`. Van en `<id>_meta.json`.
- La salida existente (`hmax_dom`, `dur5cm_dom`, `rog_stats.csv`, PNG) no cambia; los PNG se generan sólo para `lluvia.ficha`.

**Hietograma**: bloque alterno genérico actual (`DD_SHAPE_SHORT` para 3 h, `DD_SHAPE_LONG` escalado para 24 y 72 h).

## 3. Vista «Resumen» (pantalla principal)

**Datos que prepara `webdata.py`** en `projects/<n>/web/sim/`:
- Cada cuadro se **reproyecta a EPSG:3857** (vecino más cercano) sobre una grilla común a todos los escenarios
  (en el borde de una faja POSGAR la convergencia llega a ~0,8°, ~70 m a 5 km: no se puede superponer sin reproyectar).
- `sim/<id>.bin.gz`: gzip de `uint8[frames][rows][cols]` (cm). `sim/<id>_cert.bin.gz`: ídem con certeza (sección 5).
- Peso estimado: 72 h + 24 h de drenaje = 96 cuadros × ~333² celdas ≈ 10 MB por escenario sin comprimir;
  con gzip (mayoría de ceros) se espera 50-200 MB por proyecto contando la certeza. Aceptable en local; el visor
  sólo baja los escenarios que se muestran.
- `sim/index.json`: grilla (bounds 3857 y WGS84, filas, columnas), y por escenario: P, dur, suelo, horas, lluvia
  acumulada por hora, estadísticas del lote por hora, horas con agua, hora pico, período de retorno (ERA5 y CHIRPS)
  y si tiene ensamble.
- `verdict.json` (ver sección 4) y `clima.json` copiado.

**Código del visor** (sin build; scripts clásicos que cuelgan de un objeto global):
- `webapp/sim.js`: carga de `index.json`, descarga y descompresión (`DecompressionStream('gzip')`), caché en memoria,
  interpolación, pintado en canvas → `L.imageOverlay` (URL de blob) y lectura por click.
- `webapp/resumen.js`: tarjetas, frase, gráficos, estado de controles.
- `webapp/tecnico.js`: el `app.js` actual reorganizado (sección 4).
- `webapp/app.js`: arranque, carga de proyecto, cambio de vista.
- Funciones puras (interpolación, frase, clasificación de certeza) en `webapp/lib.js`, con tests `node --test` en `webapp/test/`.

**Mapa**: satelital Esri; lote en rojo; sólo agua (se ocultan < 2 cm); azules por profundidad con leyenda en
referencias cotidianas (5 cm «cubre el pie», 20 cm «media pierna», 50 cm «rodilla»). Opacidad según certeza
(sección 5). Al acercar (zoom ≥ 17) se dibuja la grilla de píxeles de 30 m sobre el lote y su entorno.

**Controles** (tarjeta 1): tipo de tormenta (Chaparrón 3 h · Día de lluvia 24 h · Temporal 3 días), suelo
(normal · saturado), deslizador de lluvia 25-250 mm (paso 5 mm), selector de umbral (> 5 cm · > 20 cm),
deslizador de hora con ▶ (≈ 4 cuadros/s). Para un P intermedio: `h = (1−w)·h_a + w·h_b` con los dos escenarios vecinos
en la misma hora (`w` lineal en mm); si las duraciones totales difieren, ambos cubren `dur + 24 h` y no hay desfase.

**Tarjeta 1 · Con esta lluvia**: etiqueta de riesgo (de `verdict.json`, en palabras); frase por plantillas:
- «Con 120 mm en un día: hasta 15 cm en un tercio del lote (probable), se va en ~6 h. Una lluvia así pasa cada ~10 años.»
- «El lote no junta agua (menos de 5 cm).»
- «Más de lo que llovió en cualquier día desde 1940.»
- Si ERA5 y CHIRPS difieren en más de un factor 2 en el período de retorno: «cada 10 a 25 años según la fuente».

Curva del agua en el lote por hora (Chart.js) con barras de lluvia y línea en la hora actual.
**Estado inicial**: día de lluvia 24 h, suelo normal, P = lluvia de T ≈ 10 años (ERA5, redondeada a 5 mm y acotada
a 25-250), hora pico del lote.

**Tarjeta 2 · ¿Pasó alguna vez?**: barras de máximo anual para la duración elegida (ERA5; CHIRPS como puntos), línea
horizontal en los mm elegidos, años que la superan resaltados, texto «se superó N veces desde 1940».
Lista de eventos mayores; al elegir uno: fecha, mm ERA5 / CHIRPS, lámina que predice el modelo con esa lluvia
(interpolada en la grilla) y resultado del radar en lenguaje llano («pasó 2 días después y no vio agua en el lote»,
«no hubo pasada a tiempo», «vio agua en el 12 % del lote»), con botón para mostrar esa escena en el mapa.

**Tarjeta 3**: enlace «Detalle técnico ›».

**Click en el mapa**: «Acá: 18 cm a la hora 18 · máximo 22 cm · con agua 7 h · certeza: probable».

**Faltantes**: cada tarjeta indica la fase a correr (`anega2 run <n> --fase clima`) si faltan sus datos; si falta
`sim/`, el visor abre directamente en la vista técnica.

## 4. Vista «Detalle técnico», paleta HAND y `verdict.json`

- Las pestañas actuales (Veredicto, Capas, Terreno, Histórico, Simulación, Figuras) pasan a esta vista.
  Por defecto no se prende el HAND junto con el agua.
- **Paleta HAND** (visor, figuras `10_terrain_hand*.png` y ficha): clases `< 0,5 m #b71c1c`, `0,5-1 #f4511e`,
  `1-2 #ffb300`, `2-5 #fff3c4`, `> 5` transparente. Cortes leídos de `rules.yml` (`desborde.hand_min_m`).
- **`verdict.json`**: `report.py` escribe `out/verdict.json` con niveles por componente, nivel global, reglas disparadas
  con sus valores, texto markdown del veredicto y de «qué chequear en campo». `webdata.py` lo copia; se elimina el
  parseo de títulos del README. El README sigue generándose igual.
- **HAND con error**: σ = máx(`terreno.sigma_dem_m`, desvío entre los HAND de los 3 DEM en el lote); default
  `sigma_dem_m: 1.0`. Se muestra «0,6 m ± 1 m · probabilidad de estar a menos de 1 m: 65 %» (normal) en la tarjeta de
  HAND y como banda en el perfil de la ficha.

## 5. Precisión: certeza por vecindad y ensamble de DEM

- **Ensamble**: los escenarios de `lluvia.ensamble` (50-200 mm, 24 h, normal = 4) se corren además con los otros dos
  DEM disponibles (hasta 8 corridas extra), usando `data/proc/terrain/<dem>/dem_breach.tif` ya calculados por la fase
  terreno. Sólo se guardan cuadros horarios y metadatos. Si un DEM no está (p. ej. fuera de Argentina no hay IGN), el
  ensamble usa los disponibles y lo declara. Copernicus GLO-30 es un modelo de superficie (ve copas y techos):
  entra al ensamble igual, porque justamente representa ese error, y el detalle técnico muestra qué DEM vio qué.
- **Certeza** por píxel, hora y umbral u (5 y 20 cm): `c = media_d( fracción de la ventana 3×3 del DEM d con h > u )`.
  Sin ensamble, `c` usa sólo el DEM primario. Se precalcula en Python sobre los cuadros ya reproyectados y se guarda
  como uint8 (0-100) por umbral en `<id>_cert.bin.gz`.
- Escenarios intermedios del deslizador: se interpola la certeza igual que la lámina. Escenarios sin ensamble muestran
  en la frase «(certeza sólo por vecindad)».
- **Niveles**: probable ≥ 70 %, posible 30-70 %, poco probable 5-30 %; < 5 % no se dibuja. Opacidad 0,95 / 0,55 / 0,2.
- La frase usa el nivel del lote: la mediana de `c` en los píxeles del lote con agua. Si sólo 1 de 3 DEM ve agua
  en el lote: «(incierto: sólo 1 de 3 modelos de terreno)».

## Verificación

- `pytest` (nuevo `tests/`): máximos por ventana, desagrupado, Gumbel y bootstrap con semilla, retorno inverso, parseo
  de respuestas Open-Meteo/CHIRPS desde fixtures (sin red), hietograma suma P, expansión de la grilla y compatibilidad
  del formato viejo, ida y vuelta de cuadros uint8, certeza sobre grillas sintéticas, `verdict.json` desde tablas de ejemplo.
- `node --test webapp/test/`: interpolación, plantillas de frase, niveles de certeza.
- De punta a punta sobre `ejemplo-bajo-giles`: `anega2 run ejemplo-bajo-giles --si`; P100_24h reproduce la lámina
  máxima del lote de hoy (8 cm) dentro de ± 2 cm; balance de agua con error < 1 %.
- Visor en Chrome: sin errores de consola; controles, ▶, umbral, click, cambio de vista, evento → escena S1; vista
  técnica sin regresiones; se ve el grillado a zoom 17.
- README (es/en) actualizado: fase `clima`, grilla, tiempos, vista Resumen.
