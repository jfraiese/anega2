# Riesgo de anegamiento — Bajo rural en la planicie del Arroyo de Giles (ejemplo) · interpretación

**Polígono**: 14.367 m², centroide -34.403760, -59.420480 (WGS84), CRS de trabajo EPSG:5347 (POSGAR 2007 / Argentina faja 5).
Fecha del análisis: 2026-09-26 · generado por anega2 (informe automático por reglas; ver sección 6).
Buffers: área de interés 500 m, análisis hidrológico 10 km.

---

## Veredicto

**Riesgo MEDIO de anegamiento para el lote** (heurística a 30 m, ver reglas al final), con esta composición:

- **Anegamiento por lluvia local (agua que cae sobre el lote o le llega de arriba): MEDIO-BAJO.** El lote no tiene depresión cerrada, su cuenca aportante es de 0,99 ha (celda más baja) a 9,45 ha (todo el lote) y escurre hacia NE (34°) con pendiente media 0,51 %. En la simulación, con 100 mm en 24 h la lámina máxima en el lote es de 9 cm (8 % del lote con más de 5 cm). Reglas: lámina máxima simulada en el lote con 100 mm en 24 h = 9,1 → MEDIO-BAJO.
- **Desborde del drenaje (el agua sube desde el arroyo o el bajo): MEDIO.** El drenaje ≥ 0,5 km² más cercano está a **134 m** y el punto más bajo del lote queda **0,57 m por encima del cauce por camino de flujo (HAND 0,57–1,4 m)**; el 48 % del entorno de 500 m está a menos de 1 m sobre el drenaje y el 72 % a menos de 2 m. Landsat 1984-2021 nunca registró agua sobre el lote. Sentinel-1 no detectó agua abierta sobre el lote en ninguna escena (máximo en el entorno: 0 %). Con 150 mm en 24 h simulados, el 34 % del entorno supera los 20 cm. Reglas: HAND mínimo del lote (altura sobre el drenaje más cercano por camino de flujo) = 0,57 → MEDIO; % del entorno con más de 20 cm simulados con 150 mm en 24 h = 34,22 → MEDIO.
- **Frecuencia**: 100 mm en 24 h ocurre en promedio cada 12 años según ERA5 (cada 10 según CHIRPS).
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
| 2015-08 agosto2015 | **sin cobertura Sentinel-1** | — | — |
| 2016-04 abril2016 | **sin cobertura Sentinel-1** | — | — |
| 2024-03 marzo2024 | 2024-03-03 (-9) | 0 / 0 / 0,01 % | 0,4 % |
| 2024-03 marzo2024 | **sin pasada a tiempo** (no se puede saber) | — | — |
| 2025-05 mayo2025 | 2025-05-15 (-2) | 0 / 0 / 0,06 % | 16,2 % |
| 2025-05 mayo2025 | **sin pasada a tiempo** (no se puede saber) | — | — |
| 2026-06 junio2026 | 2026-06-04 (-4) | 0 / 0 / 0 % | 15,5 % |
| 2026-06 junio2026 | 2026-06-09 (+1) | 0 / 0 / 0,03 % | 0,2 % |

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
| 25 mm / 3 h | 25 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 25 mm / 3 h · suelo saturado (Ks 2) | 23 | 1 | 1 | 0 | 0 | 0 | 12 | 0 | 16 |
| 25 mm / 24 h | 25 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 25 mm / 24 h · suelo saturado (Ks 2) | 25 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 7 |
| 25 mm / 72 h | 25 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 25 mm / 72 h · suelo saturado (Ks 2) | 25 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 50 mm / 3 h | 50 | 2 | 1 | 0 | 0 | 0 | 10 | 0 | 14 |
| 50 mm / 3 h · suelo saturado (Ks 2) | 31 | 24 | 6 | 32 | 8 | 7,4 | 42 | 25 | 57 |
| 50 mm / 24 h | 50 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 50 mm / 24 h · suelo saturado (Ks 2) | 42 | 7 | 2 | 4 | 0 | 3,2 | 26 | 13 | 36 |
| 50 mm / 72 h | 50 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 50 mm / 72 h · suelo saturado (Ks 2) | 47 | 2 | 1 | 0 | 0 | 0 | 17 | 0 | 21 |
| 75 mm / 3 h | 66 | 15 | 4 | 20 | 0 | 4,9 | 38 | 20 | 47 |
| 75 mm / 3 h · suelo saturado (Ks 2) | 33 | 52 | 23 | 76 | 56 | 8,8 | 56 | 37 | 88 |
| 75 mm / 24 h | 74 | 2 | 1 | 0 | 0 | 0 | 13 | 0 | 16 |
| 75 mm / 24 h · suelo saturado (Ks 2) | 50 | 29 | 8 | 44 | 16 | 8,5 | 45 | 28 | 63 |
| 75 mm / 72 h | 75 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4 |
| 75 mm / 72 h · suelo saturado (Ks 2) | 61 | 16 | 4 | 20 | 0 | 7,2 | 32 | 20 | 47 |
| 100 mm / 3 h | 75 | 42 | 16 | 64 | 36 | 6,9 | 53 | 33 | 77 |
| 100 mm / 3 h · suelo saturado (Ks 2) | 34 | 76 | 44 | 96 | 88 | 9,3 | 62 | 46 | 112 |
| 100 mm / 24 h | 94 | 9 | 3 | 8 | 0 | 3,9 | 29 | 16 | 39 |
| 100 mm / 24 h · suelo saturado (Ks 2) | 57 | 49 | 21 | 76 | 52 | 9,6 | 55 | 36 | 86 |
| 100 mm / 72 h | 99 | 2 | 1 | 0 | 0 | 0 | 11 | 0 | 15 |
| 100 mm / 72 h · suelo saturado (Ks 2) | 73 | 31 | 9 | 48 | 16 | 9 | 45 | 28 | 66 |
| 125 mm / 3 h | 80 | 67 | 36 | 88 | 76 | 7,5 | 61 | 43 | 102 |
| 125 mm / 3 h · suelo saturado (Ks 2) | 35 | 104 | 69 | 100 | 96 | 9,6 | 67 | 54 | 226 |
| 125 mm / 24 h | 110 | 26 | 7 | 36 | 8 | 6,5 | 45 | 26 | 59 |
| 125 mm / 24 h · suelo saturado (Ks 2) | 62 | 76 | 44 | 96 | 84 | 10,5 | 62 | 45 | 210 |
| 125 mm / 72 h | 122 | 3 | 2 | 0 | 0 | 0 | 23 | 6 | 29 |
| 125 mm / 72 h · suelo saturado (Ks 2) | 83 | 46 | 19 | 76 | 48 | 10,1 | 53 | 35 | 84 |
| 150 mm / 3 h | 84 | 97 | 62 | 100 | 96 | 7,9 | 66 | 52 | 206 |
| 150 mm / 3 h · suelo saturado (Ks 2) | 36 | 170 | 98 | 100 | 100 | 9,9 | 72 | 60 | 273 |
| 150 mm / 24 h | 122 | 44 | 17 | 68 | 44 | 7,3 | 53 | 34 | 79 |
| 150 mm / 24 h · suelo saturado (Ks 2) | 67 | 148 | 82 | 100 | 100 | 11,3 | 67 | 53 | 244 |
| 150 mm / 72 h | 139 | 19 | 5 | 24 | 0 | 5,9 | 40 | 22 | 51 |
| 150 mm / 72 h · suelo saturado (Ks 2) | 92 | 62 | 31 | 88 | 72 | 11,1 | 59 | 41 | 169 |
| 175 mm / 3 h | 88 | 151 | 84 | 100 | 100 | 8,1 | 71 | 57 | 262 |
| 175 mm / 3 h · suelo saturado (Ks 2) | 37 | 186 | 120 | 100 | 100 | 10,1 | 76 | 65 | 298 |
| 175 mm / 24 h | 133 | 61 | 31 | 88 | 72 | 7,9 | 59 | 41 | 97 |
| 175 mm / 24 h · suelo saturado (Ks 2) | 70 | 185 | 102 | 100 | 100 | 12,1 | 69 | 58 | 272 |
| 175 mm / 72 h | 154 | 34 | 11 | 52 | 20 | 7,1 | 49 | 30 | 69 |
| 175 mm / 72 h · suelo saturado (Ks 2) | 100 | 94 | 60 | 100 | 96 | 12,1 | 64 | 49 | 221 |
| 200 mm / 3 h | 91 | 180 | 106 | 100 | 100 | 8,3 | 75 | 63 | 294 |
| 200 mm / 3 h · suelo saturado (Ks 2) | 37 | 166 | 121 | 100 | 100 | 10,2 | 79 | 68 | 314 |
| 200 mm / 24 h | 143 | 77 | 45 | 96 | 88 | 8,3 | 63 | 47 | 139 |
| 200 mm / 24 h · suelo saturado (Ks 2) | 73 | 233 | 131 | 100 | 100 | 12,9 | 71 | 62 | 292 |
| 200 mm / 72 h | 169 | 48 | 20 | 76 | 48 | 7,7 | 55 | 36 | 84 |
| 200 mm / 72 h · suelo saturado (Ks 2) | 108 | 163 | 86 | 100 | 100 | 13,1 | 67 | 54 | 244 |
| 225 mm / 3 h | 93 | 182 | 121 | 100 | 100 | 8,5 | 80 | 68 | 306 |
| 225 mm / 3 h · suelo saturado (Ks 2) | 38 | 204 | 142 | 100 | 100 | 10,3 | 81 | 72 | 354 |
| 225 mm / 24 h | 152 | 143 | 79 | 100 | 100 | 8,6 | 67 | 54 | 218 |
| 225 mm / 24 h · suelo saturado (Ks 2) | 76 | 187 | 114 | 100 | 100 | 13,7 | 72 | 62 | 303 |
| 225 mm / 72 h | 184 | 60 | 30 | 88 | 68 | 8,1 | 59 | 41 | 96 |
| 225 mm / 72 h · suelo saturado (Ks 2) | 114 | 194 | 107 | 100 | 100 | 14,2 | 69 | 59 | 278 |
| 250 mm / 3 h | 95 | 181 | 129 | 100 | 100 | 8,6 | 82 | 70 | 308 |
| 250 mm / 3 h · suelo saturado (Ks 2) | 38 | 255 | 163 | 100 | 100 | 10,5 | 84 | 74 | 381 |
| 250 mm / 24 h | 162 | 158 | 88 | 100 | 100 | 8,9 | 70 | 57 | 265 |
| 250 mm / 24 h · suelo saturado (Ks 2) | 78 | 221 | 128 | 100 | 100 | 14,4 | 74 | 65 | 314 |
| 250 mm / 72 h | 198 | 72 | 40 | 96 | 80 | 8,5 | 62 | 45 | 108 |
| 250 mm / 72 h · suelo saturado (Ks 2) | 121 | 208 | 115 | 100 | 100 | 15,2 | 70 | 60 | 272 |

