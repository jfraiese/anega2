"""Datos de la vista «Resumen» del visor: cuadros horarios reproyectados a EPSG:3857, certeza por píxel y
lote -> projects/<n>/web/sim/{<id>.bin.gz, <id>_cert.bin.gz, index.json}.

Cuadros: data/proc/rog/<id>_frames.npz (DEM primario) y data/proc/rog/ens/<id>__<dem>_frames.npz (ensamble).
Certeza (umbral u): media sobre los DEM disponibles de la fracción de la ventana 3×3 con lámina > u; uint8 0-100.
"""
from __future__ import annotations

import gzip
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio import features
from rasterio.warp import Resampling, reproject, transform_bounds
from scipy.ndimage import uniform_filter

from .common import CRS_WGS84, json_limpio
from .project import Project
from .rog import load_dem_window, scenario_specs

EPSG3857 = "EPSG:3857"
UMBRALES = [5, 20]


def grilla_3857(tr, crs, shape, lat: float) -> dict:
    rows, cols = shape
    b = transform_bounds(crs, EPSG3857, *rasterio.transform.array_bounds(rows, cols, tr))
    res = abs(tr.a) / math.cos(math.radians(lat))
    nc, nr = int(math.ceil((b[2] - b[0]) / res)), int(math.ceil((b[3] - b[1]) / res))
    t = Affine(res, 0, b[0], 0, -res, b[3])
    bb = (b[0], b[3] - nr * res, b[0] + nc * res, b[3])
    w, s, e, n = transform_bounds(EPSG3857, CRS_WGS84, *bb)
    return dict(transform=list(t)[:6], cols=nc, rows=nr, bounds_3857=list(bb), bounds_wgs84=[[s, w], [n, e]], res_m=res)


def a_3857(frames: np.ndarray, tr, crs, g: dict) -> np.ndarray:
    # out ya viene en cero; con dst_nodata=0 GDAL desplaza los 0 legítimos del origen a 1 para no
    # confundirlos con relleno (avoid being treated as NoData), así que se deja sin nodata destino:
    # las celdas fuera del footprint reproyectado quedan en 0 porque nunca se tocan (out ya está en 0).
    out = np.zeros((frames.shape[0], g["rows"], g["cols"]), np.uint8)
    for i in range(frames.shape[0]):
        reproject(frames[i], out[i], src_transform=tr, src_crs=crs, dst_transform=Affine(*g["transform"]), dst_crs=EPSG3857,
                  resampling=Resampling.nearest, src_nodata=None, dst_nodata=None)
    return out


def _ajustar(a: np.ndarray, shape) -> np.ndarray:
    out = np.zeros(shape, a.dtype); t, r, c = (min(x, y) for x, y in zip(a.shape, shape))
    out[:t, :r, :c] = a[:t, :r, :c]; return out


def certeza(frames_por_dem: list, umbral_cm: int) -> np.ndarray:
    shape = frames_por_dem[0].shape
    acc = np.zeros(shape, float)
    for f in frames_por_dem:
        acc += uniform_filter((_ajustar(f, shape) > umbral_cm).astype(float), size=(1, 3, 3), mode="constant")
    return np.round(100 * acc / len(frames_por_dem)).astype(np.uint8)


def lote_idx(lote_geom, crs, g: dict) -> list[int]:
    import geopandas as gpd
    geom = gpd.GeoSeries([lote_geom], crs=crs).to_crs(EPSG3857).iloc[0]
    m = features.rasterize([(geom, 1)], out_shape=(g["rows"], g["cols"]), transform=Affine(*g["transform"]), all_touched=True).astype(bool)
    return [int(i) for i in np.flatnonzero(m)]


def escribir_gz(path: Path, a: np.ndarray) -> None:
    path.write_bytes(gzip.compress(np.ascontiguousarray(a, np.uint8).tobytes(), compresslevel=6))


