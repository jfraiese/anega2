# projects/

Cada subcarpeta es un proyecto anega2:

```
projects/<nombre>/
  project.yml        configuración (lo que no esté acá toma anega2/defaults.yml)
  lote.kml           polígono del lote (Google Earth, un solo polígono)
  data/raw/          descargas sin tocar (DEMs, JRC, Sentinel-1, OSM)      — no versionado
  data/proc/         productos intermedios por fase                          — no versionado
  out/               informe (README.md), KML, tablas, figuras, GeoTIFF recortados
  web/               datos del visor (anega2 serve)
```

Git ignora todo `projects/*` salvo los ejemplos públicos (`projects/ejemplo-*/`, sin su `data/`).
Creá el tuyo con `anega2 init <nombre> --kml <archivo.kml>`.
