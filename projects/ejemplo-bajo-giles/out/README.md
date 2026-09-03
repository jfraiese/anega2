# Riesgo de anegamiento — Bajo rural en la planicie del Arroyo de Giles (ejemplo) · interpretación

**Polígono**: 14.367 m², centroide -34.403760, -59.420480 (WGS84), CRS de trabajo EPSG:5347 (POSGAR 2007 / Argentina faja 5).
Fecha del análisis: 2026-09-03 · generado por anega2 (informe automático por reglas; ver sección 6).
Buffers: área de interés 500 m, análisis hidrológico 10 km.

---

## Veredicto

**Riesgo MEDIO de anegamiento para el lote** (heurística a 30 m, ver reglas al final), con esta composición:

- **Anegamiento por lluvia local (agua que cae sobre el lote o le llega de arriba): MEDIO-BAJO.** El lote no tiene depresión cerrada, su cuenca aportante es de 0,99 ha (celda más baja) a 9,45 ha (todo el lote) y escurre hacia NE (34°) con pendiente media 0,51 %. En la simulación, con 100 mm en 24 h la lámina máxima en el lote es de 8 cm (8 % del lote con más de 5 cm). Reglas: lámina máxima simulada en el lote con 100 mm en 24 h = 8,2 → MEDIO-BAJO.
- **Desborde del drenaje (el agua sube desde el arroyo o el bajo): MEDIO.** El drenaje ≥ 0,5 km² más cercano está a **134 m** y el punto más bajo del lote queda **0,57 m por encima del cauce por camino de flujo (HAND 0,57–1,4 m)**; el 48 % del entorno de 500 m está a menos de 1 m sobre el drenaje y el 72 % a menos de 2 m. Landsat 1984-2021 nunca registró agua sobre el lote. Sentinel-1 no detectó agua abierta sobre el lote en ninguna escena (máximo en el entorno: 0 %). Con 150 mm en 24 h simulados, el 34 % del entorno supera los 20 cm. Reglas: HAND mínimo del lote (altura sobre el drenaje más cercano por camino de flujo) = 0,57 → MEDIO; % del entorno con más de 20 cm simulados con 150 mm en 24 h = 33,9 → MEDIO.
- **Limitación principal**: la topografía disponible es de 30 m de píxel, con ruido vertical de décimas de metro y sin microrrelieve (zanjas, terraplenes, alcantarillas). A escala de lote la diferencia entre anegarse o no está en decenas de centímetros que el DEM no resuelve. **El veredicto es un diagnóstico regional que hay que confirmar en campo.**

---

## 1. Dónde está el lote en el relieve (terreno)

DEM primario: **FABDEM v1.2 (GLO-30 sin árboles/edificios)** (criterio: distancia mediana OSM→red (m) + preferencia por terreno desnudo). Otros DEM evaluados (control de sensibilidad): IGN MDE-Ar v2.1 30 m, Copernicus DEM GLO-30. Con IGN MDE-Ar v2.1 30 m el lote aparece mucho más alto (HAND 0 m, pendiente 2,14 %): es la firma de copas de árboles o construcciones en un modelo de superficie, no del terreno. 

| Variable (DEM primario, píxeles de 30 m; el lote toca 25) | Lote | Buffer 500 m |
|---|---|---|
| Cota (m snm) | 35,7 – 36,53 (media 36,02) | 35,01 – 42,38 |
| HAND: altura sobre el drenaje más cercano (m) | **0,57 – 1,4** (media 0,89) | media 1,53 · 48 % ≤ 1 m · 72 % ≤ 2 m |
| Pendiente media | 0,51 % | 0,8 % |
| Dirección de escurrimiento (D8 dominante / salida del camino de flujo) | N / NE (34°) | — |
| Distancia al drenaje ≥ 0,5 km² | **134 m** en línea recta · 320 m por camino de flujo | — |
| Cota del cauce más cercano / salto vertical desde el punto más bajo del lote | 35,51 m / 0,19 m (línea recta) · 0,57 m por camino de flujo | — |
| Depresión cerrada en el lote | **No** | 2 depresiones; la mayor 0,3 ha / 31 m³, prof. máx 0,01 m (todas ≤ 10 cm: dentro del ruido del DEM) |
| Cuenca aportante | **0,99 ha** (celda más baja) · 9,45 ha (todo el lote) | — |

**Cómo leerlo**: HAND es cuántos metros tendría que subir el agua desde el drenaje más cercano (por el camino que sigue el
agua) para llegar a cada punto; HAND bajo = bajo del valle. "Cuenca aportante" pequeña significa que el lote no recibe
escurrimiento de otros lados. Figuras `10_terrain_*.png`; tabla completa con todos los DEM en `terrain_stats.md`.

## 2. Historial de agua superficial

**Landsat 1984-2021 (JRC Global Surface Water v1.4, 30 m)**

