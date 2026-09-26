# Fuentes de datos que usa anega2

Todas las fuentes son de acceso abierto y **ninguna requiere cuenta**. Cada proyecto registra en
`projects/<nombre>/data/raw/` lo que bajó (inventario de DEMs en `dem_inventory.json`).

| Fuente | Uso en anega2 | Acceso | Licencia / condiciones |
|---|---|---|---|
| **IGN MDE-Ar v2.1 30 m** (Modelo Digital de Elevaciones de la República Argentina) | DEM (SRTM+ALOS, referencia vertical SRVN16, precisión declarada ~2 m). Hojas identificadas por el WFS público del IGN y bajadas por el endpoint del visor. Sólo dentro de Argentina. | WFS `https://wms.ign.gob.ar/geoserver/modelos-digitales-elevaciones/wfs` (capa `mde_v2_30m`); descarga `https://dnsg.ign.gob.ar/apps/mapas-geodesia/mde_mapa_geoserver_descarga.php?pid=7&gid=<gid>` | Distribución libre y gratuita según el IGN (https://www.ign.gob.ar/NuestrasActividades/Geodesia/ModeloDigitalElevaciones/Introduccion) |
| **IGN MDE 5 m aerofotogramétrico** | DEM de detalle donde existe (capa `mde_5m`). La descarga directa suele estar restringida (el endpoint redirige al FAQ #30: organismos e instituciones deben solicitarlo a la Dirección de Geodesia); anega2 lo intenta y lo marca como no disponible si no puede. | WFS IGN, capa `mde_5m`; descarga `…?pid=3&gid=<gid>` | Ídem IGN |
| **Copernicus DEM GLO-30** | DEM global de superficie (TanDEM-X 2011-2015, 30 m, EGM2008), leído por ventana con `/vsicurl/`. | `https://copernicus-dem-30m.s3.amazonaws.com/<tile>/<tile>.tif` (AWS Open Data) | Copernicus DEM licence: uso libre con atribución "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved" |
| **FABDEM V1-2** (Forest And Buildings removed Copernicus DEM) | DEM de terreno desnudo (GLO-30 sin árboles ni edificios). Es el primario por defecto cuando reproduce bien la red de drenaje, porque los modelos de superficie ven las copas y techos del lote. Se extrae sólo la hoja necesaria del zip de 10° con lecturas por rango HTTP. | `https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn/<bloque>_FABDEM_V1-2.zip` | **CC BY-NC-SA 4.0** (no comercial). Cita: Hawker, L. et al. (2022) *Environ. Res. Lett.* 17, 024016 |
| **JRC Global Surface Water v1.4** (1984-2021) | Histórico de agua superficial Landsat (occurrence, recurrence, extent, seasonality), leído por ventana. | `https://storage.googleapis.com/global-surface-water/downloads2021/<layer>/<layer>_<tile>v1_4_2021.tif` | Uso libre con cita: Pekel, Cottam, Gorelick, Belward (2016) *Nature* 540, 418-422 |
| **Sentinel-1 RTC** (GRD IW, gamma0 corregido por terreno, 10 m) | Detección de agua por evento de lluvia (filtro Lee + umbral) y referencia seca. | STAC `https://planetarycomputer.microsoft.com/api/stac/v1`, colección `sentinel-1-rtc`, token SAS anónimo | Datos Copernicus Sentinel: libres y abiertos. Procesamiento RTC: Microsoft Planetary Computer |
| **OpenStreetMap** (cursos de agua) | Validación de la red de drenaje derivada de cada DEM y capa de referencia. | Overpass API `https://overpass-api.de/api/interpreter` | ODbL 1.0, © OpenStreetMap contributors |
| **Esri World Imagery / Topo / Street Map** (tiles) | Sólo mapa base de la figura de ubicación y del visor. | `https://server.arcgisonline.com/ArcGIS/rest/services/` | Visualización con atribución (Esri, Maxar, Earthstar Geographics, HERE, Garmin, © OpenStreetMap contributors); no se redistribuyen tiles |
| **ERA5** (vía Open-Meteo) | Lluvia histórica horaria (1940→hoy) en el centroide del lote: máximos anuales y período de retorno (Gumbel) por duración (3/24/72 h), y selección automática de tormentas para buscar en Sentinel-1. Rejilla de reanálisis, ~28 km. | `https://archive-api.open-meteo.com/v1/archive` (`hourly=precipitation`, `models=era5`), sin API key | Contiene información modificada del Copernicus Climate Change Service (2026); ni la Comisión Europea ni ECMWF son responsables del uso que se le dé. **CC BY 4.0**. Acceso vía Open-Meteo (ver atribución en https://open-meteo.com/en/license) |
| **CHIRPS v2.0** (Climate Hazards Center, UCSB) | Lluvia histórica diaria (1981→hoy) en el píxel de 0,05° (~5 km) más cercano al lote, como segunda serie para el período de retorno; leída por ventana (`/vsicurl/`, un COG por día). Sin cobertura al sur de 50°S. | `https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/cogs/p05/<YYYY>/chirps-v2.0.<YYYY>.<MM>.<DD>.cog` | **Dominio público**. Cita: Funk, C. et al. (2015) "The climate hazards infrared precipitation with stations — a new environmental record for monitoring extremes". *Scientific Data* 2, 150066 |
| **Landlab** (software) | Motor rain-on-grid (`OverlandFlow`, de Almeida et al. 2012). | https://landlab.readthedocs.io | MIT |
| **WhiteboxTools** (software) | Hidrología de terreno (breach/fill, D8/D∞, HAND, TWI…). | https://www.whiteboxgeo.com | MIT |

## Fuentes evaluadas y no usadas

- **ORA** (Oficina de Riesgo Agropecuario) y **CONAE**: al 2026-09 no exponen servicios OGC utilizables de anomalías hídricas o
  inundaciones a escala de lote (los productos VIIRS/ABI de CONAE tienen 375 m de píxel).
- **Curvas IDF locales** (INA / Direcciones de Hidráulica): no se integran. anega2 ya calcula un período de retorno
  aproximado por Gumbel sobre ERA5 (28 km, subestima tormentas convectivas) y CHIRPS (5 km, diario) en el punto del
  lote; es una aproximación regional, no una IDF calibrada localmente. Si tenés una IDF de tu zona, es más precisa:
  usala para asignar recurrencia a cada escenario.
- **Copernicus Data Space Ecosystem** (openEO): innecesario, Sentinel-1 RTC de Planetary Computer no requiere cuenta.
- **ERA5-Land** (vía Open-Meteo): descartado; Open-Meteo devuelve precipitación nula para ese modelo (probado en el
  ejemplo, 2026-09-25). Se usa ERA5 (atmosférico) en su lugar.
