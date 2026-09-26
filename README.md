# anega2 · ¿se anega este lote?

Análisis reproducible de **riesgo de anegamiento por lluvia** para cualquier polígono KML en Argentina:
terreno (DEM, red de drenaje, HAND, depresiones, cuenca aportante), historial satelital de agua
(Landsat 1984-2021 y Sentinel-1 por evento), simulación lluvia → lámina de agua (rain-on-grid), informe
con veredicto por reglas, KML para Google Earth y un visor web. Todo con fuentes abiertas y **sin
cuentas** en ningún servicio. *English: [README.en.md](README.en.md).*

> anega2 es un diagnóstico regional a 30 m de píxel, sin calibración. Sirve para saber si un lote está en
> un alto, una ladera o un bajo, cuánto tendría que subir el agua para llegar, si el satélite lo vio
> inundado y qué pasaría con 100-200 mm de lluvia. **No reemplaza una nivelación en campo.**

## Instalación

```bash
git clone <este repo> anega2 && cd anega2
mamba env create -f environment.yml        # o conda; crea el env "anega2" e instala el paquete (-e .)
conda activate anega2
anega2 doctor                              # versiones, WhiteboxTools (baja su binario la primera vez) y acceso a las fuentes
```

Requiere Python ≥ 3.11, GDAL/rasterio/geopandas, WhiteboxTools (vía `whitebox`), Landlab. Probado en macOS (Apple Silicon) y Linux.
Si ya tenés el entorno armado (GDAL, etc.) alcanza con `pip install -e .` (hay `pyproject.toml`).

Tests: `python -m pytest` (65 casos) y `node --test webapp/test/*.test.js` (21 casos; Node ≥ 18 —
pasale el glob, algunas versiones de Node no aceptan una carpeta ahí).

## Uso

```bash
anega2 init mi-lote --kml mi-lote.kml --titulo "Lote en ..."   # crea projects/mi-lote/project.yml
anega2 run mi-lote                                             # todas las fases (pide OK antes de descargas grandes; --si para no preguntar)
anega2 serve                                                   # abre el visor en http://localhost:8000/webapp/?project=mi-lote
```

Fases (`anega2 run <nombre> --fase ...`): `aoi` · `dem` · `terreno` · `agua` · `clima` · `sar` · `lluvia` · `informe` · `ficha` · `kml` · `web`.
Cada fase reutiliza lo que ya está calculado. `clima` tarda unos 25 minutos la primera vez por lote (CHIRPS,
un píxel por día desde 1981; después queda cacheado y sólo se piden los días nuevos). `lluvia` corre en
paralelo (60 escenarios de la grilla + el ensamble de DEM, `procesos: auto`); en la práctica, 1-3 horas
según el CPU. Un proyecto completo, todo en frío, puede llevar medio día; con caché tibia, mucho menos.

El KML puede ser un polígono dibujado en Google Earth (un solo polígono; si hay varios se usa el más grande).
El CRS se elige solo (faja POSGAR 2007 por longitud; UTM fuera de Argentina). Radios, eventos de lluvia
a buscar en Sentinel-1, escenarios y parámetros de suelo se editan en `projects/<nombre>/project.yml`
(defaults comentados en `anega2/defaults.yml`).

## Qué produce (`projects/<nombre>/out/`)

