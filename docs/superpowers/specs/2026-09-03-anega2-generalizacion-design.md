# anega2 · generalización del análisis de anegamiento a cualquier polígono KML — diseño

Fecha: 2026-09-03 · Estado: aprobado en chat · Alcance: Argentina, repo público, uso local.

## Objetivo
Convertir el análisis hecho para un lote en San Andrés de Giles en una herramienta reproducible
(`anega2`) que, a partir de un polígono KML, corra las fases terreno → histórico satelital →
Sentinel-1 → simulación lluvia-escurrimiento → informe → KML → visor web, para cualquier lugar de
Argentina, y publicarla como repo open source con un ejemplo público. El lote del autor sigue
funcionando en su máquina pero queda fuera del repo público.

## Decisiones
- **Nombre**: `anega2` (paquete Python, comando `python -m anega2` / `anega2`).
- **Licencia**: MIT para el código. Advertencia explícita: FABDEM es CC BY-NC-SA 4.0 (los productos
  derivados de FABDEM no admiten uso comercial); GLO-30, JRC, Sentinel-1, OSM e IGN con sus atribuciones.
- **Territorio**: Argentina. CRS automático: faja POSGAR 2007 por longitud (EPSG:5343-5349,
  faja = round((lon+72)/3)+1); fuera de Argentina, UTM automática y sólo fuentes globales.
- **Fuentes**: IGN MDE-Ar 30 m y 5 m (si cubre y se deja bajar), Copernicus GLO-30, FABDEM; JRC GSW;
  Sentinel-1 RTC (Planetary Computer, sin cuenta); OSM Overpass. Elección del DEM primario: menor
  distancia mediana de los arroyos OSM a la red derivada, con preferencia por terreno desnudo (FABDEM)
  si está a ≤ 1,5× del mejor.
- **Proyectos por carpeta**: `projects/<nombre>/project.yml` + `lote.kml` + `data/{raw,proc}` + `out/` + `web/`.
  Git ignora `projects/*` salvo el ejemplo público. Caché compartida de hojas IGN y FABDEM en `cache/` (ignorada).
- **Informe automático** (`out/README.md`) con veredicto por reglas explícitas en `anega2/rules.yml`.
- **Visor**: mismo sitio estático, multi-proyecto (`webapp/?project=<nombre>`, datos en `projects/<nombre>/web/`),
  índice de proyectos generado; `anega2 serve` levanta el servidor y abre el navegador.
- **Ejemplo público**: polígono sobre terreno público en zona que sólo se anega con lluvias grandes
  pero de forma significativa (se elige corriendo candidatos; primer candidato: ribera del Río Areco
  en San Antonio de Areco). Resultados completos en el repo.
- **Publicación**: el repo público arranca con historia nueva (commit inicial limpio); la historia
  actual (con el KML y resultados privados) queda en una rama local `historial-privado` que no se
  publica. Chequeo de secretos/datos personales antes del push. El push lo autoriza el autor.

## Estructura
```
anega2/            paquete: project.py (config, rutas, CRS), common.py, aoi.py, dem.py, terrain.py,
                   water.py, sar.py, rog.py, report.py, rules.yml, kml.py, webdata.py, cli.py, defaults.yml
webapp/            visor estático (index.html, app.js, style.css)
projects/          proyectos (sólo el ejemplo se versiona)
cache/             hojas IGN / FABDEM compartidas (ignorada)
environment.yml    conda (agrega pyyaml)
README.md / README.en.md · LICENSE · SOURCES.md (fuentes y licencias) · docs/
```

## CLI
- `anega2 init <nombre> --kml <archivo.kml> [--titulo ...]` → crea `projects/<nombre>/project.yml` con defaults.
- `anega2 run <nombre> [--fase aoi|dem|terreno|agua|sar|lluvia|informe|kml|web|todo] [--si]` → corre con caché por producto;
  antes de descargas grandes muestra qué va a bajar y pide confirmación salvo `--si`.
- `anega2 serve [--puerto 8000] [--proyecto <nombre>]` → servidor estático en la raíz del repo y abre el navegador.
- `anega2 list` · `anega2 doctor` (versiones, WhiteboxTools, red).

## project.yml (defaults en anega2/defaults.yml)
```yaml
nombre: mi-lote
titulo: "Lote en San Andrés de Giles"
kml: lote.kml
crs: auto
buffers: {aoi_m: 500, hidro_m: 10000, lluvia_m: 5000, grilla_m: 2000}
dem: {fuentes: [ign30, ign5, glo30, fabdem], primario: auto}
sar:
  referencia_seca: {desde: 2023-01-15, hasta: 2023-03-31}
  eventos:
    - {id: 2015-08, fecha: 2015-08-10, ventana_d: 12, descr: "Lluvias 9-11 ago 2015"}
lluvia:
  escenarios: [{id: P050_24h, P_mm: 50, dur_h: 24}, ..., {id: P060_2h, P_mm: 60, dur_h: 2}]
  saturado: [P100_24h, P150_24h]
  Ks_mm_h: 10, Ks_sat_mm_h: 2, manning: 0.05, psi_m: 0.17, dtheta: 0.15
```

## Reglas del veredicto (rules.yml, heurísticas documentadas en el informe)
Niveles ordinales BAJO < MEDIO-BAJO < MEDIO < ALTO; cada componente toma el máximo disparado.
- Lluvia local: depresión cerrada en el lote (prof. máx ≥ 0,10 m → MEDIO; ≥ 0,30 → ALTO); cuenca aportante
  (≥ 5 ha → MEDIO; ≥ 50 → ALTO); lámina máx. en el lote con 100 mm/24 h (≥ 5 cm → MEDIO-BAJO; ≥ 10 → MEDIO; ≥ 20 → ALTO);
  % del lote > 5 cm con 100 mm (≥ 50 % → MEDIO).
- Desborde: HAND mínimo del lote (< 0,5 m → ALTO; < 1 → MEDIO; < 2 → MEDIO-BAJO); ocurrencia JRC en el lote
  (> 0 → ALTO); agua Sentinel-1 en el lote en algún evento (≥ 5 % → ALTO); agua S1 en 500 m (≥ 10 % → MEDIO);
  % del buffer 500 m > 20 cm con 150 mm/24 h (≥ 10 % → MEDIO).

## Verificación
- El proyecto `mi-lote` migrado reproduce los números actuales (tabla de terreno, JRC, SAR, escenarios).
- El ejemplo público corre de punta a punta con `anega2 run ejemplo --fase todo --si`.
- El visor muestra ambos proyectos; sin errores de consola.
- Chequeo de fugas antes de publicar; la historia pública no contiene el KML ni resultados del lote privado.

## Fuera de alcance
Servicio web hosteado, calibración hidrológica, países fuera de Argentina (funciona con fuentes globales pero sin soporte).