| Zona | píxeles | agua alguna vez (occ > 0) | occ > 10 % | occ > 50 % | occ máx |
|---|---|---|---|---|---|
| lote (píxeles tocados) | 25 | 0 % | 0 % | 0 % | 0 |
| buffer 500 m | 870 | 0 % | 0 % | 0 % | 0 |
| buffer 10 km | 349023 | 0,16 % | 0,03 % | 0,01 % | 66 |

Distancia del lote al píxel más cercano (centro) con occurrence ≥ 1 / 10 / 50 %: 676 / 2762 / 2780 m (dentro del buffer de 10 km).

Landsat no ve agua bajo árboles ni agua que dure menos de unos días entre pasadas. Figuras `20_jrc_*.png`.

**Sentinel-1 (radar, 10 m)**, máscara de agua por umbral (Otsu o -18.0 dB fijo, ver `sar_stats.md`):

| Evento | Escena (días respecto del evento) | Agua en lote / 500 m / 10 km | Entorno con caída > 3 dB vs. referencia seca |
|---|---|---|---|
| referencia seca | 2023-02-25 | 0 / 0 / 0,01 % | — |
| 2015-08 agosto2015 | 2015-08-18 (+8) | 0 / 0 / 0,06 % | 7,2 % |
| 2016-04 abril2016 | **sin cobertura Sentinel-1** | — | — |
| 2024-03 marzo2024 | 2024-03-03 (-9) | 0 / 0 / 0,01 % | 0,4 % |
| 2024-03 marzo2024 | 2024-03-27 (+15) | 0 / 0 / 0,04 % | 0,1 % |
| 2025-05 mayo2025 | 2025-05-09 (-8) | 0 / 0 / 0,01 % | 1,3 % |
| 2025-05 mayo2025 | 2025-05-15 (-2) | 0 / 0 / 0,06 % | 16,2 % |
| 2025-05 mayo2025 | 2025-05-27 (+10) | 0 / 0 / 0 % | 1,3 % |
| 2026-06 junio2026 | 2026-06-04 (-4) | 0 / 0 / 0 % | 15,5 % |
| 2026-06 junio2026 | 2026-06-09 (+1) | 0 / 0 / 0,03 % | 0,2 % |
| 2026-06 junio2026 | 2026-06-16 (+8) | 0 / 0 / 0 % | 1 % |

Limitaciones: el radar en banda C no ve el suelo bajo copas (agua bajo árboles aparece brillante, no oscura); superficies
lisas no-agua (suelo desnudo húmedo, pavimento) también aparecen oscuras; las escenas caen días antes o después del pico.
Figuras `30_sar_*.png`.

## 3. Simulación lluvia → lámina de agua (rain-on-grid)

Modelo 2D Landlab `OverlandFlow` sobre el DEM primario corregido (fabdem, 30 m), dominio de ±5 km con bordes
abiertos, Manning n = 0.05, infiltración Green-Ampt con Ks = 10.0 mm/h
(ψ = 0.17 m, Δθ = 0.15) y sensibilidad con Ks = 2.0 mm/h (suelo saturado / napa alta).
Hietograma de bloque alterno con relaciones P(d)/P(24 h) genéricas: **sin período de retorno** (no hay IDF local).

| Escenario | Infiltra (mm) | Lote: h máx (cm) | Lote: h media (cm) | Lote: % > 5 cm | Lote: % > 20 cm | Lote: horas > 5 cm | 500 m: % > 5 cm | 500 m: % > 20 cm | 500 m: h máx (cm) |
|---|---|---|---|---|---|---|---|---|---|
| 50 mm / 24 h | 41 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 100 mm / 24 h | 77 | 8 | 3 | 8 | 0 | 3,6 | 28 | 15 | 38 |
| 150 mm / 24 h | 101 | 43 | 16 | 64 | 36 | 7,3 | 53 | 34 | 78 |
| 200 mm / 24 h | 117 | 76 | 45 | 96 | 88 | 8,3 | 63 | 47 | 178 |
| 60 mm / 2 h | 53 | 6 | 3 | 4 | 0 | 2,8 | 27 | 12 | 35 |
| 100 mm / 24 h · suelo saturado (Ks 2) | 48 | 48 | 20 | 76 | 48 | 9,6 | 54 | 36 | 84 |
| 150 mm / 24 h · suelo saturado (Ks 2) | 58 | 167 | 90 | 100 | 100 | 11,2 | 67 | 54 | 247 |

**Escenario → efecto**

| Lluvia | Efecto en el lote | Efecto en el entorno |
|---|---|---|
| 50 mm / 24 h | nada | nada |
| 100 mm / 24 h | lámina de 8 cm en el 8 % del lote durante 3,6 h | 28 % con > 5 cm, 15 % con > 20 cm |
| 150 mm / 24 h | lámina de 43 cm en el 64 % del lote durante 7,3 h; 36 % con más de 20 cm | 53 % con > 5 cm, 34 % con > 20 cm |
| 200 mm / 24 h | lámina de 76 cm en el 96 % del lote durante 8,3 h; 88 % con más de 20 cm | 63 % con > 5 cm, 47 % con > 20 cm |
| 60 mm / 2 h | lámina de 6 cm en el 4 % del lote durante 2,8 h | 27 % con > 5 cm, 12 % con > 20 cm |
| 100 mm / 24 h · suelo saturado (Ks 2) | lámina de 48 cm en el 76 % del lote durante 9,6 h; 48 % con más de 20 cm | 54 % con > 5 cm, 36 % con > 20 cm |
| 150 mm / 24 h · suelo saturado (Ks 2) | lámina de 167 cm en el 100 % del lote durante 11,2 h; 100 % con más de 20 cm | 67 % con > 5 cm, 54 % con > 20 cm |

