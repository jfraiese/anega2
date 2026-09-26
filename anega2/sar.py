"""Fase 2 · detección de agua con Sentinel-1 alrededor de eventos de lluvia.

Fuente: Sentinel-1 RTC (GRD IW, gamma0 corregido por terreno, 10 m) en Microsoft Planetary Computer,
colección `sentinel-1-rtc`, acceso anónimo con token SAS (no requiere cuenta).

Por escena: lectura por ventana (buffer hidro) de gamma0 VV lineal -> filtro Lee 7x7 -> dB -> umbral de
Otsu sobre el buffer hidro (si no hay bimodalidad, umbral fijo de la configuración) -> máscara de agua ->
diferencia contra una escena de referencia seca. Si hay varios frames del mismo pase se usa el que
contiene al lote.

Genera (rutas relativas al proyecto):
  data/raw/s1/<id>_VV.tif              ventana, CRS nativo UTM (valores sin tocar)
  data/proc/s1/<id>_VV_db.tif          Lee + dB, CRS del proyecto, 10 m
  data/proc/s1/ref_water.tif, water_<evento>_<fecha>.tif
  out/sar_<evento>_<tag>_<fecha>_water_aoi.tif, out/30_sar_<evento>_<tag>_<fecha>.png
  out/sar_stats.csv / .md  (las columnas conservan los nombres *_500m / *_10km por compatibilidad:
                            "500m" = buffer AOI, "10km" = buffer hidro)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds
from rasterio.windows import from_bounds
from scipy.ndimage import uniform_filter

from .common import CRS_WGS84, bounds_wgs84, clip_raster, df_to_md, rasterize_geom, write_gtiff
from .project import Project

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
RES = 10.0


def search(t0: str, t1: str, bbox):
    import planetary_computer as pc
    import pystac_client
    cat = pystac_client.Client.open(STAC, modifier=pc.sign_inplace)
    items = list(cat.search(collections=["sentinel-1-rtc"], bbox=bbox, datetime=f"{t0}/{t1}").items())
    items = [i for i in items if "vv" in i.assets]
    return sorted(items, key=lambda i: i.datetime)


def fetch_vv(item, bbox4326, raw_dir: Path) -> Path:
    """Ventana VV (gamma0 lineal) en CRS nativo -> data/raw/s1/<id>_VV.tif (sin tocar valores)."""
    dst = raw_dir / f"{item.id}_VV.tif"
    if dst.exists():
        return dst
    import planetary_computer as pc
    href = pc.sign(item.assets["vv"].href)
    with rasterio.open(href) as src:
        b = transform_bounds(CRS_WGS84, src.crs, *bbox4326)
        win = from_bounds(*b, transform=src.transform).round_offsets().round_lengths()
        arr = src.read(1, window=win); tr = src.window_transform(win)
        prof = src.profile.copy()
        prof.update(height=arr.shape[0], width=arr.shape[1], transform=tr, driver="GTiff", compress="deflate", tiled=False)
        prof.pop("blockxsize", None); prof.pop("blockysize", None)
        with rasterio.open(dst, "w", **prof) as d:
            d.write(arr, 1)
    return dst


def lee_filter(img: np.ndarray, size: int = 7) -> np.ndarray:
    ok = np.isfinite(img) & (img > 0)
    x = np.where(ok, img, np.nanmean(img[ok]))
    m = uniform_filter(x, size); m2 = uniform_filter(x * x, size)
    var = np.maximum(m2 - m * m, 0)
    noise = np.nanvar(x)  # varianza global como estimador del ruido (speckle multiplicativo ~ ENL)
    w = var / (var + noise + 1e-12)
    out = m + w * (x - m)
    out[~ok] = np.nan
    return out


def to_work_grid(src_path: Path, dst_path: Path, crs: str):
    """Filtro Lee sobre gamma0 lineal, paso a dB y reproyección al CRS del proyecto a 10 m."""
    if dst_path.exists():
        with rasterio.open(dst_path) as s:
            a = s.read(1).astype("float32"); a[a == s.nodata] = np.nan
            return a, s.transform
    with rasterio.open(src_path) as src:
        lin = src.read(1).astype("float64"); lin[lin <= 0] = np.nan
        filt = lee_filter(lin, 7)
        db = 10 * np.log10(np.maximum(filt, 1e-6)).astype("float32")
        db[~np.isfinite(filt)] = np.nan
        tr, w, h = calculate_default_transform(src.crs, crs, src.width, src.height, *src.bounds, resolution=RES)
        out = np.full((h, w), np.nan, dtype="float32")
        reproject(db, out, src_transform=src.transform, src_crs=src.crs, src_nodata=np.nan,
                  dst_transform=tr, dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.bilinear)
    write_gtiff(dst_path, np.where(np.isnan(out), -9999, out).astype("float32"), tr, crs, nodata=-9999)
    return out, tr


def align(arr, tr, ref_tr, ref_shape, crs: str):
    """Realinea un raster ya en el CRS del proyecto a la grilla de referencia."""
    out = np.full(ref_shape, np.nan, dtype="float32")
    reproject(arr, out, src_transform=tr, src_crs=crs, src_nodata=np.nan,
              dst_transform=ref_tr, dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.bilinear)
    return out


FRAC_AGUA_MAX = 0.20  # fracción máxima plausible de agua abierta en el buffer hidrológico; por encima, Otsu está separando suelo húmedo/cultivos, no agua


def otsu_db(db: np.ndarray, mask: np.ndarray, fixed: float) -> tuple[float, str]:
    from skimage.filters import threshold_otsu
    v = db[mask & np.isfinite(db)]
    v = v[(v > -35) & (v < 5)]
    t = float(threshold_otsu(v, nbins=256))
    note = "Otsu"
    if t > -13.0:  # sin agua suficiente para bimodalidad: Otsu separa suelo/vegetación, no agua
        note = f"Otsu={t:.1f} dB no plausible para agua; se usa umbral fijo {fixed:.0f} dB"
        t = float(fixed)
    else:
        frac = float(np.mean(v < t))
        if frac > FRAC_AGUA_MAX:  # Otsu separa suelo húmedo/cultivos, no agua abierta
            note = f"Otsu={t:.1f} dB marca {100*frac:.0f} % del buffer como agua (no plausible); se usa umbral fijo {fixed:.0f} dB"
            t = float(fixed)
    return t, note


def _pick_frame(items, lot84):
    """Si hay varios frames del mismo pase, el que contiene al lote (o el de mayor área)."""
    from shapely.geometry import shape as _shape
    return sorted(items, key=lambda i: (not _shape(i.geometry).contains(lot84), -_shape(i.geometry).area))[0]


def plan_escenas(fechas, fecha_evento, pre_max_d: int, post_max_d: int):
    """(pre, post): la última fecha en [evento − pre_max_d, evento) y la primera en [evento, evento + post_max_d]."""
    pre = [d for d in fechas if 0 < (fecha_evento - d).days <= pre_max_d]
    post = [d for d in fechas if 0 <= (d - fecha_evento).days <= post_max_d]
    return (max(pre) if pre else None, min(post) if post else None)


def run(p: Project) -> dict:
    import geopandas as gpd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from rasterio.plot import plotting_extent
    from shapely.geometry import Point

    aoi = p.load_aoi(); crs = p.crs
    cfg = p.cfg["sar"]; fixed = float(cfg.get("umbral_fijo_dB", -18.0))
    from .clima import resolve_events
    events = {e["id"]: e for e in resolve_events(p)}
    if not events:
        print("SAR: sin eventos para buscar; se omite la fase."); return {}
    pre_max, post_max = int(cfg.get("pre_max_d", 12)), int(cfg.get("post_max_d", 3))
    dry = cfg["referencia_seca"]
    aoi_lab = f"{p.aoi_m:.0f} m"; hidro_lab = f"{p.hidro_m / 1000:.0f} km"
    RAW = p.data_raw / "s1"; PROC = p.data_proc / "s1"
    RAW.mkdir(parents=True, exist_ok=True); PROC.mkdir(parents=True, exist_ok=True)
    bbox = bounds_wgs84(aoi["hidro"], crs, pad_deg=0.005)
    lot84 = gpd.GeoSeries([Point(aoi["lote"].centroid.x, aoi["lote"].centroid.y)], crs=crs).to_crs(CRS_WGS84).iloc[0]

    # --- búsqueda de escenas (referencia + eventos) --------------------------
    ref_items = search(dry["desde"], dry["hasta"], bbox)
    if not ref_items:
        print("SAR: sin escena de referencia seca en la ventana configurada; se omite la fase."); return {}
    ref = ref_items[len(ref_items) // 2]
    plan = []  # (key, ev, item, date, tag)
    for key, ev in events.items():
        d = pd.Timestamp(ev["fecha"])
        items = search(str((d - pd.Timedelta(days=pre_max)).date()), str((d + pd.Timedelta(days=post_max)).date()), bbox)
        by_date = {}
        for it in items:
            by_date.setdefault(it.datetime.date(), []).append(it)
        pre, post = plan_escenas(list(by_date), d.date(), pre_max, post_max)
        if pre is None and post is None and not by_date:
            plan.append((key, ev, None, None, None)); continue
        if pre is not None:
            plan.append((key, ev, _pick_frame(by_date[pre], lot84), pre, "pre"))
        if post is not None:
            plan.append((key, ev, _pick_frame(by_date[post], lot84), post, "post"))
        else:
            plan.append((key, ev, None, None, "sin_post"))
    todo = [it for it in [ref] + [x[2] for x in plan if x[2] is not None] if not (RAW / f"{it.id}_VV.tif").exists()]
    n_scenes = 1 + sum(1 for x in plan if x[2] is not None)
    msg = (f"Sentinel-1 RTC (Planetary Computer): {n_scenes} escenas ({len(todo)} por bajar, ≈{16*len(todo)} MB; ventana {hidro_lab}):\n  "
           + "\n  ".join(f"{it.datetime.date()} {it.id}" for it in ([ref] + [x[2] for x in plan if x[2] is not None])))
    if todo and not p.confirm(msg):
        print("SAR: descarga no confirmada; se omite la fase."); return {}

    # --- referencia seca -----------------------------------------------------
    print(f"Referencia seca: {ref.id} ({ref.datetime.date()}), {len(ref_items)} candidatas")
    ref_db, ref_tr = to_work_grid(fetch_vv(ref, bbox, RAW), PROC / f"{ref.id}_VV_db.tif", crs)
    shape = ref_db.shape
    b10 = rasterize_geom(aoi["hidro"], shape, ref_tr); b500 = rasterize_geom(aoi["aoi"], shape, ref_tr)
    lot = rasterize_geom(aoi["lote"], shape, ref_tr, all_touched=True)
    t_ref, note_ref = otsu_db(ref_db, b10, fixed)
    ref_water = (ref_db < t_ref) & b10
    print(f"  umbral referencia: {t_ref:.2f} dB ({note_ref}); agua en {hidro_lab}: {100*ref_water.sum()/b10.sum():.2f} %")
    rows = [dict(evento="referencia_seca", descr=dry.get("descr", "referencia seca"), escena=ref.id, fecha=str(ref.datetime.date()),
                 orbita=ref.properties.get("sat:orbit_state"), umbral_dB=t_ref, nota=note_ref,
                 pct_agua_10km=100 * ref_water.sum() / b10.sum(), pct_agua_500m=100 * (ref_water & b500).sum() / b500.sum(),
                 pct_agua_lote=100 * (ref_water & lot).sum() / lot.sum(), pct_nueva_500m=np.nan, pct_nueva_lote=np.nan,
                 dB_medio_lote=float(np.nanmean(ref_db[lot])), dB_medio_500m=float(np.nanmean(ref_db[b500])))]
    write_gtiff(PROC / "ref_water.tif", ref_water.astype("uint8"), ref_tr, crs, nodata=None, dtype="uint8")

    # --- eventos -------------------------------------------------------------
    osm_path = p.out / "osm_waterways.geojson"
    osm = gpd.read_file(osm_path) if osm_path.exists() else None
    ext_geom = aoi["aoi"].buffer(2 * p.aoi_m)
    for key, ev, it, date, tag in plan:
        d = pd.Timestamp(ev["fecha"])
        if it is None:
            if tag == "sin_post":
                print(f"[{key}] sin pasada de Sentinel-1 dentro de los {post_max} días posteriores")
                rows.append(dict(evento=key, descr=ev.get("descr", ""), escena="SIN PASADA A TIEMPO", fecha=None, momento="post",
                                 fecha_evento=str(d.date()),
                                 nota=f"sin pasada en 0-{post_max} días: no se puede saber si hubo agua")); continue
            print(f"[{key}] sin escenas entre −{pre_max} y +{post_max} días de {ev['fecha']}")
            rows.append(dict(evento=key, descr=ev.get("descr", ""), escena="SIN COBERTURA", fecha=None, fecha_evento=str(d.date()))); continue
        print(f"[{key}] {it.id} ({date}, {tag}, {it.properties.get('sat:orbit_state')})")
        db, tr = to_work_grid(fetch_vv(it, bbox, RAW), PROC / f"{it.id}_VV_db.tif", crs)
        db = align(db, tr, ref_tr, shape, crs) if (db.shape != shape or tr != ref_tr) else db
        t, note = otsu_db(db, b10, fixed)
        water = (db < t) & b10
        new = water & ~ref_water
        diff = db - ref_db
        rows.append(dict(evento=key, descr=ev.get("descr", ""), escena=it.id, fecha=str(date), momento=tag,
                         fecha_evento=str(d.date()),
                         dias_desde_evento=(date - d.date()).days, orbita=it.properties.get("sat:orbit_state"),
                         umbral_dB=t, nota=note,
                         pct_agua_10km=100 * water.sum() / b10.sum(), pct_agua_500m=100 * (water & b500).sum() / b500.sum(),
                         pct_agua_lote=100 * (water & lot).sum() / lot.sum(),
                         pct_nueva_500m=100 * (new & b500).sum() / b500.sum(), pct_nueva_lote=100 * (new & lot).sum() / lot.sum(),
                         dB_medio_lote=float(np.nanmean(db[lot])), dB_medio_500m=float(np.nanmean(db[b500])),
                         dB_dif_lote=float(np.nanmean(diff[lot])), pct_500m_caida_3dB=100 * float(np.nanmean(diff[b500] < -3))))
        wm = np.where(b10, water.astype("uint8") + new.astype("uint8"), 255).astype("uint8")  # 0 no agua, 1 agua ya en ref, 2 nueva
        wpath = PROC / f"water_{key}_{date}.tif"
        write_gtiff(wpath, wm, ref_tr, crs, nodata=255, dtype="uint8")
        clip_raster(wpath, aoi["aoi"], p.out / f"sar_{key}_{tag}_{date}_water_aoi.tif", all_touched=True, nodata=255)
        # PNG: 3 paneles
        fig, axes = plt.subplots(1, 3, figsize=(19, 6.5))
        e = plotting_extent(db, ref_tr)
        x0, y0, x1, y1 = ext_geom.bounds
        for ax, (a, ttl, cmap, vmin, vmax) in zip(axes, [
            (db, f"γ⁰ VV (dB) · {date} ({tag})", "gray", -25, 0),
            (diff, f"Δ dB vs. referencia seca ({ref.datetime.date()})", "RdBu", -8, 8),
            (np.where(wm == 255, np.nan, wm.astype(float)), f"Agua (umbral {t:.1f} dB): azul = ya en ref., rojo = nueva", "coolwarm", 0, 2)]):
            im = ax.imshow(np.ma.masked_invalid(a), extent=e, cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
            gpd.GeoSeries(aoi["aoi"], crs=crs).boundary.plot(ax=ax, color="orange", lw=1.5)
            gpd.GeoSeries(aoi["lote"], crs=crs).boundary.plot(ax=ax, color="red", lw=2)
            if osm is not None and len(osm):
                osm.plot(ax=ax, color="cyan", lw=1)
            ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal"); ax.set_title(ttl, fontsize=10)
            ax.set_xticks([]); ax.set_yticks([])
            fig.colorbar(im, ax=ax, shrink=0.75)
        fig.suptitle(f"{key} · {ev.get('descr', '')} · Sentinel-1 RTC {it.id[:3]} órbita {it.properties.get('sat:orbit_state')}", fontsize=11)
        fig.tight_layout(rect=(0, 0, 1, 0.95))
        fig.savefig(p.out / f"30_sar_{key}_{tag}_{date}.png", dpi=120); plt.close(fig)

    df = pd.DataFrame(rows)
    df.to_csv(p.out / "sar_stats.csv", index=False, float_format="%.2f")
    cols = ["evento", "escena", "fecha", "momento", "dias_desde_evento", "umbral_dB", "pct_agua_lote", "pct_agua_500m", "pct_nueva_lote",
            "pct_nueva_500m", "pct_agua_10km", "dB_medio_lote", "dB_dif_lote", "pct_500m_caida_3dB", "nota"]
    cols = [c for c in cols if c in df.columns]
    (p.out / "sar_stats.md").write_text(
        "# Sentinel-1 RTC · agua detectada por evento\n\n"
        f"Fuente: Planetary Computer `sentinel-1-rtc` (gamma0 VV, 10 m). Filtro Lee 7x7, umbral de Otsu sobre el histograma "
        f"del buffer {hidro_lab} (si Otsu > −13 dB, o si marca más del {100*FRAC_AGUA_MAX:.0f} % del buffer como agua, "
        f"no es plausible y se usa {fixed:.0f} dB fijo). "
        "'nueva' = agua en la escena y no en la referencia seca. Columnas: `*_500m` = buffer AOI "
        f"({aoi_lab}), `*_10km` = buffer hidrológico ({hidro_lab}).\n\n"
        "**Limitaciones**: el radar en banda C no ve el suelo bajo copas (agua bajo árboles aparece brillante por doble rebote, "
        "no oscura); superficies lisas no-agua (suelo desnudo húmedo, pavimento, cultivos rastreros) también aparecen oscuras; "
        "el viento rugosifica el agua. Píxeles de 10 m.\n\n" + df_to_md(df[cols]) + "\n")

    lines = []
    for _, r in df.iterrows():
        if r.get("escena") in ("SIN COBERTURA", "SIN PASADA A TIEMPO"):
            lines.append(f"{r['evento']}: {r['escena'].lower()}"); continue
        pn = r.get("pct_nueva_500m"); pn = 0 if pd.isna(pn) else pn
        lines.append(f"{r['evento']} {r['fecha']} ({r.get('momento', 'ref') if isinstance(r.get('momento'), str) else 'ref'}): "
                     f"umbral {r['umbral_dB']:.1f} dB · agua lote {r['pct_agua_lote']:.1f} % · {aoi_lab} {r['pct_agua_500m']:.1f} % "
                     f"(nueva {pn:.1f} %) · {hidro_lab} {r['pct_agua_10km']:.2f} %")
    p.summary_line("FASE 2 (SAR Sentinel-1)", lines)
    return dict(referencia=ref.id, filas=df.to_dict("records"))
