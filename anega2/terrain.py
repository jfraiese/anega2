"""Fase 1 · análisis de terreno con WhiteboxTools sobre el buffer hidrológico.

Corre el pipeline completo para cada DEM disponible en data_raw/dem_inventory.json (ign30, ign5,
glo30, fabdem), valida cada red de drenaje contra los arroyos de OSM y elige el DEM primario
(menor distancia mediana OSM→red, con preferencia por terreno desnudo si está a ≤ 1,5x del mejor;
o el fijado en p.cfg['dem']['primario']). Los productos del primario van a p.out con prefijo
"terrain_"; los de los otros DEM a p.out/alt_<dem>/.

Por DEM, en data_proc/terrain/<dem>/ (todo en p.crs): dem.tif, dem_fill.tif, dem_breach.tif,
sink_depth.tif (= fill − dem), d8_pntr.tif, d8_facc_m2.tif, dinf_pntr.tif, dinf_sca.tif,
streams_<key>.tif/.geojson, hand_<key>.tif, slope_deg.tif, aspect.tif, twi.tif, hillshade.tif,
watershed_lote*.tif, flowpath_lote.tif, dist_downslope_stream.tif, stats.json, depresiones_aoi.csv,
vectores (red_drenaje_<key>, cuenca_lote, flowpath_lote, depresiones_aoi, hand_le1m, hand_le2m).
"""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio import features
from rasterio.merge import merge
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from scipy import ndimage as ndi
from shapely.geometry import LineString, Point, shape
from shapely.ops import linemerge

from .common import (CRS_WGS84, bounds_wgs84, clip_raster, df_to_md, fetch_osm_waterways, plot_map, rasterize_geom,
                     read_raster, write_gtiff)
from .paletas import HAND_CMAP, HAND_NORM
from .project import Project

MARGIN = 600.0  # m alrededor del buffer hidrológico
DEM_SPECS = {
    "ign30": dict(label="IGN MDE-Ar v2.1 30 m", nodata=-999999.0, vdatum="SRVN16 (IGN)", res=30.0, bare_earth=False),
    "ign5": dict(label="IGN MDE 5 m aerofotogramétrico", nodata=None, vdatum="SRVN16 (IGN)", res=5.0, bare_earth=False),
    "glo30": dict(label="Copernicus DEM GLO-30", nodata=None, vdatum="EGM2008", res=30.0, bare_earth=False),
    "fabdem": dict(label="FABDEM v1.2 (GLO-30 sin árboles/edificios)", nodata=None, vdatum="EGM2008", res=30.0, bare_earth=True),
}
D8_DIRS = {1: "NE", 2: "E", 4: "SE", 8: "S", 16: "SW", 32: "W", 64: "NW", 128: "N"}
D8_OFF = {1: (-1, 1), 2: (0, 1), 4: (1, 1), 8: (1, 0), 16: (1, -1), 32: (0, -1), 64: (-1, -1), 128: (-1, 0)}


def stream_key(thr_km2: float) -> str:
    return f"{thr_km2:g}km2".replace(".", "")


# ------------------------------------------------------------------ helpers
def streams_to_vector(streams_path: Path, d8_path: Path, transform, crs: str) -> gpd.GeoDataFrame:
    """Une cada celda de cauce con su celda aguas abajo (D8). Reemplaza a RasterStreamsToVector de WBT, que falla."""
    s, _ = read_raster(streams_path); d, _ = read_raster(d8_path)
    m = ~np.isnan(s) & (s > 0)
    segs = []
    for r, c in zip(*np.where(m)):
        pv = d[r, c]
        if np.isnan(pv) or int(pv) not in D8_OFF:
            continue
        dr, dc = D8_OFF[int(pv)]
        r2, c2 = r + dr, c + dc
        if 0 <= r2 < m.shape[0] and 0 <= c2 < m.shape[1] and m[r2, c2]:
            x1, y1 = rasterio.transform.xy(transform, r, c); x2, y2 = rasterio.transform.xy(transform, r2, c2)
            segs.append(LineString([(x1, y1), (x2, y2)]))
    if not segs:
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    merged = linemerge(segs)
    geoms = list(merged.geoms) if merged.geom_type == "MultiLineString" else [merged]
    return gpd.GeoDataFrame({"length_m": [g.length for g in geoms]}, geometry=geoms, crs=crs)


def domain_grid(aoi: dict, res: float):
    x0, y0, x1, y1 = aoi["hidro"].bounds
    x0 = math.floor((x0 - MARGIN) / res) * res; y0 = math.floor((y0 - MARGIN) / res) * res
    x1 = math.ceil((x1 + MARGIN) / res) * res; y1 = math.ceil((y1 + MARGIN) / res) * res
    return from_origin(x0, y1, res, res), int((x1 - x0) / res), int((y1 - y0) / res)