Advertencias: no incluye la crecida que viene de fuera del dominio; las celdas son de 30 × 30 m; celdas aisladas con láminas
> 1 m suelen ser pozos residuales del DEM; el balance de masa cierra por residuo. Figuras `40_rog_*.png`; tabla `rog_stats.md`.

## 4. Limitaciones

- **DEM de 30 m**: sin microrrelieve ni obras; los modelos de superficie (GLO-30, MDE-Ar) ven copas y techos; FABDEM los remueve
  estadísticamente. Datum vertical EGM2008 (FABDEM/GLO-30) o SRVN16 (IGN): irrelevante para alturas relativas.
- **Sin calibración**: no hay aforos ni marcas de crecida; Manning y Green-Ampt son valores de literatura.
- **Sin período de retorno**: los escenarios son "mm en 24 h".
- **Crecida del arroyo desde aguas arriba**: no simulada; el desborde se evalúa por HAND y por el registro satelital.
- **Satélite**: Landsat no ve bajo nubes ni árboles; Sentinel-1 no ve bajo copas y cae días después del pico.

## 5. Qué chequear en campo

1. **Nivelar el lote contra el drenaje**: con nivel óptico o GPS RTK, medir la cota del punto más bajo del lote y la del
   fondo y la barranca del cauce más cercano (134 m). El DEM dice ≈ 0,57 m de desnivel por camino de flujo; si en campo es
   claramente menor, el riesgo de desborde sube un nivel; si es mayor, baja.
2. **Alcantarillas y terraplenes**: rutas, caminos y vías entre el lote y el drenaje cortan la planicie. Ver diámetro y estado de
   las alcantarillas y si algún terraplén actúa como dique del lado del lote.
3. **Marcas de crecida y testimonio de vecinos**: preguntar por los eventos analizados (2015-08, 2016-04, 2024-03, 2025-05, 2026-06)
   y por la napa (si en años húmedos el agua "brota"). Buscar marcas en postes, alambrados y troncos.
4. **Napa y suelo**: en época húmeda, un pozo de 1-1,5 m para ver la profundidad de la napa; en la llanura pampeana el anegamiento
   por napa alta es tan frecuente como el desborde.
5. **Microrrelieve**: recorrer el lote y el entorno tras una lluvia fuerte para ver dónde se junta agua (el DEM no ve depresiones
   menores que un píxel ni zanjas).
6. **Cota de piso**: si se construye, elevar el piso al menos 0,5 m sobre el terreno natural (y por encima de la cota de crecida
   que surja del punto 1) cubre casi todo el rango de incertidumbre de este análisis.

## 6. Reglas del veredicto

Niveles: BAJO < MEDIO-BAJO < MEDIO < ALTO. Cada componente toma el nivel más alto que dispare alguna regla; el global es el máximo de los dos.

| Componente | Indicador | Umbrales |
|---|---|---|
| lluvia local | profundidad máxima de depresión cerrada dentro del lote (fill − DEM) | ≥ 0.1 → MEDIO, ≥ 0.3 → ALTO |
| lluvia local | cuenca que drena a la celda más baja del lote | ≥ 5 → MEDIO, ≥ 50 → ALTO |
| lluvia local | lámina máxima simulada en el lote con 100 mm en 24 h | ≥ 5 → MEDIO-BAJO, ≥ 10 → MEDIO, ≥ 20 → ALTO |
| lluvia local | % del lote con más de 5 cm con 100 mm en 24 h | ≥ 50 → MEDIO |
| desborde | HAND mínimo del lote (altura sobre el drenaje más cercano por camino de flujo) | < 0.5 → ALTO, < 1.0 → MEDIO, < 2.0 → MEDIO-BAJO |
| desborde | % de píxeles del lote con agua alguna vez (Landsat 1984-2021) | ≥ 0.0001 → ALTO |
| desborde | máximo % del lote detectado como agua en alguna escena Sentinel-1 | ≥ 5 → ALTO |
| desborde | máximo % del entorno (buffer AOI) detectado como agua en alguna escena Sentinel-1 | ≥ 10 → MEDIO |
| desborde | % del entorno con más de 20 cm simulados con 150 mm en 24 h | ≥ 10 → MEDIO |

Eventos Sentinel-1 configurados: 2015-08_agosto2015, 2016-04_abril2016, 2024-03_marzo2024, 2025-05_mayo2025, 2026-06_junio2026. Fuentes y licencias: `SOURCES.md` del repositorio.