**Escenario → efecto**

| Lluvia | Efecto en el lote | Efecto en el entorno |
|---|---|---|
| 25 mm / 3 h | nada | nada |
| 25 mm / 3 h · suelo saturado (Ks 2) | nada | 12 % con > 5 cm |
| 25 mm / 24 h | nada | nada |
| 25 mm / 24 h · suelo saturado (Ks 2) | nada | nada |
| 25 mm / 72 h | nada | nada |
| 25 mm / 72 h · suelo saturado (Ks 2) | nada | nada |
| 50 mm / 3 h | nada | 10 % con > 5 cm |
| 50 mm / 3 h · suelo saturado (Ks 2) | lámina de 24 cm en el 32 % del lote durante 7,4 h; 8 % con más de 20 cm | 42 % con > 5 cm, 25 % con > 20 cm |
| 50 mm / 24 h | nada | nada |
| 50 mm / 24 h · suelo saturado (Ks 2) | lámina de 7 cm en el 4 % del lote durante 3,2 h | 26 % con > 5 cm, 13 % con > 20 cm |
| 50 mm / 72 h | nada | nada |
| 50 mm / 72 h · suelo saturado (Ks 2) | nada | 17 % con > 5 cm |
| 75 mm / 3 h | lámina de 15 cm en el 20 % del lote durante 4,9 h | 38 % con > 5 cm, 20 % con > 20 cm |
| 75 mm / 3 h · suelo saturado (Ks 2) | lámina de 52 cm en el 76 % del lote durante 8,8 h; 56 % con más de 20 cm | 56 % con > 5 cm, 37 % con > 20 cm |
| 75 mm / 24 h | nada | 13 % con > 5 cm |
| 75 mm / 24 h · suelo saturado (Ks 2) | lámina de 29 cm en el 44 % del lote durante 8,5 h; 16 % con más de 20 cm | 45 % con > 5 cm, 28 % con > 20 cm |
| 75 mm / 72 h | nada | nada |
| 75 mm / 72 h · suelo saturado (Ks 2) | lámina de 16 cm en el 20 % del lote durante 7,2 h | 32 % con > 5 cm, 20 % con > 20 cm |
| 100 mm / 3 h | lámina de 42 cm en el 64 % del lote durante 6,9 h; 36 % con más de 20 cm | 53 % con > 5 cm, 33 % con > 20 cm |
| 100 mm / 3 h · suelo saturado (Ks 2) | lámina de 76 cm en el 96 % del lote durante 9,3 h; 88 % con más de 20 cm | 62 % con > 5 cm, 46 % con > 20 cm |
| 100 mm / 24 h | lámina de 9 cm en el 8 % del lote durante 3,9 h | 29 % con > 5 cm, 16 % con > 20 cm |
| 100 mm / 24 h · suelo saturado (Ks 2) | lámina de 49 cm en el 76 % del lote durante 9,6 h; 52 % con más de 20 cm | 55 % con > 5 cm, 36 % con > 20 cm |
| 100 mm / 72 h | nada | 11 % con > 5 cm |
| 100 mm / 72 h · suelo saturado (Ks 2) | lámina de 31 cm en el 48 % del lote durante 9 h; 16 % con más de 20 cm | 45 % con > 5 cm, 28 % con > 20 cm |
| 125 mm / 3 h | lámina de 67 cm en el 88 % del lote durante 7,5 h; 76 % con más de 20 cm | 61 % con > 5 cm, 43 % con > 20 cm |
| 125 mm / 3 h · suelo saturado (Ks 2) | lámina de 104 cm en el 100 % del lote durante 9,6 h; 96 % con más de 20 cm | 67 % con > 5 cm, 54 % con > 20 cm |
| 125 mm / 24 h | lámina de 26 cm en el 36 % del lote durante 6,5 h; 8 % con más de 20 cm | 45 % con > 5 cm, 26 % con > 20 cm |
| 125 mm / 24 h · suelo saturado (Ks 2) | lámina de 76 cm en el 96 % del lote durante 10,5 h; 84 % con más de 20 cm | 62 % con > 5 cm, 45 % con > 20 cm |
| 125 mm / 72 h | lámina de 3 cm en el 0 % del lote durante 0 h | 23 % con > 5 cm, 6 % con > 20 cm |
| 125 mm / 72 h · suelo saturado (Ks 2) | lámina de 46 cm en el 76 % del lote durante 10,1 h; 48 % con más de 20 cm | 53 % con > 5 cm, 35 % con > 20 cm |
| 150 mm / 3 h | lámina de 97 cm en el 100 % del lote durante 7,9 h; 96 % con más de 20 cm | 66 % con > 5 cm, 52 % con > 20 cm |
| 150 mm / 3 h · suelo saturado (Ks 2) | lámina de 170 cm en el 100 % del lote durante 9,9 h; 100 % con más de 20 cm | 72 % con > 5 cm, 60 % con > 20 cm |
| 150 mm / 24 h | lámina de 44 cm en el 68 % del lote durante 7,3 h; 44 % con más de 20 cm | 53 % con > 5 cm, 34 % con > 20 cm |
| 150 mm / 24 h · suelo saturado (Ks 2) | lámina de 148 cm en el 100 % del lote durante 11,3 h; 100 % con más de 20 cm | 67 % con > 5 cm, 53 % con > 20 cm |
| 150 mm / 72 h | lámina de 19 cm en el 24 % del lote durante 5,9 h | 40 % con > 5 cm, 22 % con > 20 cm |
| 150 mm / 72 h · suelo saturado (Ks 2) | lámina de 62 cm en el 88 % del lote durante 11,1 h; 72 % con más de 20 cm | 59 % con > 5 cm, 41 % con > 20 cm |
| 175 mm / 3 h | lámina de 151 cm en el 100 % del lote durante 8,1 h; 100 % con más de 20 cm | 71 % con > 5 cm, 57 % con > 20 cm |
| 175 mm / 3 h · suelo saturado (Ks 2) | lámina de 186 cm en el 100 % del lote durante 10,1 h; 100 % con más de 20 cm | 76 % con > 5 cm, 65 % con > 20 cm |
| 175 mm / 24 h | lámina de 61 cm en el 88 % del lote durante 7,9 h; 72 % con más de 20 cm | 59 % con > 5 cm, 41 % con > 20 cm |
| 175 mm / 24 h · suelo saturado (Ks 2) | lámina de 185 cm en el 100 % del lote durante 12,1 h; 100 % con más de 20 cm | 69 % con > 5 cm, 58 % con > 20 cm |
| 175 mm / 72 h | lámina de 34 cm en el 52 % del lote durante 7,1 h; 20 % con más de 20 cm | 49 % con > 5 cm, 30 % con > 20 cm |
| 175 mm / 72 h · suelo saturado (Ks 2) | lámina de 94 cm en el 100 % del lote durante 12,1 h; 96 % con más de 20 cm | 64 % con > 5 cm, 49 % con > 20 cm |
| 200 mm / 3 h | lámina de 180 cm en el 100 % del lote durante 8,3 h; 100 % con más de 20 cm | 75 % con > 5 cm, 63 % con > 20 cm |
| 200 mm / 3 h · suelo saturado (Ks 2) | lámina de 166 cm en el 100 % del lote durante 10,2 h; 100 % con más de 20 cm | 79 % con > 5 cm, 68 % con > 20 cm |
| 200 mm / 24 h | lámina de 77 cm en el 96 % del lote durante 8,3 h; 88 % con más de 20 cm | 63 % con > 5 cm, 47 % con > 20 cm |
| 200 mm / 24 h · suelo saturado (Ks 2) | lámina de 233 cm en el 100 % del lote durante 12,9 h; 100 % con más de 20 cm | 71 % con > 5 cm, 62 % con > 20 cm |
| 200 mm / 72 h | lámina de 48 cm en el 76 % del lote durante 7,7 h; 48 % con más de 20 cm | 55 % con > 5 cm, 36 % con > 20 cm |
| 200 mm / 72 h · suelo saturado (Ks 2) | lámina de 163 cm en el 100 % del lote durante 13,1 h; 100 % con más de 20 cm | 67 % con > 5 cm, 54 % con > 20 cm |
| 225 mm / 3 h | lámina de 182 cm en el 100 % del lote durante 8,5 h; 100 % con más de 20 cm | 80 % con > 5 cm, 68 % con > 20 cm |
| 225 mm / 3 h · suelo saturado (Ks 2) | lámina de 204 cm en el 100 % del lote durante 10,3 h; 100 % con más de 20 cm | 81 % con > 5 cm, 72 % con > 20 cm |
| 225 mm / 24 h | lámina de 143 cm en el 100 % del lote durante 8,6 h; 100 % con más de 20 cm | 67 % con > 5 cm, 54 % con > 20 cm |
| 225 mm / 24 h · suelo saturado (Ks 2) | lámina de 187 cm en el 100 % del lote durante 13,7 h; 100 % con más de 20 cm | 72 % con > 5 cm, 62 % con > 20 cm |
| 225 mm / 72 h | lámina de 60 cm en el 88 % del lote durante 8,1 h; 68 % con más de 20 cm | 59 % con > 5 cm, 41 % con > 20 cm |
| 225 mm / 72 h · suelo saturado (Ks 2) | lámina de 194 cm en el 100 % del lote durante 14,2 h; 100 % con más de 20 cm | 69 % con > 5 cm, 59 % con > 20 cm |
| 250 mm / 3 h | lámina de 181 cm en el 100 % del lote durante 8,6 h; 100 % con más de 20 cm | 82 % con > 5 cm, 70 % con > 20 cm |
| 250 mm / 3 h · suelo saturado (Ks 2) | lámina de 255 cm en el 100 % del lote durante 10,5 h; 100 % con más de 20 cm | 84 % con > 5 cm, 74 % con > 20 cm |
| 250 mm / 24 h | lámina de 158 cm en el 100 % del lote durante 8,9 h; 100 % con más de 20 cm | 70 % con > 5 cm, 57 % con > 20 cm |
| 250 mm / 24 h · suelo saturado (Ks 2) | lámina de 221 cm en el 100 % del lote durante 14,4 h; 100 % con más de 20 cm | 74 % con > 5 cm, 65 % con > 20 cm |
| 250 mm / 72 h | lámina de 72 cm en el 96 % del lote durante 8,5 h; 80 % con más de 20 cm | 62 % con > 5 cm, 45 % con > 20 cm |
| 250 mm / 72 h · suelo saturado (Ks 2) | lámina de 208 cm en el 100 % del lote durante 15,2 h; 100 % con más de 20 cm | 70 % con > 5 cm, 60 % con > 20 cm |

Advertencias: no incluye la crecida que viene de fuera del dominio; las celdas son de 30 × 30 m; celdas aisladas con láminas
> 1 m suelen ser pozos residuales del DEM; el balance de masa cierra por residuo. Figuras `40_rog_*.png`; tabla `rog_stats.md`.

## 4. Limitaciones

- **DEM de 30 m**: sin microrrelieve ni obras; los modelos de superficie (GLO-30, MDE-Ar) ven copas y techos; FABDEM los remueve
  estadísticamente. Datum vertical EGM2008 (FABDEM/GLO-30) o SRVN16 (IGN): irrelevante para alturas relativas.
- **Sin calibración**: no hay aforos ni marcas de crecida; Manning y Green-Ampt son valores de literatura.
- **Período de retorno aproximado**: Gumbel sobre máximos anuales de ERA5 (28 km, subestima tormentas convectivas) y CHIRPS (5 km); no hay IDF local.
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

Eventos Sentinel-1 configurados: 2015-08, 2016-04, 2024-03, 2025-05, 2026-06. Fuentes y licencias: `SOURCES.md` del repositorio.