| Archivo | Contenido |
|---|---|
| `README.md` | **Informe**: números clave, veredicto (BAJO / MEDIO-BAJO / MEDIO / ALTO para lluvia local y para desborde), limitaciones, qué chequear en campo y las reglas usadas |
| `veredicto.json` | el mismo veredicto en JSON (niveles por componente, reglas disparadas con sus valores, texto del informe): lo lee el visor |
| `clima_serie_diaria.csv`, `clima_maximos_anuales.csv`, `clima_retorno.csv`, `clima_eventos.csv`, `clima_stats.md`, `clima.json` | **Lluvia histórica**: series ERA5 (Open-Meteo) y CHIRPS, máximos anuales, período de retorno aproximado por duración (Gumbel, intervalo 90 % por bootstrap) y las tormentas mayores desde 1940 y desde 2014 (éstas alimentan los eventos de radar) |
| `ficha_<nombre>.pdf`, `ficha/*.png` | **Ficha para arquitecto / ingeniero**: 8 páginas A4 apaisadas sobre imagen satelital, con leyenda, escala y pie de página. Resumen con veredicto y qué hacer · ubicación regional · lote y drenaje · cotas · altura sobre el drenaje (HAND) · el drenaje más cercano de cerca (perfil transversal con los tres DEM y radar: ¿arroyo o vaguada?) · lluvias simuladas con tabla de escenarios · agua vista por satélite |
| `<nombre>.kml` | KML único: lote, buffer, arroyos OSM, red de drenaje, cuenca aportante, camino de flujo, depresiones, HAND ≤ 1 / ≤ 2 m, manchas de agua simuladas |
| `terrain_stats.md`, `jrc_stats.md`, `sar_stats.md`, `rog_stats.md` | tablas por fase (también en CSV) |
| `10_terrain_*.png`, `20_jrc_*.png`, `30_sar_*.png`, `40_rog_*.png` | figuras con el lote superpuesto |
| `terrain_*_aoi.tif`, `jrc_*_aoi.tif`, `sar_*_aoi.tif`, `rog_*_aoi.tif` | GeoTIFF recortados al buffer de interés |
| `*.geojson` / `*.kml` | vectores (red, cuenca, camino de flujo, depresiones, HAND, manchas) |

El visor (`projects/<nombre>/web/`, servido por `anega2 serve`) abre en la vista **Resumen**, para un
cliente sin conocimientos técnicos: mapa satelital con sólo el lote y el agua simulada (sin capas
técnicas), tipo de tormenta (chaparrón 3 h · día de lluvia 24 h · temporal 72 h), suelo normal/saturado,
deslizador de lluvia (25-250 mm) y de hora con ▶, umbral 5/20 cm, una frase en lenguaje llano con la
**certeza** (probable / posible / poco probable, ver «Cómo decide») y una tarjeta «¿Pasó alguna vez?» con
los máximos anuales históricos y las tormentas mayores enlazadas a su escena de radar. El botón «Detalle
técnico ›» lleva a las pestañas de siempre (Veredicto, Capas, Terreno, Histórico, Simulación, Figuras),
con selector de escenas Sentinel-1, de escenarios de lluvia y click en el mapa para leer cota, HAND
(± incertidumbre del DEM), pendiente y lámina en cada punto. `web/sim/` (15-200 MB según el proyecto:
cuadros horarios comprimidos que alimentan la vista Resumen) no se versiona; se regenera con
`anega2 run <nombre> --fase lluvia web`.

## Cómo decide

1. **DEM**: baja IGN MDE-Ar 30 m (y 5 m si existe y se deja bajar), Copernicus GLO-30 y FABDEM; corre el
   análisis con todos y elige como primario el que mejor reproduce los arroyos de OpenStreetMap, con
   preferencia por FABDEM (terreno desnudo) porque los modelos de superficie ven las copas de los árboles
   y los techos del propio lote y lo hacen parecer una loma.
2. **Terreno** (WhiteboxTools): breach/fill, D8 y D∞, red de drenaje (0,5 y 2 km²), HAND, TWI, pendiente,
   depresiones cerradas (fill − DEM), cuenca aportante al lote, camino de flujo hasta el arroyo.
3. **Histórico**: lluvia histórica de ERA5 horario (Open-Meteo, 1940→) y CHIRPS v2.0 diario (1981→, sin
   cobertura al sur de 50°S), con período de retorno aproximado por duración (Gumbel, intervalo 90 % por
   bootstrap); las tormentas más grandes desde 2014 se usan para elegir automáticamente qué eventos buscar
   en Sentinel-1 (`sar.eventos: auto`, se puede fijar una lista manual en `project.yml`). Agua superficial:
   JRC Global Surface Water (Landsat 1984-2021) y Sentinel-1 RTC de Planetary Computer alrededor de esos
   eventos (filtro Lee, umbral de Otsu con chequeo de plausibilidad o umbral fijo, diferencia contra una
   referencia seca; escena "pre" = la última dentro de 12 días antes, "post" = la primera pasada 0-3 días
   después, si no hay pasada a tiempo queda registrado así).
