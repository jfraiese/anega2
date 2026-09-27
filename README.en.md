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

If you already have the environment set up (GDAL, etc.), `pip install -e .` is enough (there's a `pyproject.toml`).

Tests: `python -m pytest` (65 cases) and `node --test webapp/test/*.test.js` (21 cases; Node ≥ 18 —
pass the glob, some Node versions won't accept a folder there).

## Use

```bash
anega2 init my-parcel --kml my-parcel.kml --titulo "Parcel in ..."
anega2 run my-parcel                     # all phases (asks before large downloads; --si to skip prompts)
anega2 serve                             # opens http://localhost:8000/webapp/?project=my-parcel
```

Phases (`--fase`): `aoi` · `dem` · `terreno` · `agua` · `clima` · `sar` · `lluvia` · `informe` · `ficha` · `kml` · `web`.
Each phase reuses cached products. `clima` takes about 25 minutes the first time per parcel (CHIRPS, one pixel
per day since 1981; cached afterwards, only new days are fetched). `lluvia` runs in parallel (60 grid scenarios
plus the DEM ensemble, `procesos: auto`); in practice, 1-3 hours depending on the CPU. A full project, all cold,
can take half a day; with a warm cache, much less.
The CRS is chosen automatically (POSGAR 2007 Gauss-Krüger zone in Argentina, UTM elsewhere). Buffers,
rain events searched in Sentinel-1, scenarios and soil parameters live in `projects/<name>/project.yml`
(defaults in `anega2/defaults.yml`).

## Outputs (`projects/<name>/out/`)

`README.md` (report in Spanish: key numbers, verdict LOW / MEDIUM-LOW / MEDIUM / HIGH for local rain and for
overflow, limitations, field checks, rules used), `veredicto.json` (the same verdict as JSON — levels per
component, triggering rules with values, report text — read by the viewer), `clima_*.csv/.md` and `clima.json`
(historical rain: ERA5 via Open-Meteo and CHIRPS series, annual maxima, approximate return period per duration
by Gumbel with a 90% bootstrap interval, and the largest storms since 1940 and since 2014 — the latter feed the
automatic radar events), `ficha_<name>.pdf` (8-page A4 landscape brief for an architect or
engineer: summary with verdict and field checklist, regional locator, lot and drainage, contours, height above drainage,
a cross-section of the nearest drainage line across the three DEMs and radar to tell a stream from a swale, simulated
rain with the scenario table, satellite water history), `<name>.kml`, per-phase tables (`*_stats.md/.csv`),
figures (`10_terrain_*`, `20_jrc_*`, `30_sar_*`, `40_rog_*`), clipped GeoTIFFs and vectors.

The viewer (`projects/<name>/web/`, served by `anega2 serve`) opens on the **Summary** view, for a
non-technical client: satellite map with only the parcel and the simulated water (no technical layers), storm
type (3 h downpour · 24 h rainy day · 72 h storm), normal/saturated soil, a rain slider (25-250 mm) and an hour
slider with ▶, a 5/20 cm threshold, a plain-language sentence with the **certainty** (probable / possible /
unlikely — see "How it decides"), and a "Did it ever happen?" card with historical annual maxima and the
largest storms linked to their radar scene. The "Technical detail ›" button leads to the usual tabs (Verdict,
Layers, Terrain, History, Simulation, Figures), with Sentinel-1 scene and rain-scenario selectors and
click-to-read elevation, HAND (± DEM uncertainty), slope and depth values. `web/sim/` (15-200 MB depending on
the project: compressed hourly frames behind the Summary view) is not versioned; it's regenerated with
`anega2 run <name> --fase lluvia web`.

## How it decides

1. **DEM**: downloads IGN MDE-Ar 30 m (and 5 m when available), Copernicus GLO-30 and FABDEM, runs the
   analysis on all of them and picks as primary the one whose derived network best matches OpenStreetMap
   waterways, preferring FABDEM (bare earth) because surface models see the parcel's own tree canopy and roofs.
2. **Terrain** (WhiteboxTools): breach/fill, D8 and D∞, drainage network (0.5 and 2 km²), HAND, TWI, slope,
   closed depressions, contributing catchment, flow path to the stream.
3. **History**: historical rain from ERA5 hourly (Open-Meteo, 1940→) and CHIRPS v2.0 daily (1981→, no
   coverage south of 50°S), with an approximate return period per duration (Gumbel, 90% bootstrap interval);
   the largest storms since 2014 are used to automatically pick which events to look up in Sentinel-1
   (`sar.eventos: auto`; a manual list in `project.yml` still works). Surface water: JRC Global Surface Water
   (Landsat) and Sentinel-1 RTC from Planetary Computer around those events (Lee filter, Otsu with a
   plausibility check or fixed threshold, change vs. a dry reference; "pre" scene = the last one within 12
   days before, "post" = the first pass 0-3 days after, recorded as such when none arrives in time).
4. **Rain**: Landlab `OverlandFlow` with Green-Ampt infiltration on the conditioned DEM, ±5 km domain. A grid
   of 60 scenarios (25-250 mm every 25, 3/24/72 h, normal/saturated soil), run in parallel, with hourly depth
   frames for the viewer. Plus a DEM ensemble at 50/100/150/200 mm in 24 h with the other available DEMs, to
   see how much the result changes with the starting terrain.
5. **Verdict**: explicit rules in `anega2/rules.yml`, printed in the report (and in `veredicto.json`) with the
   triggering values.
6. **Certainty**: per pixel, hour and threshold (5/20 cm), the fraction of the 3×3 neighborhood over the
   threshold, averaged across the ensemble DEMs when available. Classified as probable (≥ 70%) / possible
   (30-70%) / unlikely (5-30%); under 5% isn't drawn. Scenarios without an ensemble show certainty from
   neighborhood alone, on the primary DEM.

## Example

`projects/ejemplo-bajo-giles/`: a 1.4 ha rural low in the Arroyo de Giles floodplain (Buenos Aires), 134 m from
the channel and 0.57-1.4 m above it (HAND). Satellites never saw it flooded; 50 mm does nothing, 100 mm in 24 h
leaves just 9 cm over 8% of the parcel, 150 mm puts up to 44 cm (20 cm or more over 44% of the parcel) and
200 mm, up to 77 cm over almost all of it (88% over 20 cm). Per ERA5, 100 mm in 24 h happens on average every
12 years (every 10 per CHIRPS). Verdict: MEDIUM. See its `out/README.md` (Spanish), `ficha_ejemplo-bajo-giles.pdf`,
and `anega2 serve` (Summary view).

![viewer](docs/visor.jpg)

(The example doesn't include `data/` or the GeoTIFFs: regenerated with `anega2 run ejemplo-bajo-giles`.
`web/sim/` isn't versioned either: regenerated with `anega2 run ejemplo-bajo-giles --fase lluvia web`.)

## Honest limitations

30 m pixel (no ditches, embankments or culverts), uncalibrated, no flood wave from outside the domain,
Sentinel-1 doesn't see under trees and revisits every 6-12 days, approximate return periods (ERA5's 28 km
pixel underestimates convective storms; CHIRPS is 5 km and daily). The verdict thresholds are heuristic:
change them in `rules.yml` if you have local judgment to apply.

## License

Code: MIT. Data sources keep their own licenses (see [SOURCES.md](SOURCES.md)); **FABDEM is CC BY-NC-SA 4.0
(non-commercial)**; Copernicus DEM, Sentinel, JRC and OSM require attribution; ERA5 (via Open-Meteo) is
CC BY 4.0 (Copernicus Climate Change Service); CHIRPS is public domain with citation.
