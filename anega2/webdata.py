"""Fase web · datos del visor (webapp/) para un proyecto -> projects/<nombre>/web/.

Genera layers.json (manifiesto), geo/*.geojson (WGS84), img/*.png (rasters RGBA en Web Mercator con
nodata transparente), stats.json (tablas, hietogramas, veredicto), grid.json (grilla de valores en
±buffers.grilla_m del lote para el click), figures/ + figures.json, y actualiza projects/index.json.
Las URLs del manifiesto son relativas a la carpeta web del proyecto.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio
import yaml
from matplotlib import colors
from PIL import Image
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds
from rasterio.windows import from_bounds

from .common import CRS_WGS84
from .project import PROJECTS_DIR, Project
from .rog import ficha_ids, scenario_specs

EPSG3857 = "EPSG:3857"
JRC_CMAP = colors.LinearSegmentedColormap.from_list("jrc", ["#ffffff", "#ff0000", "#8b00ff", "#0000ff"])


def _first(*paths):
    return next((q for q in paths if q is not None and Path(q).exists()), None)


def _glob1(d: Path, pattern: str):
    m = sorted(d.glob(pattern)) if d.exists() else []
    return m[0] if m else None


# ---------------------------------------------------------------- rasters
def read_window(path: Path, geom=None):
    with rasterio.open(path) as s:
        if geom is None:
            arr = s.read(1); tr = s.transform
        else:
            win = from_bounds(*geom.bounds, transform=s.transform).round_offsets().round_lengths()
            arr = s.read(1, window=win); tr = s.window_transform(win)
        nd = s.nodata; crs = s.crs
    a = arr.astype("float64")
    if nd is not None:
        a[a == nd] = np.nan
    return a, tr, crs


def to_3857(a, tr, crs, categorical=False):
    h, w = a.shape
    b = rasterio.transform.array_bounds(h, w, tr)
    dtr, dw, dh = calculate_default_transform(crs, EPSG3857, w, h, *b)
    out = np.full((dh, dw), np.nan)
    reproject(a, out, src_transform=tr, src_crs=crs, src_nodata=np.nan, dst_transform=dtr, dst_crs=EPSG3857,
              dst_nodata=np.nan, resampling=Resampling.nearest if categorical else Resampling.bilinear)
    bb = rasterio.transform.array_bounds(dh, dw, dtr)
    ll = transform_bounds(EPSG3857, CRS_WGS84, *bb)
    return out, [[ll[1], ll[0]], [ll[3], ll[2]]]


class Builder:
    def __init__(self, p: Project):
        self.p = p; self.web = p.web
        for d in ("geo", "img", "figures"):
            (self.web / d).mkdir(parents=True, exist_ok=True)
        self.layers = []; self.warnings = []

    def warn(self, msg):
        self.warnings.append(msg); print("  [aviso]", msg)

    def raster(self, lid, title, group, src, cmap=None, vmin=None, vmax=None, unit="", geom=None, mask_below=None,
               transform_fn=None, categorical=None, visible=False, description="", subgroup=None):
        if src is None or not Path(src).exists():
            self.warn(f"falta el raster de la capa '{lid}'"); return None
        a, tr, crs = read_window(src, geom)
        if transform_fn is not None:
            a = transform_fn(a)
        if mask_below is not None:
            a[a <= mask_below] = np.nan
        if vmin is None or vmax is None:
            ok = a[np.isfinite(a)]
            if len(ok):
                lo, hi = np.percentile(ok, [2, 98]); vmin = float(np.floor(lo)) if vmin is None else vmin; vmax = float(np.ceil(hi)) if vmax is None else vmax
            else:
                vmin, vmax = 0.0, 1.0
        a3, bounds = to_3857(a, tr, crs, categorical=categorical is not None)
        if categorical:
            rgba = np.zeros(a3.shape + (4,), dtype=np.uint8)
            for v, (lab, col) in categorical.items():
                m = np.isfinite(a3) & (np.round(a3) == v)
                rgba[m] = (np.array(colors.to_rgba(col)) * 255).astype(np.uint8)
            legend = dict(type="classes", classes=[dict(value=v, label=l, color=c) for v, (l, c) in categorical.items()])
        else:
            cm_ = matplotlib.colormaps[cmap] if isinstance(cmap, str) else cmap
            norm = colors.Normalize(vmin, vmax, clip=True)
            rgba = (cm_(norm(np.nan_to_num(a3, nan=vmin))) * 255).astype(np.uint8)
            rgba[~np.isfinite(a3), 3] = 0
            legend = dict(type="gradient", vmin=vmin, vmax=vmax, unit=unit, stops=[colors.to_hex(cm_(x)) for x in np.linspace(0, 1, 9)])
        fn = f"img/{lid}.png"
        Image.fromarray(rgba, "RGBA").save(self.web / fn, optimize=True)
        d = dict(id=lid, title=title, group=group, subgroup=subgroup, type="image", url=fn, bounds=bounds,
                 legend=legend, visible=visible, description=description)
        self.layers.append(d); return d

    def vector(self, lid, title, group, src, style, visible=False, description="", gdf=None, simplify=None):
        if gdf is None:
            if src is None or not Path(src).exists():
                self.warn(f"falta el vector de la capa '{lid}'"); return None
            gdf = gpd.read_file(src)
        g = gdf
        if simplify:
            g = g.copy(); g["geometry"] = g.geometry.simplify(simplify)
        g = g.to_crs(CRS_WGS84)
        keep = [c for c in g.columns if c in ("Name", "name", "waterway", "length_m", "geometry", "id", "area_m2", "vol_m3", "prof_max_m")]
        g[keep].to_file(self.web / f"geo/{lid}.geojson", driver="GeoJSON")
        d = dict(id=lid, title=title, group=group, type="geojson", url=f"geo/{lid}.geojson", style=style,
                 visible=visible, description=description, n=int(len(g)))
        self.layers.append(d); return d


def _jrc_extra(md: Path) -> str:
    if not md.exists():
        return ""
    m = re.search(r"Distancia del lote.*", md.read_text())
    return m.group(0) if m else ""


def _csv_rows(path: Path | None):
    if path is None or not Path(path).exists():
        return dict(columns=[], rows=[])
    d = pd.read_csv(path)
    return dict(columns=list(d.columns), rows=[[None if (isinstance(v, float) and np.isnan(v)) else v for v in r] for r in d.itertuples(index=False)])


def update_index() -> list:
    """projects/index.json: proyectos con datos del visor."""
    rows = []
    for lj in sorted(PROJECTS_DIR.glob("*/web/layers.json")):
        name = lj.parent.parent.name
        try:
            m = json.load(open(lj)); titulo = m.get("titulo") or name
        except Exception:  # noqa: BLE001
            titulo = name
            yml = lj.parent.parent / "project.yml"
            if yml.exists():
                titulo = (yaml.safe_load(yml.read_text()) or {}).get("titulo") or name
        rows.append(dict(nombre=name, titulo=titulo, actualizado=_dt.datetime.fromtimestamp(lj.stat().st_mtime).isoformat(timespec="seconds")))
    PROJECTS_DIR.mkdir(exist_ok=True)
    json.dump(rows, open(PROJECTS_DIR / "index.json", "w"), ensure_ascii=False, indent=1)
    return rows


def _vista_resumen(p: Project, B: Builder) -> None:
    """Cuadros horarios 3857 + certeza (vista Resumen del visor). No debe abortar la fase web: un fallo
    (falta la fase lluvia, DEM incompatible, etc.) se registra como aviso y el resto de la fase sigue."""
    from . import websim
    try:
        websim.run(p)
    except Exception as e:  # noqa: BLE001
        B.warn(f"vista Resumen no generada: {e}")


def run(p: Project) -> dict:
    aoi = p.load_aoi(); out = p.out; proc = p.data_proc; web = p.web
    crs = p.crs; aoi_m = p.aoi_m; hidro_m = p.hidro_m
    aoi_lab = f"{aoi_m:.0f} m"; hidro_lab = f"{hidro_m/1000:g} km"
    prim_path = out / "terrain_primary.json"
    primary = json.load(open(prim_path))["primary"] if prim_path.exists() else None
    T = proc / "terrain" / primary if primary else None
    lote = aoi["lote"]; c = lote.centroid
    grilla_m = float(p.buffers.get("grilla_m", 2000)); ext3 = lote.buffer(3000).envelope; extg = lote.buffer(grilla_m).envelope
    B = Builder(p)
    if primary is None:
        B.warn("falta out/terrain_primary.json (correr la fase terreno); se generan sólo las capas de referencia")

    # --- Referencia (vectores) ---
    B.vector("lote", "Lote", "Referencia", None, dict(color="#ff0000", weight=3, fillOpacity=0.05), True,
             gdf=gpd.GeoDataFrame({"Name": ["Lote"]}, geometry=[lote], crs=crs))
    B.vector("buffer_aoi", f"Buffer {aoi_lab}", "Referencia", None, dict(color="#ff9900", weight=2, fill=False, dashArray="6 4"), True,
             gdf=gpd.GeoDataFrame({"Name": [f"Buffer {aoi_lab}"]}, geometry=[aoi["aoi"]], crs=crs))
    B.vector("buffer_hidro", f"Buffer {hidro_lab}", "Referencia", None, dict(color="#3388ff", weight=1.5, fill=False, dashArray="8 6"), False,
             gdf=gpd.GeoDataFrame({"Name": [f"Buffer {hidro_lab}"]}, geometry=[aoi["hidro"]], crs=crs))
    osm = _first(out / "osm_waterways.geojson", out / "osm_waterways_10km.geojson")
    if osm:
        g = gpd.read_file(osm); g["Name"] = g["name"].fillna("sin nombre").astype(str) + " (" + g["waterway"].fillna("").astype(str) + ")"
        B.vector("osm", "Arroyos (OpenStreetMap)", "Referencia", None, dict(color="#00e5ff", weight=3), True, gdf=g,
                 description="Cursos de agua mapeados en OSM (river/stream/canal/drain/ditch).")
    else:
        B.warn("falta out/osm_waterways.geojson")
    reds = sorted(out.glob("terrain_red_drenaje_*.geojson"))
    for i, r in enumerate(sorted(reds, key=lambda q: float(q.stem.split("_")[-1].replace("km2", "").replace("05", "0.5")))):
        thr = r.stem.split("_")[-1].replace("km2", "").replace("05", "0,5")
        big = i == len(reds) - 1
        B.vector(f"red_{r.stem.split('_')[-1]}", f"Red de drenaje ≥ {thr} km² (DEM)", "Referencia", r,
                 dict(color="#0033ff" if big else "#66ccff", weight=2.5 if big else 1.5), big)
    B.vector("cuenca", "Cuenca aportante al lote", "Referencia", out / "terrain_cuenca_lote.geojson", dict(color="#00ff00", weight=2, fillOpacity=0.15), True)
    if (out / "terrain_flowpath_lote.geojson").exists():
        B.vector("flowpath", "Camino de flujo desde el lote", "Referencia", out / "terrain_flowpath_lote.geojson", dict(color="#ff00ff", weight=3), True)
    dep = _first(out / "terrain_depresiones_aoi.geojson", out / "terrain_depresiones_500m.geojson")
    if dep:
        B.vector("depresiones", f"Depresiones cerradas ({aoi_lab})", "Referencia", dep, dict(color="#9900cc", weight=1, fillOpacity=0.45), False)
    for thr in (1, 2):
        q = out / f"terrain_hand_le{thr}m.geojson"
        if q.exists():
            g = gpd.read_file(q); g = g[g.intersects(ext3)]
            B.vector(f"hand_le{thr}", f"HAND ≤ {thr} m (±3 km)", "Referencia", None,
                     dict(color="#cc0000" if thr == 1 else "#ff9933", weight=1, fillOpacity=0.35), False, gdf=g)

    # --- Terreno ---
    sl2pct = lambda a: 100 * np.tan(np.radians(a))  # noqa: E731
    res_m = None
    if T is not None:
        with rasterio.open(T / "dem.tif") as s:
            res_m = abs(s.transform.a)
        B.raster("dem", "Elevación (m snm)", "Terreno", T / "dem.tif", "terrain", None, None, "m", description=f"DEM primario {primary} ({res_m:.0f} m).")
        hand_src = _first(T / "hand_05km2.tif", _glob1(T, "hand_*.tif"))
        B.raster("hand", "HAND · altura sobre el drenaje (m)", "Terreno", hand_src, "RdYlBu", 0, 6, "m", visible=True,
                 description="Altura sobre la celda de drenaje a la que escurre cada celda. Rojo = bajo.")
        B.raster("slope", "Pendiente (%)", "Terreno", T / "slope_deg.tif", "magma", 0, 3, "%", transform_fn=sl2pct)
        B.raster("twi", "TWI · índice de humedad", "Terreno", T / "twi.tif", "Blues", 5, 15, "")
        B.raster("sink", "Depresiones cerradas · profundidad (m)", "Terreno", T / "sink_depth.tif", "PuBu", 0, 0.5, "m", mask_below=0.0)
        B.raster("facc", "Área de aporte (log10 ha)", "Terreno", T / "d8_facc_m2.tif", "cividis", -1, 3, "log10 ha",
                 transform_fn=lambda a: np.log10(np.maximum(a, 1.0) / 1e4))
        B.raster("dist", "Distancia de flujo al drenaje (m)", "Terreno", T / "dist_downslope_stream.tif", "YlOrBr", 0, 2000, "m")
    # --- Histórico ---
    jrc_src = _first(proc / "jrc" / "occurrence_hidro.tif", _glob1(proc / "jrc", "occurrence_*.tif"))
    B.raster("jrc_occ", "JRC · ocurrencia de agua 1984-2021 (%)", "Histórico", jrc_src, JRC_CMAP, 0, 100, "%", mask_below=0.0,
             transform_fn=lambda a: np.where(a == 255, np.nan, a), description="Landsat, 30 m. % de observaciones con agua.")
    sar_csv = out / "sar_stats.csv"
    sar = pd.read_csv(sar_csv) if sar_csv.exists() else pd.DataFrame()
    scenes = []
    for _, r in sar.iterrows():
        if not isinstance(r.get("escena"), str) or r["escena"] in ("SIN COBERTURA", "SIN PASADA A TIEMPO"):
            continue
        db = _first(proc / "s1" / f"{r['escena']}_VV_db.tif", _glob1(proc / "s1", f"{r['escena']}_VV_db*.tif"))
        if db is None:
            B.warn(f"falta la escena {r['escena']}"); continue
        tag = r.get("momento") if isinstance(r.get("momento"), str) else "ref"
        ev = str(r["evento"])
        lab = f"{r['fecha']} · {ev.split('_')[0] if ev != 'referencia_seca' else 'referencia seca'} ({tag})"
        sid = re.sub(r"[^0-9a-zA-Z]", "", f"{r['fecha']}{tag}")
        B.raster(f"sar_db_{sid}", f"S1 γ⁰ VV dB · {lab}", "Histórico", db, "gray", -25, 0, "dB", geom=ext3, subgroup="sar_db",
                 description=f"Escena {r['escena']}")
        wm = _glob1(proc / "s1", f"water_{ev}_{r['fecha']}.tif")
        if wm:
            B.raster(f"sar_w_{sid}", f"S1 agua · {lab}", "Histórico", wm, geom=ext3, subgroup="sar_w",
                     categorical={1: ("agua (también en ref. seca)", "#1f4fd8"), 2: ("agua nueva", "#e31a1c")})
        num = {}
        for k in ["umbral_dB", "pct_agua_lote", "pct_agua_aoi", "pct_agua_500m", "pct_agua_hidro", "pct_agua_10km", "dB_medio_lote", "dB_dif_lote",
                  "pct_aoi_caida_3dB", "pct_500m_caida_3dB"]:
            if k in r:
                num[k] = None if pd.isna(r[k]) else float(r[k])
        scenes.append(dict(id=sid, label=lab, evento=ev, fecha=str(r["fecha"]), momento=tag, escena=r["escena"],
                           db_layer=f"sar_db_{sid}", w_layer=f"sar_w_{sid}" if wm else None, **num))

    # --- Simulación ---
    rog_csv = out / "rog_stats.csv"
    rog = pd.read_csv(rog_csv) if rog_csv.exists() else pd.DataFrame()
    cfg_ll = p.cfg.get("lluvia", {})
    by_id = {s["id"]: s for s in scenario_specs(cfg_ll)}
    scen = []
    for q in sorted((proc / "rog").glob("*_hmax_dom.tif")) if (proc / "rog").exists() else []:
        name = q.name.replace("_hmax_dom.tif", "")
        if name not in ficha_ids(cfg_ll):
            continue
        meta_p = proc / "rog" / f"{name}_meta.json"
        meta = json.load(open(meta_p)) if meta_p.exists() else {}
        row = rog[rog.escenario == name].iloc[0].to_dict() if len(rog) and (rog.escenario == name).any() else {}
        base = by_id.get(name.replace("_sat", ""))
        if base:
            P, dur = float(base["P_mm"]), float(base["dur_h"])
        else:
            mP = re.search(r"P(\d+)", name); md = re.search(r"_(\d+)h", name)
            P = float(mP.group(1)) if mP else float(row.get("P_mm", 0) or 0); dur = float(md.group(1)) if md else float(row.get("dur_h", 0) or 0)
        lab = f"{P:g} mm en {dur:g} h" + (f" · suelo saturado (Ks {cfg_ll.get('Ks_sat_mm_h', 2):g} mm/h)" if name.endswith("_sat") else "")
        B.raster(f"rog_h_{name}", f"Lámina máxima · {lab} (m)", "Simulación", q, "Blues", 0, 0.5, "m", mask_below=0.02,
                 subgroup="rog_h", visible=(name == "P100_24h"))
        B.raster(f"rog_d_{name}", f"Duración > 5 cm · {lab} (h)", "Simulación", proc / "rog" / f"{name}_dur5cm_dom.tif",
                 "YlGnBu", 0, 24, "h", mask_below=0.0, subgroup="rog_d")
        gj = out / f"rog_{name}_agua5cm.geojson"
        if gj.exists():
            B.vector(f"rog_v_{name}", f"Mancha > 5 cm · {lab}", "Simulación", gj, dict(color="#0033aa", weight=1, fillOpacity=0.35), False)
        scen.append(dict(id=name, label=lab, P_mm=P, dur_h=dur, hyetograph_mm=meta.get("hyetograph_mm", []),
                         Ks_mm_h=meta.get("Ks_mm_h"), balance=meta.get("balance"), h_layer=f"rog_h_{name}", d_layer=f"rog_d_{name}",
                         v_layer=f"rog_v_{name}" if gj.exists() else None,
                         **{k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in row.items()
                            if k not in ("escenario", "P_mm", "dur_h", "Ks_mm_h")}))
    if scen and not any(s.get("visible") for s in B.layers if s["id"].startswith("rog_h_")):
        for d in B.layers:
            if d["id"] == f"rog_h_{scen[0]['id']}":
                d["visible"] = True; break

    # --- manifiesto ---
    for l in B.layers:
        assert (web / l["url"]).exists(), l["url"]
    c84 = gpd.GeoSeries([c], crs=crs).to_crs(CRS_WGS84).iloc[0]
    manifest = dict(nombre=p.name, titulo=p.titulo, crs=crs, aoi_m=aoi_m, hidro_m=hidro_m, res_m=res_m, primary=primary,
                    generado=_dt.datetime.now().isoformat(timespec="seconds"), center=[float(c84.y), float(c84.x)],
                    layers=B.layers, scenes=scenes, scenarios=scen)
    json.dump(manifest, open(web / "layers.json", "w"), ensure_ascii=False, indent=0)

    # --- grid.json (±grilla_m) ---
    grid = {}; tr = None; shape_ = None
    if T is not None:
        a, tr, _ = read_window(T / "dem.tif", extg); grid["dem"] = a; shape_ = a.shape
        def add(key, path, fn=None):
            if path is None or not Path(path).exists():
                return
            v, _, _ = read_window(path, extg)
            if v.shape == shape_:
                grid[key] = fn(v) if fn else v
        add("hand", _first(T / "hand_05km2.tif", _glob1(T, "hand_*.tif")))
        add("slope_pct", T / "slope_deg.tif", sl2pct)
        add("twi", T / "twi.tif"); add("sink_m", T / "sink_depth.tif")
        add("facc_ha", T / "d8_facc_m2.tif", lambda v: v / 1e4); add("dist_m", T / "dist_downslope_stream.tif")
        add("jrc_occ", jrc_src, lambda v: np.where(v == 255, np.nan, v))
        for sc in scen:
            add(f"hmax_{sc['id']}", proc / "rog" / f"{sc['id']}_hmax_dom.tif"); add(f"dur_{sc['id']}", proc / "rog" / f"{sc['id']}_dur5cm_dom.tif")
    def enc(x, nd=2):
        return [None if not np.isfinite(v) else round(float(v), nd) for v in x.ravel()]
    from pyproj import CRS as _CRS
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        proj4 = _CRS.from_user_input(crs).to_proj4()
    json.dump(dict(crs=crs, proj4=proj4, transform=[tr.a, tr.b, tr.c, tr.d, tr.e, tr.f] if tr else None,
                   nrows=int(shape_[0]) if shape_ else 0, ncols=int(shape_[1]) if shape_ else 0,
                   layers={k: enc(v, 3 if k.startswith(("hmax", "sink")) else 2) for k, v in grid.items()}),
              open(web / "grid.json", "w"))

    # --- stats.json ---
    ts_p = out / "terrain_stats.csv"
    ts = pd.read_csv(ts_p) if ts_p.exists() else pd.DataFrame(columns=["variable"])
    vj = json.load(open(out / "veredicto.json")) if (out / "veredicto.json").exists() else {}
    if vj:
        shutil.copy(out / "veredicto.json", web / "veredicto.json")
    else:
        (web / "veredicto.json").unlink(missing_ok=True)
    prim_cols = [cc for cc in ts.columns if "(primario)" in cc]
    kv = dict(zip(ts["variable"], ts[prim_cols[0]])) if prim_cols else {}
    stats = dict(
        nombre=p.name, titulo=p.titulo, crs=crs, aoi_m=aoi_m, hidro_m=hidro_m, res_m=res_m, generado=manifest["generado"],
        lote=dict(area_m2=round(lote.area, 1), centroide_wgs84=manifest["center"], E=round(c.x, 1), N=round(c.y, 1)),
        primary=primary, terrain=dict(columns=list(ts.columns), rows=ts.values.tolist()), key=kv,
        jrc=_csv_rows(out / "jrc_stats.csv"), sar=_csv_rows(sar_csv), rog=_csv_rows(rog_csv),
        rog_params=json.load(open(out / "rog_params.json")) if (out / "rog_params.json").exists() else {},
        depresiones=_csv_rows(_first(out / "terrain_depresiones_aoi.csv", out / "terrain_depresiones_500m.csv")),
        verdict_md=vj.get("verdict_md", ""), field_md=vj.get("field_md", ""),
        jrc_extra=_jrc_extra(out / "jrc_stats.md"),
    )
    json.dump(stats, open(web / "stats.json", "w"), ensure_ascii=False,
              default=lambda o: None if (isinstance(o, float) and np.isnan(o)) else str(o))

    # --- figuras ---
    caps = {"00_": "Ubicación", "10_terrain_": "Terreno · ", "20_jrc_": "JRC · ", "30_sar_": "Sentinel-1 · ", "40_rog_": "Rain-on-grid · "}
    figs = []
    for q in sorted(out.glob("*.png")):
        shutil.copy(q, web / "figures" / q.name)
        cap = next((v + q.stem[len(k):].replace("_", " ") for k, v in caps.items() if q.name.startswith(k)), q.stem)
        figs.append(dict(file=f"figures/{q.name}", caption=cap))
    json.dump(figs, open(web / "figures.json", "w"), ensure_ascii=False)
    _vista_resumen(p, B)
    idx = update_index()
    size_mb = sum(f.stat().st_size for f in web.rglob("*") if f.is_file()) / 1e6
    p.summary_line("FASE WEB (datos del visor)", [
        f"capas: {len(B.layers)} · escenas Sentinel-1: {len(scenes)} · escenarios: {len(scen)} · figuras: {len(figs)}",
        f"grilla del click: {shape_[1] if shape_ else 0}x{shape_[0] if shape_ else 0} celdas (±{grilla_m/1000:g} km)",
        f"carpeta web: {web} ({size_mb:.1f} MB)",
        f"proyectos en el índice: {', '.join(r['nombre'] for r in idx)}",
        "abrir con: anega2 serve  (o python -m http.server 8000 en la raíz del repo → http://localhost:8000/webapp/?project=" + p.name + ")"
        + (f"  · avisos: {len(B.warnings)}" if B.warnings else ""),
    ])
    return dict(layers=len(B.layers), scenes=len(scenes), scenarios=len(scen), figures=len(figs), warnings=B.warnings, web=str(web))