4. **Lluvia**: Landlab `OverlandFlow` con Green-Ampt sobre el DEM corregido, dominio de ±5 km. Grilla de
   60 escenarios (25-250 mm cada 25, 3/24/72 h, suelo normal/saturado), corridos en paralelo, con cuadros
   horarios de lámina para el visor. Además, un ensamble de 50/100/150/200 mm en 24 h con los otros DEM
   disponibles, para ver cuánto cambia el resultado según el terreno de partida.
5. **Veredicto**: reglas explícitas en `anega2/rules.yml` (HAND mínimo, depresiones, cuenca, agua vista por
   satélite, láminas simuladas). Se imprimen en el informe (y en `veredicto.json`) con los valores que las
   dispararon.
6. **Certeza**: por píxel, hora y umbral (5/20 cm), fracción de la vecindad 3×3 que supera el umbral,
   promediada entre los DEM del ensamble cuando existe. Se clasifica probable (≥ 70 %) / posible (30-70 %) /
   poco probable (5-30 %); menos de 5 % no se dibuja. Escenarios sin ensamble muestran la certeza sólo por
   vecindad del DEM primario.

## Ejemplo

`projects/ejemplo-bajo-giles/` es un caso público corrido de punta a punta: un bajo rural de 1,4 ha en la
planicie de inundación del Arroyo de Giles (Buenos Aires), a 134 m del cauce y 0,57-1,4 m por encima de él
(HAND). Los satélites nunca lo vieron con agua; con 50 mm no pasa nada, con 100 mm en 24 h apenas 9 cm en el
8 % del lote, con 150 mm el modelo pone hasta 44 cm (20 cm o más en el 44 % del lote) y con 200 mm, hasta
77 cm en casi todo (88 % supera los 20 cm). Según ERA5, 100 mm en 24 h ocurre en promedio cada 12 años
(cada 10 según CHIRPS). Veredicto: MEDIO. Ver `projects/ejemplo-bajo-giles/out/README.md`, la ficha
`ficha_ejemplo-bajo-giles.pdf`, y `anega2 serve` para recorrerlo en el visor (vista Resumen).

![visor](docs/visor.jpg)

(El ejemplo no incluye `data/` ni los GeoTIFF: se regeneran con `anega2 run ejemplo-bajo-giles`.
`web/sim/` tampoco se versiona: se regenera con `anega2 run ejemplo-bajo-giles --fase lluvia web`.)

## Limitaciones honestas

Píxel de 30 m (no ve zanjas, terraplenes ni alcantarillas), sin calibración, sin crecida del arroyo desde
fuera del dominio, Sentinel-1 no ve bajo árboles y pasa cada 6-12 días, período de retorno aproximado
(ERA5 tiene 28 km de píxel y subestima tormentas convectivas; CHIRPS, 5 km, es diario). Los umbrales del
veredicto son heurísticos: cambialos en `rules.yml` si tenés criterio local.

## Licencia y atribuciones

Código MIT. Los datos tienen sus licencias (ver [SOURCES.md](SOURCES.md)): en particular **FABDEM es
CC BY-NC-SA 4.0 (no comercial)**, Copernicus DEM y Sentinel requieren atribución, JRC y OSM también.
IGN: distribución libre y gratuita. ERA5 (vía Open-Meteo) es CC BY 4.0 (Copernicus Climate Change
Service); CHIRPS es de dominio público con cita. Mapas base Esri sólo para visualización.

## Desarrollo

Paquete `anega2/` (`project.py` config y rutas, `common.py` helpers, un módulo por fase, `report.py` +
`rules.yml`, `cli.py`). Visor estático en `webapp/`. Diseño en `docs/superpowers/specs/`.
Notas de implementación: WhiteboxTools decodifica mal GeoTIFF float32 con deflate+predictor (los
intermedios se escriben sin compresión); su `RasterStreamsToVector` falla en macOS arm64 (la red se
vectoriza en Python desde el puntero D8); Landlab `OverlandFlow` necesita una película mínima de agua.