def prepare_dem(files: list[Path], nodata, transform, w, h, crs: str, dst_path: Path) -> Path:
    """Mosaico + reproyección bilineal a la grilla común."""
    if dst_path.exists():
        return dst_path
    srcs = [rasterio.open(f) for f in files]
    nd = nodata if nodata is not None else srcs[0].nodata
    if len(srcs) > 1:
        arr, tr = merge(srcs, nodata=nd); arr = arr[0]
    else:
        arr = srcs[0].read(1); tr = srcs[0].transform
    src_crs = srcs[0].crs
    for s in srcs:
        s.close()
    arr = arr.astype("float32")
    if nd is not None:
        arr[arr == nd] = np.nan
    arr[(arr < -100) | (arr > 7000)] = np.nan  # valores imposibles
    dst = np.full((h, w), np.nan, dtype="float32")
    reproject(arr, dst, src_transform=tr, src_crs=src_crs, src_nodata=np.nan,
              dst_transform=transform, dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.bilinear)
    return write_gtiff(dst_path, np.where(np.isnan(dst), -9999.0, dst).astype("float32"), transform, crs, nodata=-9999.0, dtype="float32")


def noise_metrics(dem_path: Path, res: float) -> dict:
    a, _ = read_raster(dem_path)
    ok = ~np.isnan(a)
    sm = ndi.uniform_filter(np.where(ok, a, 0), 5) / np.maximum(ndi.uniform_filter(ok.astype(float), 5), 1e-6)
    resid = np.where(ok, a - sm, np.nan)
    strict = ok.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == dx == 0:
                continue
            nb = np.roll(np.roll(a, dy, 0), dx, 1)
            strict &= (a < nb) | np.isnan(nb)
    area_km2 = ok.sum() * res * res / 1e6
    return dict(rough_std_m=float(np.nanstd(resid)), pits_per_km2=float(strict.sum() / max(area_km2, 1e-9)),
                nodata_pct=float(100 * (~ok).mean()), z_min=float(np.nanmin(a)), z_max=float(np.nanmax(a)))


def vectorize(mask: np.ndarray, transform, crs: str, res: float, min_cells=1) -> gpd.GeoDataFrame:
    shp = [shape(g) for g, v in features.shapes(mask.astype("uint8"), mask=mask, transform=transform) if v == 1]
    gdf = gpd.GeoDataFrame(geometry=shp, crs=crs)
    return gdf[gdf.area >= min_cells * res * res]


def save_vector(gdf: gpd.GeoDataFrame, stem: Path, name_col: str | None = None):
    if gdf is None or len(gdf) == 0:
        return
    gdf.to_file(stem.with_suffix(".geojson"), driver="GeoJSON")
    g84 = gdf.to_crs(CRS_WGS84)
    if name_col and name_col in g84:
        g84 = g84.rename(columns={name_col: "Name"})
    keep = [c for c in ["Name", "Description", "geometry"] if c in g84]
    g84[keep].to_file(stem.with_suffix(".kml"), driver="KML")


