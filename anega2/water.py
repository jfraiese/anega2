"""Fase 2 · agua superficial histórica: JRC Global Surface Water v1.4 (1984-2021, Landsat 30 m).

Fuente: https://global-surface-water.appspot.com/download (tiles 10°x10°, WGS84). Acceso por ventana
vía /vsicurl/ (no se baja el tile entero de 40000x40000 px); si el área cruza tiles se mosaican.

Genera (rutas relativas al proyecto):
  data/raw/jrc/<layer>_hidro_4326.tif   ventana del tile original (valores sin tocar)
  data/proc/jrc/<layer>_hidro.tif       reproyectado al CRS del proyecto (30 m, vecino más cercano)
  out/jrc_<layer>_aoi.tif               recorte al buffer AOI
  out/20_jrc_*.png                      PNG con paleta JRC y lote superpuesto
  out/jrc_stats.csv / .md               % píxeles con occurrence > 0 / >10 / >50 (lote, AOI, hidro)
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.merge import merge
from rasterio.warp import Resampling, calculate_default_transform, reproject
from rasterio.windows import from_bounds

from .common import CRS_WGS84, bounds_wgs84, clip_raster, df_to_md, plot_map, rasterize_geom, write_gtiff
from .project import Project

BASE = "https://storage.googleapis.com/global-surface-water/downloads2021"
LAYERS = ["occurrence", "recurrence", "extent", "seasonality"]  # extent = max_extent
NODATA = 255


def tile_names(minx, miny, maxx, maxy) -> list[str]:
    """Tiles JRC de 10° que cubren el bbox. Nombre = esquina superior izquierda, p.ej. 60W_30S."""
    names = set()
    for lon in range(int(math.floor(minx / 10) * 10), int(math.ceil(maxx / 10) * 10), 10):
        for lat_top in range(int(math.ceil(miny / 10) * 10), int(math.ceil(maxy / 10) * 10) + 10, 10):
            lo = f"{abs(lon)}{'W' if lon < 0 else 'E'}"
            la = f"{abs(lat_top)}{'S' if lat_top < 0 else 'N'}"
            names.add(f"{lo}_{la}")
    return sorted(names)


def fetch_window(layer: str, tiles: list[str], bbox4326, dst: Path) -> Path:
    urls = [f"/vsicurl/{BASE}/{layer}/{layer}_{t}v1_4_2021.tif" for t in tiles]
    srcs = [rasterio.open(u) for u in urls]
    try:
        if len(srcs) == 1:
            src = srcs[0]
            win = from_bounds(*bbox4326, transform=src.transform).round_offsets().round_lengths()
            arr = src.read(1, window=win); tr = src.window_transform(win)
        else:
            arr, tr = merge(srcs, bounds=bbox4326, nodata=NODATA); arr = arr[0]
        prof = srcs[0].profile.copy()
        prof.update(height=arr.shape[0], width=arr.shape[1], transform=tr, compress="deflate", tiled=False, driver="GTiff")
        prof.pop("blockxsize", None); prof.pop("blockysize", None)
        with rasterio.open(dst, "w", **prof) as d:
            d.write(arr, 1)
            try:
                d.write_colormap(1, srcs[0].colormap(1))
            except Exception:  # noqa: BLE001
                pass
    finally:
        for s in srcs:
            s.close()
    return dst


def reproject_to_work(src_path: Path, dst_path: Path, crs: str, res=30.0) -> Path:
    with rasterio.open(src_path) as src:
        tr, w, h = calculate_default_transform(src.crs, crs, src.width, src.height, *src.bounds, resolution=res)
        out = np.full((h, w), NODATA, dtype="uint8")
        reproject(src.read(1), out, src_transform=src.transform, src_crs=src.crs, src_nodata=NODATA,
                  dst_transform=tr, dst_crs=crs, dst_nodata=NODATA, resampling=Resampling.nearest)
    return write_gtiff(dst_path, out, tr, crs, nodata=NODATA, dtype="uint8")


def stats_for(path: Path, geom, all_touched: bool) -> dict:
    with rasterio.open(path) as src:
        arr = src.read(1); tr = src.transform
    m = rasterize_geom(geom, arr.shape, tr, all_touched=all_touched)
    valid = m & (arr != NODATA)
    n = int(valid.sum()); vals = arr[valid]
    return {"n_pix": n, "occ>0 %": 100 * float((vals > 0).mean()) if n else np.nan,
            "occ>10 %": 100 * float((vals > 10).mean()) if n else np.nan,
            "occ>50 %": 100 * float((vals > 50).mean()) if n else np.nan,
            "occ max": int(vals.max()) if n else np.nan}


def run(p: Project) -> dict:
    aoi = p.load_aoi()
    crs = p.crs
    aoi_lab = f"{p.aoi_m:.0f} m"; hidro_lab = f"{p.hidro_m / 1000:.0f} km"
    RAW = p.data_raw / "jrc"; PROC = p.data_proc / "jrc"
    RAW.mkdir(parents=True, exist_ok=True); PROC.mkdir(parents=True, exist_ok=True)
    bbox = bounds_wgs84(aoi["hidro"], crs, pad_deg=0.002)
    tiles = tile_names(*bbox)
    print(f"Tiles JRC: {tiles}")

    paths = {}
    for layer in LAYERS:
        raw = RAW / f"{layer}_hidro_4326.tif"
        if not raw.exists():
            print(f"  bajando ventana {layer} de {tiles} ...")
            fetch_window(layer, tiles, bbox, raw)
        proc = reproject_to_work(raw, PROC / f"{layer}_hidro.tif", crs)
        clip_raster(proc, aoi["aoi"], p.out / f"jrc_{layer}_aoi.tif", all_touched=True, nodata=NODATA)
        paths[layer] = proc

    # --- estadísticas (occurrence) -----------------------------------------
    occ = paths["occurrence"]
    rows = []
    for name, geom, at in [("lote (píxeles tocados)", aoi["lote"], True),
                           (f"buffer {aoi_lab}", aoi["aoi"], False),
                           (f"buffer {hidro_lab}", aoi["hidro"], False)]:
        r = stats_for(occ, geom, at); r["zona"] = name; rows.append(r)
    df = pd.DataFrame(rows)[["zona", "n_pix", "occ>0 %", "occ>10 %", "occ>50 %", "occ max"]]
    df.to_csv(p.out / "jrc_stats.csv", index=False, float_format="%.2f")

    with rasterio.open(occ) as src:
        arr = src.read(1); tr = src.transform
    extra = {}
    from shapely.geometry import MultiPoint
    for thr in (1, 10, 50):
        rr, cc = np.where((arr != NODATA) & (arr >= thr))
        if len(rr):
            xs, ys = rasterio.transform.xy(tr, rr, cc)
            extra[thr] = float(aoi["lote"].distance(MultiPoint(list(zip(xs, ys)))))
        else:
            extra[thr] = np.nan
    (p.out / "jrc_stats.md").write_text(
        "# JRC Global Surface Water v1.4 (1984-2021) · occurrence\n\n" + df_to_md(df)
        + f"\n\nPíxeles de 30 m. 'lote' usa all_touched (un lote chico toca pocos píxeles).\n"
        + "\nDistancia del lote al píxel más cercano (centro) con occurrence ≥ 1 / 10 / 50 %: "
          f"{extra[1]:.0f} / {extra[10]:.0f} / {extra[50]:.0f} m (dentro del buffer de {hidro_lab}).\n")

    # --- PNGs ---------------------------------------------------------------
    from matplotlib.colors import LinearSegmentedColormap
    occ_cmap = LinearSegmentedColormap.from_list("jrc_occ", ["#ffffff", "#ff0000", "#8b00ff", "#0000ff"])
    ext_aoi = aoi["aoi"].buffer(3 * p.aoi_m)
    for layer in LAYERS:
        with rasterio.open(paths[layer]) as src:
            a = src.read(1).astype("float32"); tr = src.transform
        a[a == NODATA] = np.nan
        a = np.where(a == 0, np.nan, a)
        if layer == "occurrence":
            plot_map(a, tr, aoi, "JRC GSW v1.4 · Water occurrence 1984-2021 (%)", p.out / "20_jrc_occurrence.png",
                     cmap=occ_cmap, vmin=0, vmax=100, cbar_label="occurrence (%)", extent_geom=ext_aoi)
            plot_map(a, tr, aoi, f"JRC GSW v1.4 · Water occurrence 1984-2021 (%) · {hidro_lab}",
                     p.out / "20_jrc_occurrence_hidro.png", cmap=occ_cmap, vmin=0, vmax=100, cbar_label="occurrence (%)",
                     extent_geom=aoi["hidro"])
        elif layer == "recurrence":
            plot_map(a, tr, aoi, "JRC GSW v1.4 · Recurrence (% de años con agua)", p.out / "20_jrc_recurrence.png",
                     cmap="YlGnBu", vmin=0, vmax=100, cbar_label="recurrence (%)", extent_geom=ext_aoi)
        elif layer == "extent":
            plot_map(a, tr, aoi, "JRC GSW v1.4 · Máxima extensión de agua 1984-2021", p.out / "20_jrc_max_extent.png",
                     discrete_labels={1: ("agua alguna vez", "#1f4fd8")}, extent_geom=ext_aoi)
        elif layer == "seasonality":
            plot_map(a, tr, aoi, "JRC GSW v1.4 · Seasonality 2021 (meses con agua)", p.out / "20_jrc_seasonality.png",
                     cmap="Blues", vmin=1, vmax=12, cbar_label="meses/año", extent_geom=ext_aoi)

    lines = []
    for _, r in df.iterrows():
        lines.append(f"{r['zona']}: {r['n_pix']} px · >0 %: {r['occ>0 %']:.1f} · >10 %: {r['occ>10 %']:.1f} · "
                     f">50 %: {r['occ>50 %']:.1f} · máx {r['occ max']}")
    lines.append(f"Distancia lote → agua detectada (≥1/≥10/≥50 %): {extra[1]:.0f} / {extra[10]:.0f} / {extra[50]:.0f} m")
    lines.append(f"Fuente: tiles {tiles}, lectura por ventana (bbox {np.round(bbox, 3).tolist()})")
    p.summary_line("FASE 2 (JRC GSW v1.4, occurrence)", lines)
    return dict(stats=df.to_dict("records"), distancias_m=extra, tiles=tiles)
