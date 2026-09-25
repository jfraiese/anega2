"""Fase lluvia · simulación lluvia → lámina de agua (rain-on-grid) con Landlab OverlandFlow.

Dominio: cuadrado de ±buffers.lluvia_m alrededor del lote, sobre el DEM primario corregido
(data/proc/terrain/<primario>/dem_breach.tif), a la resolución nativa del DEM. Bordes abiertos.
Infiltración: Green-Ampt por celda (Ks, ψ, Δθ de cfg['lluvia']). Escenarios de cfg['lluvia'].escenarios,
más copias "_sat" (suelo saturado, Ks_sat_mm_h) para los ids de cfg['lluvia'].saturado.
Hietograma de bloque alterno con relaciones profundidad-duración genéricas (sin IDF local: sin período de retorno).

Salidas: data/proc/rog/<esc>_hmax_dom.tif, <esc>_dur5cm_dom.tif, <esc>_meta.json;
         out/rog_<esc>_hmax_aoi.tif, out/rog_<esc>_dur5cm_aoi.tif, out/40_rog_<esc>.png, out/40_rog_<esc>_dom.png,
         out/rog_stats.csv/.md, out/rog_params.json, out/rog_<esc>_agua5cm.geojson/.kml
"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio import features
from shapely.geometry import shape

from .common import CRS_WGS84, clip_raster, df_to_md, plot_map, rasterize_geom, read_window, write_gtiff
from .project import Project

# Relaciones profundidad-duración genéricas P(d)/P(dur) para la Pampa húmeda (supuesto, sin IDF local).
# Claves en fracción de la duración total de la tormenta (se escalan a cualquier duración).
DD_SHAPE_LONG = {1 / 24: 0.40, 2 / 24: 0.52, 3 / 24: 0.60, 4 / 24: 0.66, 6 / 24: 0.74, 8 / 24: 0.80, 12 / 24: 0.88, 18 / 24: 0.95, 1.0: 1.0}
DD_SHAPE_SHORT = {10 / 120: 0.25, 20 / 120: 0.40, 30 / 120: 0.55, 60 / 120: 0.75, 90 / 120: 0.90, 1.0: 1.0}
H_FILM = 1e-5      # película mínima que requiere el esquema de de Almeida (h_init de OverlandFlow)
ALPHA = 0.7        # coeficiente de estabilidad de OverlandFlow
H_THRESH = 0.05    # umbral de "anegado" (m) para la duración y las manchas


def encode_frame(h_m: np.ndarray) -> np.ndarray:
    return np.clip(np.round((h_m - H_FILM) * 100), 0, 255).astype(np.uint8)


def lote_por_hora(frames: np.ndarray, lot: np.ndarray) -> dict:
    v = frames[:, lot].astype(float)
    hmax = v.max(axis=1)
    return dict(hmax_lote_cm=[int(x) for x in hmax],
                pct_lote_gt5cm=[round(100 * float(x), 1) for x in (v > 5).mean(axis=1)],
                pct_lote_gt20cm=[round(100 * float(x), 1) for x in (v > 20).mean(axis=1)],
                horas_con_agua_lote=int((hmax > 5).sum()), hora_pico_lote=int(hmax.argmax()))


def alternating_block(P_mm: float, dur_h: float, dt_h: float, ratios: dict) -> np.ndarray:
    """Hietograma de bloque alterno (mm por intervalo) a partir de relaciones P(d)/P(dur) (d en horas)."""
    ds = np.array(sorted(ratios)); rs = np.array([ratios[d] for d in ds])
    n = int(round(dur_h / dt_h))
    t = np.arange(1, n + 1) * dt_h
    cum = np.interp(t, ds, rs, left=rs[0] * t[0] / ds[0]) * P_mm
    cum = np.maximum.accumulate(cum)
    inc = np.diff(np.concatenate([[0.0], cum]))
    inc = np.sort(inc)[::-1]
    out = np.zeros(n); mid = n // 2
    out[mid] = inc[0]
    l, r = mid - 1, mid + 1
    for i, v in enumerate(inc[1:], 1):
        if i % 2 == 1 and l >= 0:
            out[l] = v; l -= 1
        elif r < n:
            out[r] = v; r += 1
        elif l >= 0:
            out[l] = v; l -= 1
    return out


def scen_id(P: float, dur: float, sat: bool) -> str:
    return f"P{int(round(P)):03d}_{dur:g}h" + ("_sat" if sat else "")


def scenario_specs(cfg: dict) -> list[dict]:
    """Escenarios a correr: la grilla P × duración × suelo, o la lista del formato viejo (escenarios + saturado)."""
    if cfg.get("escenarios"):
        print("  [aviso] lluvia.escenarios / saturado es el formato viejo: se usa tal cual (ver lluvia.grilla en defaults.yml)")
        out = [dict(id=s["id"], P_mm=float(s["P_mm"]), dur_h=float(s["dur_h"]), suelo="normal") for s in cfg["escenarios"]]
        by = {s["id"]: s for s in out}
        out += [dict(by[i], id=f"{i}_sat", suelo="saturado") for i in cfg.get("saturado", []) or [] if i in by]
        return out
    g = cfg["grilla"]
    return [dict(id=scen_id(P, d, s == "saturado"), P_mm=float(P), dur_h=float(d), suelo=s)
            for P in g["P_mm"] for d in g["dur_h"] for s in g["suelo"]]


def build_scenarios(cfg: dict) -> dict:
    """Escenarios -> {id: dict(P_mm, dur_h, dt_h, ratios, t_end_h, Ks_mm_h, suelo, label)}."""
    dren = float(cfg.get("drenaje_h", 24)); out = {}
    for s in scenario_specs(cfg):
        dur, P, sat = s["dur_h"], s["P_mm"], s["suelo"] == "saturado"
        dt_h = 1.0 if dur >= 6 else 1 / 6
        shape_ = DD_SHAPE_LONG if dur > 3 else DD_SHAPE_SHORT
        ks = float(cfg["Ks_sat_mm_h"] if sat else cfg["Ks_mm_h"])
        out[s["id"]] = dict(P_mm=P, dur_h=dur, dt_h=dt_h, ratios={f * dur: r for f, r in shape_.items()}, t_end_h=dur + dren, Ks_mm_h=ks,
                            suelo=s["suelo"], label=f"{P:g} mm en {dur:g} h" + (f" · suelo saturado (Ks {ks:g} mm/h)" if sat else ""))
    return out


def ficha_ids(cfg: dict) -> list[str]:
    return list(cfg.get("ficha") or [s["id"] for s in scenario_specs(cfg) if s["dur_h"] == 24])


def load_dem_window(p: Project, primary: str, aoi: dict, name: str = "dem_breach.tif"):
    half = float(p.buffers["lluvia_m"])
    c = aoi["lote"].centroid
    from shapely.geometry import box
    return read_window(p.data_proc / "terrain" / primary / name, box(c.x - half, c.y - half, c.x + half, c.y + half))


def run_scenario(p: Project, name: str, sc: dict, z: np.ndarray, tr, params: dict, budget_s: float, lot: np.ndarray, subdir: str = "") -> dict:
    from landlab import RasterModelGrid
    from landlab.components import OverlandFlow

    proc = p.data_proc / "rog" / subdir; proc.mkdir(parents=True, exist_ok=True)
    hmax_path = proc / f"{name}_hmax_dom.tif"; dur_path = proc / f"{name}_dur5cm_dom.tif"; meta_path = proc / f"{name}_meta.json"
    frames_path = proc / f"{name}_frames.npz"
    if hmax_path.exists() and dur_path.exists() and meta_path.exists() and frames_path.exists():
        with rasterio.open(hmax_path) as s:
            hmax = s.read(1)
        with rasterio.open(dur_path) as s:
            dur = s.read(1)
        return dict(hmax=hmax, dur=dur, **json.load(open(meta_path)))

    rows, cols = z.shape
    dx = tr.a
    grid = RasterModelGrid((rows, cols), xy_spacing=dx)
    zz = np.flipud(z).astype(np.float64)           # Landlab: fila 0 = sur; OverlandFlow exige float64
    zz[np.isnan(zz)] = np.nanmax(zz) + 10          # nodata -> pared alta
    grid.add_field("topographic__elevation", zz.ravel(), at="node", clobber=True)
    grid.add_zeros("surface_water__depth", at="node", clobber=True)
    grid.status_at_node[grid.perimeter_nodes] = grid.BC_NODE_IS_FIXED_VALUE  # bordes abiertos
    of = OverlandFlow(grid, mannings_n=params["manning"], alpha=ALPHA, steep_slopes=True, rainfall_intensity=0.0)

    hyet = alternating_block(sc["P_mm"], sc["dur_h"], sc["dt_h"], sc["ratios"])
    dt_block = sc["dt_h"] * 3600; t_end = sc["t_end_h"] * 3600
    Ks = sc["Ks_mm_h"] / 1000 / 3600; psi_dt = params["psi_m"] * params["dtheta"]
    F = np.full(grid.number_of_nodes, 1e-4)
    h = grid.at_node["surface_water__depth"]
    hmax = np.zeros_like(h); dur = np.zeros_like(h)
    infil_tot = np.zeros_like(h); rain_tot = 0.0; out_tot = 0.0
    bdy = grid.boundary_nodes; core = grid.core_nodes; cell_a = dx * dx
    t = 0.0; steps = 0; t0 = time.time(); next_log = 3600
    frames = [encode_frame(np.flipud(h.reshape(rows, cols)))]; rain_acc = [0.0]; next_frame = 3600.0
    while t < t_end:
        k = int(t // dt_block)
        rain = hyet[k] / 1000 / dt_block if k < len(hyet) else 0.0
        dt = float(of.calc_time_step())
        if not np.isfinite(dt):
            dt = 60.0
        dt = min(dt, t_end - t, dt_block - (t - k * dt_block) if k < len(hyet) else t_end - t, next_frame - t, 60.0)
        dt = max(dt, 0.1)
        h += rain * dt; rain_tot += rain * dt
        fp = Ks * (1 + psi_dt / F[core]) * dt
        inf = np.minimum(fp, np.maximum(h[core] - H_FILM, 0.0))
        h[core] -= inf; F[core] += inf; infil_tot[core] += inf
        core_sum_before = float(h[core].sum())
        of.overland_flow(dt=dt)
        out_tot += (core_sum_before - float(h[core].sum())) * cell_a          # flujo core -> borde (el borde es fijo, no acumula estado)
        out_tot += float(np.maximum(h[bdy] - H_FILM, 0).sum()) * cell_a       # lluvia caída directo sobre el borde
        h[bdy] = H_FILM
        np.maximum(hmax, h, out=hmax)
        dur += (h > H_THRESH) * dt
        t += dt; steps += 1
        if t >= next_frame - 1e-6:
            frames.append(encode_frame(np.flipud(h.reshape(rows, cols)))); rain_acc.append(rain_tot * 1000); next_frame += 3600.0
        if t >= next_log:
            el = time.time() - t0
            print(f"    [{name}] t={t/3600:5.1f} h · pasos {steps} · dt={dt:5.1f} s · h_max dominio {h[core].max():.2f} m · {el:5.0f} s")
            next_log += 3600 * 3
            if el > budget_s:
                print(f"    [{name}] presupuesto de tiempo agotado a t={t/3600:.1f} h; se corta la simulación"); break
    el = time.time() - t0
    hmax2 = np.flipud(np.maximum(hmax - H_FILM, 0).reshape(rows, cols)).astype("float32")
    dur2 = np.flipud(dur.reshape(rows, cols) / 3600).astype("float32")
    write_gtiff(hmax_path, hmax2, tr, p.crs, nodata=None); write_gtiff(dur_path, dur2, tr, p.crs, nodata=None)
    fr = np.stack(frames)
    np.savez_compressed(frames_path, h_cm=fr, t_h=np.arange(len(fr)), lluvia_acum_mm=np.array(rain_acc))
    n_core = len(core)
    vol_rain = rain_tot * cell_a * grid.number_of_nodes; vol_inf = float(infil_tot[core].sum()) * cell_a
    vol_store = float(np.maximum(h[core] - H_FILM, 0).sum()) * cell_a
    meta = dict(steps=steps, t_sim_h=t / 3600, wall_s=el, rain_mm=rain_tot * 1000, Ks_mm_h=Ks * 3.6e6,
                infil_mean_mm=float(infil_tot[core].mean() * 1000), hyetograph_mm=hyet.round(2).tolist(),
                balance=dict(lluvia_m3=vol_rain, infiltrado_m3=vol_inf, almacenado_final_m3=vol_store, salida_bordes_m3=out_tot,
                             error_pct=100 * (vol_rain - vol_inf - vol_store - out_tot) / max(vol_rain, 1e-9)))
    meta.update(lote_por_hora(fr, lot))
    json.dump(meta, open(meta_path, "w"), indent=1)
    b = meta["balance"]
    print(f"  [{name}] listo: {steps} pasos, {el/60:.1f} min, lluvia {rain_tot*1000:.0f} mm, infiltración media {meta['infil_mean_mm']:.0f} mm · "
          f"infiltrado {100*b['infiltrado_m3']/b['lluvia_m3']:.0f} %, almacenado {100*b['almacenado_final_m3']/b['lluvia_m3']:.0f} %")
    return dict(hmax=hmax2, dur=dur2, **meta)


def _worker(args):
    p, name, sc, z, tr, params, budget_s, lot, subdir = args
    return name, run_scenario(p, name, sc, z, tr, params, budget_s, lot, subdir)


def _first(*paths: Path) -> Path | None:
    return next((q for q in paths if q is not None and q.exists()), None)


def run(p: Project) -> dict:
    cfg = p.cfg["lluvia"]
    params = dict(manning=float(cfg["manning"]), Ks_mm_h=float(cfg["Ks_mm_h"]), Ks_sat_mm_h=float(cfg["Ks_sat_mm_h"]),
                  psi_m=float(cfg["psi_m"]), dtheta=float(cfg["dtheta"]), alpha=ALPHA, h_thresh_m=H_THRESH,
                  drenaje_h=float(cfg.get("drenaje_h", 6)), dominio_m=float(p.buffers["lluvia_m"]))
    aoi = p.load_aoi(); out = p.out
    primary = json.load(open(out / "terrain_primary.json"))["primary"]
    z, tr = load_dem_window(p, primary, aoi)
    res = abs(tr.a)
    print(f"DEM: {primary} dem_breach, dominio ±{params['dominio_m']/1000:g} km ({z.shape[1]}x{z.shape[0]} celdas de {res:.0f} m)")
    lot = rasterize_geom(aoi["lote"], z.shape, tr, all_touched=True); ba = rasterize_geom(aoi["aoi"], z.shape, tr)
    hs, _ = load_dem_window(p, primary, aoi, "hillshade.tif")
    scen = build_scenarios(cfg)
    budget_s = 60 * float(cfg.get("presupuesto_min", 60))
    nproc = cfg.get("procesos", "auto"); nproc = max(1, (os.cpu_count() or 4) - 2) if nproc == "auto" else int(nproc)
    lot_n = rasterize_geom(aoi["lote"], z.shape, tr, all_touched=True)
    jobs = [(p, name, sc, z, tr, params, budget_s, lot_n, "") for name, sc in scen.items()]
    print(f"{len(jobs)} escenarios · {nproc} en paralelo")
    with ProcessPoolExecutor(nproc) as ex:
        results = dict(ex.map(_worker, jobs))          # "res" ya está usado para la resolución del DEM
    aoi_lab = f"{p.aoi_m:.0f} m"
    ov = []
    osm = _first(out / "osm_waterways.geojson", out / "osm_waterways_10km.geojson")
    if osm:
        ov.append((gpd.read_file(osm).geometry, dict(color="white", lw=1.5)))
    red = _first(out / "terrain_red_drenaje_05km2.geojson")
    if red:
        ov.append((gpd.read_file(red).geometry, dict(color="deepskyblue", lw=0.8)))
    rows = []
    fids = ficha_ids(cfg)
    for name, sc in scen.items():
        print(f"== {name}: {sc['label']} ==")
        r = results[name]
        hmax, dur = r["hmax"], r["dur"]
        clip_raster(p.data_proc / "rog" / f"{name}_hmax_dom.tif", aoi["aoi"], out / f"rog_{name}_hmax_aoi.tif", all_touched=True, nodata=-9999)
        clip_raster(p.data_proc / "rog" / f"{name}_dur5cm_dom.tif", aoi["aoi"], out / f"rog_{name}_dur5cm_aoi.tif", all_touched=True, nodata=-9999)
        rows.append(dict(escenario=name, P_mm=sc["P_mm"], dur_h=sc["dur_h"], Ks_mm_h=r.get("Ks_mm_h", sc["Ks_mm_h"]),
                         hmax_lote_m=float(hmax[lot].max()), hmedia_lote_m=float(hmax[lot].mean()),
                         pct_lote_gt5cm=100 * float((hmax[lot] > 0.05).mean()), pct_lote_gt20cm=100 * float((hmax[lot] > 0.20).mean()),
                         dur_max_lote_h=float(dur[lot].max()),
                         hmax_aoi_m=float(hmax[ba].max()), hmedia_aoi_m=float(hmax[ba].mean()),
                         pct_aoi_gt5cm=100 * float((hmax[ba] > 0.05).mean()), pct_aoi_gt20cm=100 * float((hmax[ba] > 0.20).mean()),
                         infil_media_mm=r["infil_mean_mm"],
                         escurrido_pct=100 * (1 - r["balance"]["infiltrado_m3"] / r["balance"]["lluvia_m3"]),
                         almacenado_final_pct=100 * r["balance"]["almacenado_final_m3"] / r["balance"]["lluvia_m3"],
                         t_sim_h=r["t_sim_h"], pasos=r["steps"], wall_min=r["wall_s"] / 60))
        if name not in fids:
            continue
        plot_map(np.where(hmax > 0.02, hmax, np.nan), tr, aoi,
                 f"Lámina máxima (m) · {sc['label']} · Green-Ampt Ks={sc['Ks_mm_h']:g} mm/h · n={params['manning']}\n"
                 f"DEM {primary} {res:.0f} m · se muestran celdas con h > 2 cm",
                 out / f"40_rog_{name}.png", cmap="Blues", vmin=0, vmax=0.5, cbar_label="m", extent_geom=aoi["aoi"].buffer(1000),
                 overlays=ov, hillshade=hs)
        plot_map(np.where(hmax > H_THRESH, hmax, np.nan), tr, aoi,
                 f"Lámina máxima (m) · {sc['label']} · dominio ±{params['dominio_m']/1000:g} km (h > 5 cm)",
                 out / f"40_rog_{name}_dom.png", cmap="Blues", vmin=0, vmax=1.0, cbar_label="m",
                 extent_geom=aoi["lote"].buffer(params["dominio_m"]).envelope, overlays=ov, hillshade=hs, figsize=(10, 9))
        m = hmax > H_THRESH
        shp = [shape(g) for g, v in features.shapes(m.astype("uint8"), mask=m, transform=tr) if v == 1]
        if shp:
            g = gpd.GeoDataFrame({"Name": [f"{sc['label']} · h>5 cm"] * len(shp)}, geometry=shp, crs=p.crs)
            g = g[g.intersects(aoi["aoi"].buffer(2000))]
            if len(g):
                g.to_file(out / f"rog_{name}_agua5cm.geojson", driver="GeoJSON")
                g.to_crs(CRS_WGS84).to_file(out / f"rog_{name}_agua5cm.kml", driver="KML")
    df = pd.DataFrame(rows)
    df.to_csv(out / "rog_stats.csv", index=False, float_format="%.3f")
    (out / "rog_stats.md").write_text(
        "# Rain-on-grid · lámina máxima por escenario\n\n"
        f"Landlab OverlandFlow (de Almeida et al. 2012) sobre {primary} ({res:.0f} m, dominio ±{params['dominio_m']/1000:g} km), "
        f"Manning n = {params['manning']}, Green-Ampt Ks = {params['Ks_mm_h']:g} mm/h (saturado: {params['Ks_sat_mm_h']:g}), "
        f"ψ = {params['psi_m']} m, Δθ = {params['dtheta']}. Hietograma de bloque alterno. Sin período de retorno (no hay IDF local). "
        f"Columnas `*_aoi_*` = buffer de {aoi_lab}. `escurrido_pct` = 100 − infiltrado (sale por los bordes abiertos o queda almacenado; "
        "la salida por los bordes se estima como residuo).\n\n" + df_to_md(df) + "\n")
    json.dump(params, open(out / "rog_params.json", "w"), indent=1)
    lines = []
    for _, r in df.iterrows():
        lines.append(f"{r['escenario']}: lote h_max {r['hmax_lote_m']*100:.0f} cm, {r['pct_lote_gt5cm']:.0f} % >5 cm, "
                     f"{r['pct_lote_gt20cm']:.0f} % >20 cm, anegado máx {r['dur_max_lote_h']:.1f} h · {aoi_lab}: "
                     f"{r['pct_aoi_gt5cm']:.0f} % >5 cm, {r['pct_aoi_gt20cm']:.0f} % >20 cm · infiltrado {r['infil_media_mm']:.0f} mm")
    p.summary_line("FASE LLUVIA (rain-on-grid)", lines[:5] if len(lines) <= 5 else lines)
    return dict(escenarios=list(scen), stats=df.to_dict("records"), primary=primary, params=params)