# ------------------------------------------------------------------ pipeline por DEM
def run_dem(p: Project, name: str, spec: dict, files: list[Path], aoi: dict, wbt) -> dict | None:
    crs = p.crs; res = spec["res"]
    out = p.data_proc / "terrain" / name
    out.mkdir(parents=True, exist_ok=True)
    tr, w, h = domain_grid(aoi, res)
    dem = prepare_dem(files, spec["nodata"], tr, w, h, crs, out / "dem.tif")
    a_dem, _ = read_raster(dem)
    lot_mask = rasterize_geom(aoi["lote"], a_dem.shape, tr, all_touched=True)
    if not np.isfinite(a_dem[lot_mask]).any():
        print(f"   [{name}] el DEM no tiene datos sobre el lote: se omite"); return None
    wbt.set_working_dir(str(out))
    P = lambda s: str(out / s)  # noqa: E731

    def once(fn, target, *a, **k):
        """Corre una herramienta WBT si falta el producto; verifica que lo haya escrito (reintenta en modo verboso)."""
        if not (out / target).exists():
            fn(*a, **k)
            if not (out / target).exists():
                wbt.set_verbose_mode(True); fn(*a, **k); wbt.set_verbose_mode(False)
                if not (out / target).exists():
                    raise RuntimeError(f"WhiteboxTools no generó {target} ({fn.__name__})")
        return P(target)

    thresholds = sorted(float(t) for t in p.cfg["dem"].get("umbrales_red_km2", [0.5, 2.0]))
    keys = [stream_key(t) for t in thresholds]
    k0, k1 = keys[0], keys[-1]

    # --- corrección hidrológica ---
    fill = once(wbt.fill_depressions, "dem_fill.tif", P("dem.tif"), P("dem_fill.tif"), fix_flats=True)
    breach = once(wbt.breach_depressions_least_cost, "dem_breach.tif", P("dem.tif"), P("dem_breach.tif"),
                  dist=50, max_cost=None, min_dist=True, flat_increment=None, fill=True)
    a_fill, _ = read_raster(fill)
    if not (out / "sink_depth.tif").exists():
        sink = np.where(np.isnan(a_dem), -9999.0, np.maximum(a_fill - a_dem, 0)).astype("float32")
        write_gtiff(out / "sink_depth.tif", sink, tr, crs, nodata=-9999.0)
    # --- flujo ---
    d8 = once(wbt.d8_pointer, "d8_pntr.tif", breach, P("d8_pntr.tif"))
    facc = once(wbt.d8_flow_accumulation, "d8_facc_m2.tif", breach, P("d8_facc_m2.tif"), out_type="catchment area")
    once(wbt.d_inf_pointer, "dinf_pntr.tif", breach, P("dinf_pntr.tif"))
    sca = once(wbt.d_inf_flow_accumulation, "dinf_sca.tif", breach, P("dinf_sca.tif"), out_type="Specific Contributing Area")
    # --- red de drenaje ---
    streams = {}
    for key, thr in zip(keys, thresholds):
        s = once(wbt.extract_streams, f"streams_{key}.tif", facc, P(f"streams_{key}.tif"), threshold=thr * 1e6, zero_background=False)
        if not (out / f"streams_{key}.geojson").exists():
            streams_to_vector(out / f"streams_{key}.tif", out / "d8_pntr.tif", tr, crs).to_file(out / f"streams_{key}.geojson", driver="GeoJSON")
        streams[key] = s
    hand = once(wbt.elevation_above_stream, f"hand_{k0}.tif", breach, streams[k0], P(f"hand_{k0}.tif"))
    # --- derivados ---
    slope = once(wbt.slope, "slope_deg.tif", P("dem.tif"), P("slope_deg.tif"), units="degrees")
    once(wbt.aspect, "aspect.tif", P("dem.tif"), P("aspect.tif"))
    once(wbt.wetness_index, "twi.tif", sca, slope, P("twi.tif"))
    once(wbt.hillshade, "hillshade.tif", P("dem.tif"), P("hillshade.tif"), azimuth=315.0, altitude=35.0, zfactor=8.0)
    once(wbt.downslope_distance_to_stream, "dist_downslope_stream.tif", breach, streams[k0], P("dist_downslope_stream.tif"))

    # --- celda más baja del lote (sobre DEM corregido) y cuenca aportante ---
    a_br, _ = read_raster(breach)
    vals = np.where(lot_mask, a_br, np.nan)
    r0, c0 = np.unravel_index(np.nanargmin(vals), vals.shape)
    x0, y0 = rasterio.transform.xy(tr, r0, c0)
    if not (out / "pour_lote.shp").exists():
        gpd.GeoDataFrame({"id": [1]}, geometry=[Point(x0, y0)], crs=crs).to_file(out / "pour_lote.shp")
    once(wbt.watershed, "watershed_lote.tif", d8, P("pour_lote.shp"), P("watershed_lote.tif"))
    once(wbt.trace_downslope_flowpaths, "flowpath_lote.tif", P("pour_lote.shp"), d8, P("flowpath_lote.tif"), zero_background=True)
    if not (out / "pour_lote_all.shp").exists():
        lot_pts = [Point(*rasterio.transform.xy(tr, r, c)) for r, c in zip(*np.where(lot_mask))]
        gpd.GeoDataFrame({"id": list(range(1, len(lot_pts) + 1))}, geometry=lot_pts, crs=crs).to_file(out / "pour_lote_all.shp")
    once(wbt.watershed, "watershed_lote_all.tif", d8, P("pour_lote_all.shp"), P("watershed_lote_all.tif"))

    # --- estadísticas del lote -------------------------------------------
    a_hand, _ = read_raster(hand); a_slope, _ = read_raster(slope); a_sink, _ = read_raster(out / "sink_depth.tif")
    a_facc, _ = read_raster(facc); a_ws, _ = read_raster(out / "watershed_lote.tif"); a_wsall, _ = read_raster(out / "watershed_lote_all.tif")
    a_d8, _ = read_raster(d8); a_dd, _ = read_raster(out / "dist_downslope_stream.tif"); a_fp, _ = read_raster(out / "flowpath_lote.tif")
    b_aoi = rasterize_geom(aoi["aoi"], a_br.shape, tr)
    lot = lot_mask
    d8_lot = a_d8[lot]; d8_lot = d8_lot[~np.isnan(d8_lot)].astype(int)
    d8_mode = int(np.bincount(d8_lot).argmax()) if len(d8_lot) else 0
    fp_mask = ~np.isnan(a_fp) & (a_fp > 0)
    sv = gpd.read_file(out / f"streams_{k0}.geojson"); sv2 = gpd.read_file(out / f"streams_{k1}.geojson")
    d_euc_0 = float(aoi["lote"].distance(sv.union_all())) if len(sv) else np.nan
    d_euc_1 = float(aoi["lote"].distance(sv2.union_all())) if len(sv2) else np.nan
    s0, _ = read_raster(streams[k0])
    sr, sc = np.where(~np.isnan(s0) & (s0 > 0))
    if len(sr):
        sx, sy = rasterio.transform.xy(tr, sr, sc)
        dd = np.hypot(np.array(sx) - x0, np.array(sy) - y0); k = int(np.argmin(dd))
        z_stream_near = float(a_br[sr[k], sc[k]])
    else:
        z_stream_near = np.nan
    fp_on_stream = fp_mask & ~np.isnan(s0) & (s0 > 0)
    if fp_on_stream.any():
        rr, cc = np.where(fp_on_stream)
        xx, yy = rasterio.transform.xy(tr, rr, cc)
        j = int(np.argmin(np.hypot(np.array(xx) - x0, np.array(yy) - y0)))
        ang = (math.degrees(math.atan2(xx[j] - x0, yy[j] - y0)) + 360) % 360
        comp = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int(((ang + 22.5) % 360) // 45)]
        outlet_dir = f"{comp} ({ang:.0f}°)"
    else:
        outlet_dir = "n/d"
    sink_lot = a_sink[lot]; sink_lot = sink_lot[~np.isnan(sink_lot)]
    dd_lot = a_dd[lot]
    stats = {
        "dem": name, "dem_label": spec["label"], "vdatum": spec["vdatum"], "res_m": res,
        "n_celdas_lote": int(lot.sum()),
        "z_min_lote": float(np.nanmin(a_dem[lot])), "z_max_lote": float(np.nanmax(a_dem[lot])), "z_mean_lote": float(np.nanmean(a_dem[lot])),
        "z_mean_aoi": float(np.nanmean(a_dem[b_aoi])), "z_min_aoi": float(np.nanmin(a_dem[b_aoi])), "z_max_aoi": float(np.nanmax(a_dem[b_aoi])),
        "hand_min_lote": float(np.nanmin(a_hand[lot])), "hand_max_lote": float(np.nanmax(a_hand[lot])), "hand_mean_lote": float(np.nanmean(a_hand[lot])),
        "hand_mean_aoi": float(np.nanmean(a_hand[b_aoi])), "hand_min_aoi": float(np.nanmin(a_hand[b_aoi])),
        "pct_aoi_hand_le1": float(100 * np.nanmean(a_hand[b_aoi] <= 1)), "pct_aoi_hand_le2": float(100 * np.nanmean(a_hand[b_aoi] <= 2)),
        "slope_mean_lote_pct": float(100 * math.tan(math.radians(np.nanmean(a_slope[lot])))),
        "slope_mean_aoi_pct": float(100 * math.tan(math.radians(np.nanmean(a_slope[b_aoi])))),
        "d8_dominante_lote": D8_DIRS.get(d8_mode, str(d8_mode)),
        "direccion_salida_flowpath": outlet_dir,
        "dist_euclid_red_05km2_m": d_euc_0, "dist_euclid_red_2km2_m": d_euc_1,
        "dist_flujo_red_05km2_m": float(np.nanmin(dd_lot)) if np.isfinite(dd_lot).any() else np.nan,
        "z_cauce_mas_cercano": z_stream_near, "salto_lote_min_vs_cauce_m": float(np.nanmin(a_br[lot]) - z_stream_near),
        "lote_intersecta_depresion": bool((sink_lot > 0.0).any()), "sink_depth_max_lote_m": float(sink_lot.max()) if len(sink_lot) else np.nan,
        "facc_max_lote_ha": float(np.nanmax(a_facc[lot]) / 1e4),
        "cuenca_celda_mas_baja_ha": float(np.nansum(a_ws == 1) * res * res / 1e4),
        "cuenca_todo_el_lote_ha": float(np.nansum(~np.isnan(a_wsall)) * res * res / 1e4),
        "pour_x": float(x0), "pour_y": float(y0),
        "red_keys": keys,
    }
    stats.update({f"dem_{k}": v for k, v in noise_metrics(dem, res).items()})

    # --- depresiones dentro del AOI ----------------------------------------
    lab, _ = ndi.label(np.nan_to_num(a_sink) > 0.0)
    rows = []
    aoi_idx = set(np.unique(lab[b_aoi & (lab > 0)]))
    for i in aoi_idx:
        m = lab == i
        rows.append(dict(id=int(i), area_m2=float(m.sum() * res * res), vol_m3=float(np.nansum(a_sink[m]) * res * res),
                         prof_max_m=float(np.nanmax(a_sink[m])), prof_media_m=float(np.nanmean(a_sink[m])), toca_lote=bool((m & lot).any())))
    deps = pd.DataFrame(rows).sort_values("vol_m3", ascending=False) if rows else pd.DataFrame(
        columns=["id", "area_m2", "vol_m3", "prof_max_m", "prof_media_m", "toca_lote"])
    deps.to_csv(out / "depresiones_aoi.csv", index=False, float_format="%.2f")
    for old in (out / "depresiones_500m.csv", out / "depresiones_500m.geojson", out / "depresiones_500m.kml"):
        old.unlink(missing_ok=True)
    if rows:
        gd = vectorize(np.isin(lab, list(aoi_idx)), tr, crs, res)
        gd["Name"] = [f"depresión {i}" for i in range(1, len(gd) + 1)]
        save_vector(gd, out / "depresiones_aoi", "Name")
    stats["n_depresiones_aoi"] = len(rows)
    stats["depresion_aoi_vol_max_m3"] = float(deps["vol_m3"].max()) if rows else 0.0
    stats["depresion_aoi_prof_max_m"] = float(deps["prof_max_m"].max()) if rows else 0.0

    # --- vectores: cuenca, flowpath, HAND<=1/<=2, red ------------------------
    ws = vectorize(a_ws == 1, tr, crs, res); ws["Name"] = f"Cuenca aportante al lote ({stats['cuenca_celda_mas_baja_ha']:.1f} ha)"
    save_vector(ws, out / "cuenca_lote", "Name")
    if fp_mask.any():
        pts = sorted(zip(a_facc[fp_mask], *rasterio.transform.xy(tr, *np.where(fp_mask))))
        if len(pts) > 1:
            fpg = gpd.GeoDataFrame({"Name": ["Camino de flujo desde el lote"]}, geometry=[LineString([(x, y) for _, x, y in pts])], crs=crs)
            save_vector(fpg, out / "flowpath_lote", "Name")
    for thr in (1, 2):
        hm = vectorize(np.nan_to_num(a_hand, nan=99) <= thr, tr, crs, res, min_cells=2)
        hm["Name"] = f"HAND ≤ {thr} m"
        save_vector(hm, out / f"hand_le{thr}m", "Name")
    for key, thr in zip(keys, thresholds):
        s = gpd.read_file(out / f"streams_{key}.geojson")
        s["Name"] = f"Red de drenaje ≥ {thr:g} km²"
        save_vector(s, out / f"red_drenaje_{key}", "Name")
    json.dump(stats, open(out / "stats.json", "w"), indent=1, ensure_ascii=False)
    return stats


def validate_vs_osm(p: Project, name: str, osm: gpd.GeoDataFrame | None, aoi: dict, keys: list[str]) -> dict:
    """Distancia de los arroyos OSM a la red derivada del DEM (muestreo cada 50 m)."""
    out = p.data_proc / "terrain" / name
    res = {}
    if osm is None or len(osm) == 0:
        return res
    osm_in = osm[osm.intersects(aoi["hidro"])]
    pts = [g.interpolate(d) for g in osm_in.geometry for d in np.arange(0, g.length, 50.0)]
    if not pts:
        return res
    for key in keys:
        sv = gpd.read_file(out / f"streams_{key}.geojson")
        if len(sv) == 0:
            res[f"osm_dist_med_{key}_m"] = np.nan; res[f"osm_dist_p90_{key}_m"] = np.nan; continue
        u = sv.union_all()
        d = np.array([pt.distance(u) for pt in pts])
        res[f"osm_dist_med_{key}_m"] = float(np.median(d)); res[f"osm_dist_p90_{key}_m"] = float(np.percentile(d, 90))
        res[f"osm_pct_within_100m_{key}"] = float(100 * np.mean(d <= 100))
    res["osm_n_ways"] = int(len(osm_in)); res["osm_km"] = float(osm_in.length.sum() / 1000)
    return res


# ------------------------------------------------------------------ salidas
def export_outputs(p: Project, name: str, spec: dict, aoi: dict, dest: Path, keys: list[str], is_primary: bool):
    src = p.data_proc / "terrain" / name
    dest.mkdir(parents=True, exist_ok=True)
    aoi_lbl = f"{p.aoi_m:.0f} m"; hidro_lbl = f"{p.hidro_m/1000:g} km"
    k0, k1 = keys[0], keys[-1]
    lab_k0 = k0.replace("05", "0,5").replace("km2", " km²"); lab_k1 = k1.replace("km2", " km²")
    ext = aoi["aoi"].buffer(1000)
    hs, tr = read_raster(src / "hillshade.tif")
    lab = spec["label"]
    layers = {
        "dem": ("dem.tif", "Elevación (m snm)", "terrain", None, None),
        "hand": (f"hand_{k0}.tif", "HAND · altura sobre el drenaje más cercano (m) · sin color: > 5 m", HAND_CMAP, None, None),
        "slope": ("slope_deg.tif", "Pendiente (°)", "magma", 0, 1.5),
        "twi": ("twi.tif", "TWI (índice topográfico de humedad)", "Blues", 5, 15),
        "sink": ("sink_depth.tif", "Profundidad de depresiones cerradas (fill − DEM, m)", "PuBu", 0, 1),
        "facc": ("d8_facc_m2.tif", "Área de aporte D8 (ha, log)", "cividis", None, None),
        "aspect": ("aspect.tif", "Orientación (°)", "twilight", 0, 360),
        "dist": ("dist_downslope_stream.tif", f"Distancia de flujo al drenaje ≥{lab_k0} (m)", "YlOrBr", 0, 2000),
    }
    sv = gpd.read_file(src / f"red_drenaje_{k0}.geojson"); sv2 = gpd.read_file(src / f"red_drenaje_{k1}.geojson")
    osm_path = p.out / "osm_waterways.geojson"
    base_ov = [(sv.geometry, dict(color="deepskyblue", lw=1.2)), (sv2.geometry, dict(color="blue", lw=2))]
    if osm_path.exists():
        base_ov.append((gpd.read_file(osm_path).geometry, dict(color="white", lw=2.5, alpha=0.9)))
    if (src / "cuenca_lote.geojson").exists():
        base_ov.append((gpd.read_file(src / "cuenca_lote.geojson").geometry.boundary, dict(color="lime", lw=1.5, linestyle="--")))
    if (src / "flowpath_lote.geojson").exists():
        base_ov.append((gpd.read_file(src / "flowpath_lote.geojson").geometry, dict(color="magenta", lw=2)))
    sub = f"{lab} · red ≥{lab_k0} (celeste) / ≥{lab_k1} (azul) · arroyos OSM (blanco) · cuenca del lote (verde) · flujo (magenta)"
    for key, (fn, title, cmap, vmin, vmax) in layers.items():
        clip_raster(src / fn, aoi["aoi"], dest / f"terrain_{key}_aoi.tif", all_touched=True)
        a, _ = read_raster(src / fn)
        if key == "facc":
            a = np.log10(np.maximum(a, spec["res"] ** 2) / 1e4); vmin, vmax = -1, 3
        if key == "sink":
            a = np.where(a <= 0, np.nan, a)
        plot_map(a, tr, aoi, f"{title}\n{sub}", dest / f"10_terrain_{key}.png", cmap=cmap, vmin=vmin, vmax=vmax,
                 cbar_label=title.split("(")[-1].rstrip(")"), extent_geom=ext, overlays=base_ov,
                 hillshade=hs if key in ("dem", "hand", "sink") else None,
                 norm=HAND_NORM if key == "hand" else None)
    a, _ = read_raster(src / "dem.tif")
    ov = [(sv.geometry, dict(color="deepskyblue", lw=0.6)), (sv2.geometry, dict(color="blue", lw=1.2))]
    if osm_path.exists():
        ov.insert(0, (gpd.read_file(osm_path).geometry, dict(color="white", lw=2.0, alpha=0.9)))
    if (src / "cuenca_lote.geojson").exists():
        ov.append((gpd.read_file(src / "cuenca_lote.geojson").geometry.boundary, dict(color="lime", lw=1.5)))
    plot_map(a, tr, aoi, f"Elevación y red de drenaje · buffer {hidro_lbl} · {lab}\nOSM arroyos (blanco) · red ≥{lab_k0} (celeste) · ≥{lab_k1} (azul) · cuenca del lote (verde)",
             dest / "10_terrain_overview_hidro.png", cmap="terrain", cbar_label="m snm", extent_geom=aoi["hidro"], overlays=ov, hillshade=hs, figsize=(10, 9))
    a, _ = read_raster(src / f"hand_{k0}.tif")
    plot_map(a, tr, aoi, f"HAND (m) · buffer {hidro_lbl} · {lab}", dest / "10_terrain_hand_hidro.png", cmap=HAND_CMAP, norm=HAND_NORM,
             cbar_label="m", extent_geom=aoi["hidro"], overlays=ov, figsize=(10, 9))
    for v in [f"red_drenaje_{k0}", f"red_drenaje_{k1}", "cuenca_lote", "flowpath_lote", "depresiones_aoi", "hand_le1m", "hand_le2m"]:
        for ext_ in (".geojson", ".kml"):
            if (src / f"{v}{ext_}").exists():
                shutil.copy(src / f"{v}{ext_}", dest / f"terrain_{v}{ext_}")
    if (src / "depresiones_aoi.csv").exists():
        shutil.copy(src / "depresiones_aoi.csv", dest / "terrain_depresiones_aoi.csv")
    # limpiar nombres viejos del proyecto migrado
    for old in list(dest.glob("terrain_*_500m.tif")) + list(dest.glob("terrain_depresiones_500m.*")) + \
            [dest / "10_terrain_overview_10km.png", dest / "10_terrain_hand_10km.png"]:
        old.unlink(missing_ok=True)


# ------------------------------------------------------------------ main
def run(p: Project) -> dict:
    import whitebox
    wbt = whitebox.WhiteboxTools(); wbt.set_verbose_mode(False)
    aoi = p.load_aoi()
    inv_path = p.data_raw / "dem_inventory.json"
    if not inv_path.exists():
        from . import dem as _dem
        _dem.run(p)
    inv = json.loads(inv_path.read_text())
    sources = {k: [Path(f) for f in v if Path(f).exists()] for k, v in inv.get("sources", {}).items()}
    sources = {k: v for k, v in sources.items() if v and k in DEM_SPECS}
    if not sources:
        raise SystemExit("no hay ningún DEM disponible (corré la fase dem)")
    print("DEMs disponibles:", {k: len(v) for k, v in sources.items()})

    # OSM
    osm = None
    try:
        cache = p.data_raw / "osm" / "waterways_hidro_4326.geojson"
        legacy = p.data_raw / "osm" / "waterways_10km_4326.geojson"
        if not cache.exists() and legacy.exists():
            legacy.rename(cache)
        osm = fetch_osm_waterways(bounds_wgs84(aoi["hidro"], p.crs, pad_deg=0.01), cache, p.crs)
        print(f"OSM: {len(osm)} cursos de agua en el bbox ({osm.length.sum()/1000:.1f} km)")
        osm.to_file(p.out / "osm_waterways.geojson", driver="GeoJSON")
        o84 = osm.to_crs(CRS_WGS84); o84["Name"] = o84["name"].fillna("") + " (" + o84["waterway"].fillna("") + ")"
        o84[["Name", "geometry"]].to_file(p.out / "osm_waterways.kml", driver="KML")
        for old in (p.out / "osm_waterways_10km.geojson", p.out / "osm_waterways_10km.kml"):
            old.unlink(missing_ok=True)
    except Exception as e:  # noqa: BLE001
        print("OSM Overpass no disponible:", e)

    results = {}
    order = [k for k in ("ign30", "ign5", "glo30", "fabdem") if k in sources]
    for name in order:
        spec = DEM_SPECS[name]
        print(f"== {spec['label']} ==")
        r = run_dem(p, name, spec, sources[name], aoi, wbt)
        if r is None:
            continue
        r.update(validate_vs_osm(p, name, osm, aoi, r["red_keys"]))
        results[name] = r
        k0 = r["red_keys"][0]
        print(f"   ruido (std residuo 5x5): {r['dem_rough_std_m']:.2f} m · pozos: {r['dem_pits_per_km2']:.1f}/km² · "
              f"dist. mediana OSM→red {k0}: {r.get(f'osm_dist_med_{k0}_m', float('nan')):.0f} m (p90 {r.get(f'osm_dist_p90_{k0}_m', float('nan')):.0f} m)")
    if not results:
        raise SystemExit("ningún DEM cubre el lote")

    # --- elección del DEM primario ------------------------------------------
    k0 = next(iter(results.values()))["red_keys"][0]
    if all(np.isfinite(r.get(f"osm_dist_med_{k0}_m", np.nan)) for r in results.values()):
        score = {n: r[f"osm_dist_med_{k0}_m"] for n, r in results.items()}; crit = "distancia mediana OSM→red (m)"
    else:
        score = {n: r["dem_rough_std_m"] for n, r in results.items()}; crit = "ruido (m)"
    primary = min(score, key=score.get)
    bare = [n for n in results if DEM_SPECS[n].get("bare_earth")]
    if bare and np.isfinite(score[bare[0]]) and score[bare[0]] <= 1.5 * score[primary]:
        primary = bare[0]; crit += " + preferencia por terreno desnudo"
    forced = p.cfg["dem"].get("primario", "auto")
    if isinstance(forced, str) and forced.lower() != "auto":
        if forced in results:
            primary = forced; crit = f"fijado en project.yml ({forced})"
        else:
            print(f"   DEM primario '{forced}' pedido en project.yml no está disponible; se usa {primary}")
    print(f"\nDEM primario: {DEM_SPECS[primary]['label']}  ({crit}: { {k: round(v, 2) for k, v in score.items()} })")
    for name in results:
        dest = p.out if name == primary else p.out / f"alt_{name}"
        export_outputs(p, name, DEM_SPECS[name], aoi, dest, results[name]["red_keys"], name == primary)
    for old in list(p.out.glob("alt_*")):
        if old.is_dir() and old.name[4:] not in results or old.name[4:] == primary:
            shutil.rmtree(old, ignore_errors=True)

    # --- tabla comparativa ---------------------------------------------------
    df = pd.DataFrame({k: {kk: vv for kk, vv in v.items() if kk != "red_keys"} for k, v in results.items()})
    cols = ["dem_label", "vdatum", "res_m", "n_celdas_lote", "z_min_lote", "z_max_lote", "z_mean_lote", "z_min_aoi", "z_max_aoi",
            "hand_min_lote", "hand_max_lote", "hand_mean_lote", "hand_mean_aoi", "pct_aoi_hand_le1", "pct_aoi_hand_le2",
            "slope_mean_lote_pct", "slope_mean_aoi_pct", "d8_dominante_lote", "direccion_salida_flowpath",
            "dist_euclid_red_05km2_m", "dist_euclid_red_2km2_m", "dist_flujo_red_05km2_m", "z_cauce_mas_cercano",
            "salto_lote_min_vs_cauce_m", "lote_intersecta_depresion", "sink_depth_max_lote_m", "n_depresiones_aoi",
            "depresion_aoi_prof_max_m", "facc_max_lote_ha", "cuenca_celda_mas_baja_ha", "cuenca_todo_el_lote_ha",
            "dem_rough_std_m", "dem_pits_per_km2",
            f"osm_dist_med_{k0}_m", f"osm_dist_p90_{k0}_m", f"osm_pct_within_100m_{k0}"]
    cols = [c for c in cols if c in df.index]
    df = df.loc[cols]
    df.columns = [f"{c}{' (primario)' if c == primary else ''}" for c in df.columns]
    df.index.name = "variable"
    df.to_csv(p.out / "terrain_stats.csv")
    md = df.reset_index()
    for c in md.columns[1:]:
        md[c] = md[c].map(lambda v: f"{v:.2f}" if isinstance(v, (float, np.floating)) else str(v))
    (p.out / "terrain_stats.md").write_text(
        f"# Terreno · estadísticas del lote y del buffer {p.aoi_m:.0f} m\n\nDEM primario: **{DEM_SPECS[primary]['label']}**. "
        "Los otros DEM se reportan como control de sensibilidad (carpeta out/alt_*/).\n\n" + df_to_md(md) + "\n")
    json.dump({"primary": primary, "criterio": crit, "score": score, "labels": {k: DEM_SPECS[k]["label"] for k in results},
               "red_keys": results[primary]["red_keys"]}, open(p.out / "terrain_primary.json", "w"), indent=1, ensure_ascii=False)

    r = results[primary]
    p.summary_line(f"FASE 1 (terreno, DEM primario = {DEM_SPECS[primary]['label']})", [
        f"Lote: cota {r['z_min_lote']:.2f}–{r['z_max_lote']:.2f} m (media {r['z_mean_lote']:.2f}); buffer {p.aoi_m:.0f} m: {r['z_min_aoi']:.2f}–{r['z_max_aoi']:.2f} m",
        f"HAND lote: {r['hand_min_lote']:.2f}–{r['hand_max_lote']:.2f} m (media {r['hand_mean_lote']:.2f}); buffer con HAND ≤1 m: {r['pct_aoi_hand_le1']:.1f} %, ≤2 m: {r['pct_aoi_hand_le2']:.1f} %",
        f"Pendiente media lote {r['slope_mean_lote_pct']:.2f} % · D8 dominante {r['d8_dominante_lote']} · salida del flujo hacia {r['direccion_salida_flowpath']}",
        f"Distancia al drenaje ≥{k0.replace('05', '0,5').replace('km2', ' km²')}: {r['dist_euclid_red_05km2_m']:.0f} m (euclídea) / {r['dist_flujo_red_05km2_m']:.0f} m (por flujo); salto vertical lote(min)−cauce: {r['salto_lote_min_vs_cauce_m']:.2f} m",
        f"Depresión cerrada en el lote: {r['lote_intersecta_depresion']} (prof. máx {r['sink_depth_max_lote_m']:.2f} m) · cuenca aportante: {r['cuenca_celda_mas_baja_ha']:.1f} ha (celda más baja) / {r['cuenca_todo_el_lote_ha']:.1f} ha (todo el lote)",
    ])
    return {"primary": primary, "criterio": crit, "score": score, "stats": results}
