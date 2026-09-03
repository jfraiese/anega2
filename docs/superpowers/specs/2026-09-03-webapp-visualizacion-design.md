# Web app de visualización · giles-flood — diseño

Fecha: 2026-09-03 · Estado: aprobado por el propietario (chat) · Alcance: sitio estático local.

## Objetivo
Explorar en el navegador todos los productos del análisis de riesgo de anegamiento del lote
(fases 0-3): mapa con capas prendibles sobre imagen satelital, números y veredicto, comparación
de escenarios de lluvia y lectura de valores por click.

## Decisiones
- **Destino**: local, servido con `python -m http.server -d webapp 8000`. Sin backend, sin build.
  Publicable después en Vercel/Netlify como sitio estático sin cambios.
- **Stack**: Leaflet 1.9 (mapa), Chart.js 4 (gráficos), proj4js (WGS84 ↔ EPSG:5347 para el click),
  todo desde cdnjs. HTML/CSS/JS plano en castellano.
- **Datos** preparados por `scripts/09_webapp_data.py` en `webapp/data/`:
  - `layers.json`: manifiesto (id, grupo, título, tipo geojson/imagen, url, bounds WGS84, leyenda, visibilidad inicial).
  - GeoJSON WGS84: lote, buffer 500 m, buffer 10 km, arroyos OSM, red ≥0,5 y ≥2 km², cuenca aportante,
    camino de flujo, depresiones, HAND ≤1/≤2 m, manchas > 5 cm por escenario.
  - Rasters como PNG RGBA reproyectados a Web Mercator (nodata transparente, paleta fija):
    DEM, HAND, pendiente, TWI, depresiones, acumulación (log), distancia al drenaje (10 km);
    JRC occurrence (10 km); Sentinel-1 dB y máscara de agua por escena (±3 km);
    lámina máxima y duración > 5 cm por escenario (dominio ±5 km).
  - `stats.json`: tablas terreno/JRC/SAR/escenarios, hietogramas y parámetros, DEM primario,
    texto del veredicto (sección "Veredicto" de `out/README.md`), datos del lote.
  - `grid.json`: grilla de 30 m en ±2 km del lote con cota, HAND, pendiente, TWI, depresión,
    acumulación y lámina máxima por escenario (para el popup del click).
  - `figures/`: copia de los PNG de `out/` con leyenda.
- **UI**: mapa (fondos Esri satelital / Esri topo / OSM; leyenda; slider de opacidad; escala; popup
  de valores) + panel con pestañas Veredicto · Capas · Terreno · Histórico · Simulación · Figuras.
  En Histórico, elegir una escena Sentinel-1 muestra su capa; en Simulación, elegir un escenario
  muestra su lámina y su hietograma. Rasters de un mismo grupo son excluyentes (radio); vectores, checkbox.

## Fuera de alcance
Edición de datos, autenticación, backend, tiles propios, soporte offline del mapa base.

## Verificación
- El script valida que exista cada archivo referenciado en `layers.json` y que las tablas no estén vacías.
- Se abre el sitio en Chrome: sin errores de consola, todas las capas se prenden/apagan, click devuelve
  valores en el lote, el selector de escenario cambia la capa.

## Secuencia de implementación
1. `scripts/09_webapp_data.py` (rasters → PNG 3857, GeoJSON 4326, stats/grid/manifiesto).
2. `webapp/index.html`, `webapp/style.css`, `webapp/app.js`.
3. Correr, abrir en Chrome, corregir.
4. Documentar en README (sección "Web app") y commit.
