# anega2 · does this parcel flood?

Reproducible **rain-flooding risk analysis for any KML polygon in Argentina**: terrain (DEM, drainage
network, HAND, closed depressions, contributing catchment), satellite surface-water history (Landsat
1984-2021 and Sentinel-1 per rain event), rain-on-grid simulation, a rule-based report with a verdict,
a KML for Google Earth and a web viewer. Open data only, **no accounts needed**. *Español: [README.md](README.md).*

> anega2 is a regional, uncalibrated diagnosis at 30 m pixel. It tells you whether a parcel sits on a
> rise, a slope or a low, how much water would have to rise to reach it, whether satellites ever saw it
> flooded and what 100-200 mm of rain would do. **It does not replace a field survey.**

## Install

```bash
git clone <this repo> anega2 && cd anega2
mamba env create -f environment.yml      # creates env "anega2" and installs the package (-e .)
conda activate anega2
anega2 doctor                            # versions, WhiteboxTools binary (downloaded on first use), source reachability
```

## Use

```bash
anega2 init my-parcel --kml my-parcel.kml --titulo "Parcel in ..."
anega2 run my-parcel                     # all phases (asks before large downloads; --si to skip prompts)
anega2 serve                             # opens http://localhost:8000/webapp/?project=my-parcel
```

Phases (`--fase`): `aoi` · `dem` · `terreno` · `agua` · `sar` · `lluvia` · `informe` · `ficha` · `kml` · `web`. Each phase
reuses cached products. A full project takes 30-90 minutes (downloads + the rain simulation).
The CRS is chosen automatically (POSGAR 2007 Gauss-Krüger zone in Argentina, UTM elsewhere). Buffers,
rain events searched in Sentinel-1, scenarios and soil parameters live in `projects/<name>/project.yml`
(defaults in `anega2/defaults.yml`).

## Outputs (`projects/<name>/out/`)

`README.md` (report in Spanish: key numbers, verdict LOW / MEDIUM-LOW / MEDIUM / HIGH for local rain and for
overflow, limitations, field checks, rules used), `ficha_<name>.pdf` (8-page A4 landscape brief for an architect or
engineer: summary with verdict and field checklist, regional locator, lot and drainage, contours, height above drainage,
a cross-section of the nearest drainage line across the three DEMs and radar to tell a stream from a swale, simulated
rain with the scenario table, satellite water history), `<name>.kml`, per-phase tables (`*_stats.md/.csv`),
figures (`10_terrain_*`, `20_jrc_*`, `30_sar_*`, `40_rog_*`), clipped GeoTIFFs and vectors. The viewer
(`webapp/`) shows everything on satellite imagery with Sentinel-1 scene and rain-scenario selectors and
click-to-read values.

## How it decides

1. **DEM**: downloads IGN MDE-Ar 30 m (and 5 m when available), Copernicus GLO-30 and FABDEM, runs the
   analysis on all of them and picks as primary the one whose derived network best matches OpenStreetMap
   waterways, preferring FABDEM (bare earth) because surface models see the parcel's own tree canopy and roofs.
2. **Terrain** (WhiteboxTools): breach/fill, D8 and D∞, drainage network (0.5 and 2 km²), HAND, TWI, slope,
   closed depressions, contributing catchment, flow path to the stream.
3. **History**: JRC Global Surface Water (Landsat) and Sentinel-1 RTC from Planetary Computer around the
   configured events (Lee filter, Otsu or fixed threshold, change vs. a dry reference).
4. **Rain**: Landlab `OverlandFlow` with Green-Ampt infiltration on the conditioned DEM, ±5 km domain,
   50/100/150/200 mm in 24 h and 60 mm in 2 h, plus saturated-soil runs. No local IDF, no return periods.
5. **Verdict**: explicit rules in `anega2/rules.yml`, printed in the report with the triggering values.

## Example

`projects/ejemplo-bajo-giles/`: a 1.4 ha rural low in the Arroyo de Giles floodplain (Buenos Aires), 134 m from
the channel and 0.6-1.4 m above it. Satellites never saw it flooded; 50 mm does nothing and 100 mm leaves 8 cm in
one corner, but 150 mm/24 h puts 43 cm over a third of the parcel and 200 mm, 76 cm over almost all of it.
Verdict: MEDIUM. See its `out/README.md` (Spanish), `ficha_ejemplo-bajo-giles.pdf`, and `anega2 serve`.

![viewer](docs/visor.jpg)

## License

Code: MIT. Data sources keep their own licenses (see [SOURCES.md](SOURCES.md)); **FABDEM is CC BY-NC-SA 4.0
(non-commercial)**; Copernicus DEM, Sentinel, JRC and OSM require attribution.