def run(p: Project) -> dict:
    rogd = p.data_proc / "rog"; out = p.web / "sim"; out.mkdir(parents=True, exist_ok=True)
    prim = json.load(open(p.out / "terrain_primary.json"))["primary"]
    aoi = p.load_aoi(); _, tr = load_dem_window(p, prim, aoi)
    lat = p.lot_centroid_wgs84()[1]
    specs = [s for s in scenario_specs(p.cfg["lluvia"]) if (rogd / f"{s['id']}_frames.npz").exists()]
    if not specs:
        print("  [aviso] no hay cuadros horarios (correr la fase lluvia): la vista Resumen no tendrá simulación"); return {}
    f0 = np.load(rogd / f"{specs[0]['id']}_frames.npz")["h_cm"]
    g = grilla_3857(tr, p.crs, f0.shape[1:], lat)
    ens = json.load(open(p.out / "rog_ensamble.json")) if (p.out / "rog_ensamble.json").exists() else {"dems": [], "ids": []}
    idx = dict(grid={k: g[k] for k in ("transform", "cols", "rows", "bounds_wgs84", "res_m")}, lote_idx=lote_idx(aoi["lote"], p.crs, g),
               umbrales_cm=UMBRALES, duraciones=sorted({s["dur_h"] for s in specs}), P_mm=sorted({s["P_mm"] for s in specs}),
               suelos=sorted({s["suelo"] for s in specs}), escenarios={})
    for s in specs:
        z = np.load(rogd / f"{s['id']}_frames.npz")
        fr = a_3857(z["h_cm"], tr, p.crs, g)
        por_dem = [fr]; dems = [prim]
        for dem in (ens["dems"] if s["id"] in ens["ids"] else []):
            q = rogd / "ens" / f"{s['id']}__{dem}_frames.npz"
            if q.exists():
                por_dem.append(a_3857(np.load(q)["h_cm"], tr, p.crs, g)); dems.append(dem)
        escribir_gz(out / f"{s['id']}.bin.gz", fr)
        escribir_gz(out / f"{s['id']}_cert.bin.gz", np.stack([certeza(por_dem, u) for u in UMBRALES]))
        meta_p = rogd / f"{s['id']}_meta.json"
        meta = json.load(open(meta_p)) if meta_p.exists() else {}
        horas = int(fr.shape[0])
        esc = dict(P_mm=s["P_mm"], dur_h=s["dur_h"], suelo=s["suelo"], horas=horas,
                   lluvia_acum_mm=[round(float(v), 1) for v in z["lluvia_acum_mm"]], ensamble=dems,
                   cortado=bool(meta.get("cortado", False)),
                   url=f"sim/{s['id']}.bin.gz", cert_url=f"sim/{s['id']}_cert.bin.gz")
        hmax_cm, pct5, pct20 = meta.get("hmax_lote_cm"), meta.get("pct_lote_gt5cm"), meta.get("pct_lote_gt20cm")
        # estadísticas del lote en la grilla nativa (30 m): la reproyección a 3857 con vecino más cercano
        # puede perder la celda de borde con el pico (ver ruling); si falta algo en el meta, se omite "lote".
        if hmax_cm is not None and pct5 is not None and pct20 is not None and len(hmax_cm) == horas and len(pct5) == horas and len(pct20) == horas:
            esc["lote"] = dict(hmax_cm=hmax_cm, pct5=pct5, pct20=pct20)
        idx["escenarios"][s["id"]] = esc
    cl = p.out / "clima.json"
    idx["clima"] = json.load(open(cl)) if cl.exists() else {"disponible": False}
    json.dump(json_limpio(idx), open(out / "index.json", "w"), ensure_ascii=False, allow_nan=False)
    mb = sum(q.stat().st_size for q in out.glob("*")) / 1e6
    print(f"  vista Resumen: {len(specs)} escenarios, grilla {g['cols']}×{g['rows']} (3857, {g['res_m']:.1f} m), {mb:.0f} MB en {out}")
    return dict(escenarios=len(specs), mb=mb)
