"""Ficha para arquitecto / ingeniero: láminas A4 apaisadas sobre imagen satelital, con leyenda, escala, pie de
figura con los números clave y pie de página (proyecto, fecha, DEM, página), más el PDF que las junta
(out/ficha/*.png y out/ficha_<nombre>.pdf).

Páginas: resumen · 1 ubicación regional · 2 lote y drenaje · 3 cotas · 4 altura sobre el drenaje (HAND) ·
5 el drenaje más cercano de cerca (¿arroyo o vaguada?) · 6 lluvias simuladas · 7 agua vista por satélite."""
from __future__ import annotations

import json
import math
import textwrap
from datetime import date, datetime
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import patches  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from rasterio.plot import plotting_extent  # noqa: E402
from scipy.ndimage import uniform_filter, uniform_filter1d  # noqa: E402
from shapely.ops import nearest_points  # noqa: E402

from . import __version__  # noqa: E402
from .common import read_window  # noqa: E402
from .project import Project  # noqa: E402
from .report import f as fnum  # noqa: E402

A4 = (11.69, 8.27)                     # A4 apaisado, pulgadas
MAP = [0.03, 0.10, 0.60, 0.83]         # caja del mapa en láminas de un solo mapa
SIDE_X, SIDE_W = 0.655, 0.325          # columna derecha: leyenda + pie de figura
C_LOTE, C_AOI = "#ff1744", "#ffb300"
C_RED2, C_RED05, C_OSM = "#1e88e5", "#4fc3f7", "white"
LAB_RED2, LAB_RED05, LAB_OSM = "drenaje calculado, cuenca ≥ 2 km²", "drenaje calculado, cuenca ≥ 0,5 km²", "arroyos mapeados (OpenStreetMap)"
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


# ---------------------------------------------------------------- helpers
def _compass(dx, dy):
    ang = (math.degrees(math.atan2(dx, dy)) + 360) % 360
    return f"{COMPASS[int(((ang + 22.5) % 360) // 45)]} ({ang:.0f}°)"


def _zoom(width_m, lat, px=1100):
    z = math.log2(156543.03 * math.cos(math.radians(lat)) / (width_m / px))
    return int(min(17, max(6, round(z))))


def _wrap(text, width):
    return "\n".join(textwrap.fill(par, width) for par in text.split("\n"))


def _sample(path: Path, pts):
    with rasterio.open(path) as s:
        v = np.array([x[0] for x in s.sample(pts)], dtype=float)
        if s.nodata is not None:
            v[v == s.nodata] = np.nan
    return v


def _lst(items):
    items = [str(i) for i in items]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1] if items else "—"


class _Ctx:
    """Todo lo que las láminas comparten: proyecto, AOI, estadísticas del DEM primario, veredicto, tablas."""

    def __init__(self, p: Project):
        self.p = p; self.aoi = p.load_aoi(); self.crs = p.crs; self.lote = self.aoi["lote"]
        info = json.load(open(p.out / "terrain_primary.json"))
        self.prim = info["primary"]; self.prim_label = info["labels"][self.prim]; self.k0 = info.get("red_keys", ["05km2"])[0]
        self.T = p.data_proc / "terrain" / self.prim
        ts = pd.read_csv(p.out / "terrain_stats.csv")
        pc = [c for c in ts.columns if "(primario)" in c][0]
        self.k = dict(zip(ts["variable"], ts[pc]))
        self.alt = {c: dict(zip(ts["variable"], ts[c])) for c in ts.columns if c not in ("variable", pc)}
        vj = p.out / "veredicto.json"
        self.ev = (json.load(open(vj)) if vj.exists() else {}).get("veredicto", {})
        self.fecha = datetime.fromtimestamp(vj.stat().st_mtime).date().isoformat() if vj.exists() else date.today().isoformat()
        self.lon, self.lat = p.lot_centroid_wgs84()
        self.ext = self.lote.buffer(p.aoi_m + 700).envelope
        self.aoi_lab = f"{p.aoi_m:.0f} m"
        self.n_pix = int(float(self.k.get("n_celdas_lote", 0) or 0))
        self.osm = gpd.read_file(p.out / "osm_waterways.geojson") if (p.out / "osm_waterways.geojson").exists() else None
        self.rog = pd.read_csv(p.out / "rog_stats.csv") if (p.out / "rog_stats.csv").exists() else None
        self.sar = pd.read_csv(p.out / "sar_stats.csv") if (p.out / "sar_stats.csv").exists() else None
        self.jrc = pd.read_csv(p.out / "jrc_stats.csv") if (p.out / "jrc_stats.csv").exists() else None
        self.years = sorted({str(e.get("fecha", ""))[:4] for e in p.cfg.get("sar", {}).get("eventos", []) if e.get("fecha")})
        self.num = {}   # nombre de lámina -> número, para las referencias cruzadas del resumen

    def kf(self, key, d=2):
        return fnum(self.k.get(key), d)

    def rd(self, path, ext=None):
        return read_window(path, ext if ext is not None else self.ext)


# ---------------------------------------------------------------- dibujo común
def _page(ctx: _Ctx, title: str, box=MAP):
    fig = plt.figure(figsize=A4); fig.patch.set_facecolor("white")
    fig.text(0.03, 0.968, title, fontsize=14, fontweight="bold", va="top")
    return fig, fig.add_axes(box)


def _footer(fig, ctx: _Ctx, i: int, n: int):
    fig.add_artist(Line2D([0.03, 0.97], [0.05, 0.05], color="#ccc", lw=0.6, transform=fig.transFigure))
    fig.text(0.03, 0.036, f"Ficha de anegamiento · {ctx.p.titulo} · anega2 {__version__} · análisis {ctx.fecha} · DEM {ctx.prim_label}",
             fontsize=6.8, color="#666", va="center")
    fig.text(0.03, 0.018, "Datos: FABDEM (CC BY-NC-SA 4.0), Copernicus DEM, IGN MDE-Ar, JRC Global Surface Water, Sentinel-1 (Planetary Computer), "
             "OpenStreetMap · imagen Esri sólo para visualización", fontsize=6.8, color="#666", va="center")
    fig.text(0.97, 0.027, f"página {i} / {n}", fontsize=7.5, color="#666", va="center", ha="right")


def _basemap(ax, ctx: _Ctx, ext, source=None, px=1100):
    x0, y0, x1, y1 = ext.bounds
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal")
    try:
        import contextily as cx
        cx.add_basemap(ax, crs=ctx.crs, source=source or cx.providers.Esri.WorldImagery, zoom=_zoom(x1 - x0, ctx.lat, px), attribution=False)
        for im in ax.images:
            im.set_zorder(0)
    except Exception as e:  # noqa: BLE001
        print("  [aviso] sin mapa base:", e)
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)


def _frame(ax, ctx: _Ctx, ext, aoi_ring=True, lot=True, dark=True):
    """Marco del mapa: límites, lote, entorno, barra de escala y norte."""
    x0, y0, x1, y1 = ext.bounds
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    if aoi_ring:
        gpd.GeoSeries(ctx.aoi["aoi"], crs=ctx.crs).boundary.plot(ax=ax, color=C_AOI, lw=1.2, linestyle="--", zorder=6)
    if lot:
        gpd.GeoSeries(ctx.lote, crs=ctx.crs).boundary.plot(ax=ax, color=C_LOTE, lw=2.5, zorder=7)
    W = x1 - x0
    L = next(v for v in [50, 100, 200, 500, 1000, 2000, 5000, 10000] if v >= W / 6)
    xs = x0 + 0.04 * W; ys = y0 + 0.05 * (y1 - y0)
    fg, bg = ("white", "k") if dark else ("k", "white")
    ax.plot([xs, xs + L], [ys, ys], color=fg, lw=4, solid_capstyle="butt", zorder=8); ax.plot([xs, xs + L], [ys, ys], color=bg, lw=1.5, zorder=8)
    ax.text(xs + L / 2, ys + 0.012 * (y1 - y0), f"{L/1000:g} km" if L >= 1000 else f"{L} m", ha="center", va="bottom", fontsize=8, color=fg,
            bbox=dict(fc=bg, alpha=0.5, ec="none", pad=1.5), zorder=8)
    ax.annotate("N", xy=(x1 - 0.05 * W, y1 - 0.05 * (y1 - y0)), xytext=(x1 - 0.05 * W, y1 - 0.14 * (y1 - y0)), ha="center", color=fg,
                fontsize=11, fontweight="bold", arrowprops=dict(arrowstyle="-|>", color=fg, lw=1.5), zorder=8)


def _side(fig, handles, caption, title=None, wrap=56):
    """Columna derecha: leyenda arriba, pie de figura abajo."""
    axl = fig.add_axes([SIDE_X, MAP[1], SIDE_W, MAP[3]]); axl.axis("off")
    if handles:
        lg = axl.legend(handles=handles, loc="upper left", fontsize=8.8, title=title, title_fontsize=9.2, framealpha=1, borderaxespad=0)
        lg.get_frame().set_edgecolor("#bbb")
    fig.text(SIDE_X, MAP[1], _wrap(caption, wrap), fontsize=9.1, va="bottom", ha="left", linespacing=1.4,
             bbox=dict(fc="#f6f7f9", ec="#d0d3d8", boxstyle="round,pad=0.6"))


def _streams(ax, ctx: _Ctx, minor=False, osm=True):
    """Drenaje calculado (≥ 2 km² y opcionalmente ≥ 0,5 km²) y arroyos OSM. Devuelve handles de leyenda."""
    hs = []
    if minor and (ctx.p.out / "terrain_red_drenaje_05km2.geojson").exists():
        gpd.read_file(ctx.p.out / "terrain_red_drenaje_05km2.geojson").plot(ax=ax, color=C_RED05, lw=1.3, zorder=4)
        hs.append(Line2D([], [], color=C_RED05, lw=1.3, label=LAB_RED05))
    f2 = ctx.p.out / "terrain_red_drenaje_2km2.geojson"
    if f2.exists():
        gpd.read_file(f2).plot(ax=ax, color=C_RED2, lw=2.0, zorder=4); hs.append(Line2D([], [], color=C_RED2, lw=2.0, label=LAB_RED2))
    if osm and ctx.osm is not None and len(ctx.osm):
        ctx.osm.plot(ax=ax, color=C_OSM, lw=1.2, linestyle=":", zorder=5); hs.append(Line2D([], [], color="#777", lw=1.2, linestyle=":", label=LAB_OSM))
    return hs


def _classes(ax, arr, tr, bounds, colors, alpha=0.65):
    a = np.array(arr, dtype=float)
    cmap = ListedColormap(colors); norm = BoundaryNorm(bounds, cmap.N)
    m = np.ma.masked_invalid(np.where((a >= bounds[0]) & (a < bounds[-1]), a, np.nan))
    ax.imshow(m, extent=plotting_extent(a, tr), cmap=cmap, norm=norm, alpha=alpha, interpolation="nearest", zorder=3)
    return [patches.Patch(fc=c, ec="none", alpha=0.85, label=f"{bounds[i]:g} – {bounds[i+1]:g}") for i, c in enumerate(colors)]


def _lot_handle():
    return Line2D([], [], color=C_LOTE, lw=2.5, label="lote")


# ---------------------------------------------------------------- drenaje más cercano (lámina 5 y resumen)
def _drainage(ctx: _Ctx) -> dict | None:
    """Punto del drenaje calculado (≥ 0,5 km²) más cercano al lote, perfil perpendicular A–B de ±300 m y arroyo OSM más próximo."""
    f_ = ctx.T / f"streams_{ctx.k0}.geojson"
    if not f_.exists():
        return None
    sv = gpd.read_file(f_)
    if not len(sv):
        return None
    near = nearest_points(ctx.lote, sv.union_all())[1]
    line = sv.geometry.iloc[int(np.argmin(sv.geometry.distance(near).values))]
    d = line.project(near); p0 = line.interpolate(max(0.0, d - 20)); p1 = line.interpolate(min(line.length, d + 20))
    tx, ty = p1.x - p0.x, p1.y - p0.y; nrm = math.hypot(tx, ty) or 1.0
    nx, ny = -ty / nrm, tx / nrm
    c = ctx.lote.centroid
    if nx * (c.x - near.x) + ny * (c.y - near.y) < 0:
        nx, ny = -nx, -ny
    xs = np.arange(-300, 301, 5.0)
    d_osm, name = math.inf, None
    if ctx.osm is not None and len(ctx.osm):
        dd = ctx.osm.geometry.distance(near).values; j = int(np.argmin(dd)); d_osm = float(dd[j])
        nm = ctx.osm.iloc[j].get("name"); name = nm if isinstance(nm, str) and nm else None
    return dict(near=near, n=(nx, ny), xs=xs, pts=[(near.x + x * nx, near.y + x * ny) for x in xs],
                dist=float(ctx.lote.distance(near)), dir=_compass(near.x - c.x, near.y - c.y),
                x_lote=float(nx * (c.x - near.x) + ny * (c.y - near.y)), d_osm=d_osm, osm_name=name)


def _profile(ctx: _Ctx, dr: dict) -> dict | None:
    """Perfil A–B en los DEM disponibles, diferencia Sentinel-1 (escena más húmeda − referencia seca) y clasificación."""
    prof = {}
    for key in [ctx.prim] + list(ctx.alt):
        f_ = ctx.p.data_proc / "terrain" / key / "dem.tif"
        if f_.exists():
            prof[key] = _sample(f_, dr["pts"])
    if ctx.prim not in prof:
        return None
    z, x = prof[ctx.prim], dr["xs"]
    z0 = float(np.nanmin(z[np.abs(x) <= 30])); zs = float(np.nanmedian(z[(np.abs(x) >= 100) & (np.abs(x) <= 200)]))
    prof_cm = max(0.0, 100 * (zs - z0))
    s1 = None
    if ctx.sar is not None and "pct_500m_caida_3dB" in ctx.sar:
        ev = ctx.sar[(ctx.sar.evento != "referencia_seca") & ctx.sar.pct_500m_caida_3dB.notna()]
        ref = ctx.sar[ctx.sar.evento == "referencia_seca"]
        if len(ev) and len(ref):
            r = ev.iloc[int(np.argmax(ev.pct_500m_caida_3dB.values))]
            fs = ctx.p.data_proc / "s1" / f"{r.escena}_VV_db.tif"; fr = ctx.p.data_proc / "s1" / f"{ref.iloc[0].escena}_VV_db.tif"
            if fs.exists() and fr.exists():
                dif = _sample(fs, dr["pts"]) - _sample(fr, dr["pts"])
                s1 = dict(fecha=str(r.fecha), ref=str(ref.iloc[0].fecha), dif=uniform_filter1d(np.nan_to_num(dif, nan=0.0), 7))
    if dr["d_osm"] <= 60:
        tipo, corto = "arroyo", "un arroyo mapeado en OpenStreetMap" + (f" ({dr['osm_name']})" if dr["osm_name"] else "")
    elif prof_cm >= 50:
        tipo, corto = "cauce", "un cauce marcado que OpenStreetMap no tiene mapeado"
    else:
        tipo, corto = "vaguada", "una vaguada (línea de escurrimiento calculada, sin cauce ni arroyo mapeado)"
    return dict(prof=prof, prof_cm=prof_cm, s1=s1, tipo=tipo, corto=corto)


# ---------------------------------------------------------------- láminas
def _lam_ubicacion(ctx: _Ctx, n: int, dr):
    import contextily as cx
    ext = ctx.lote.centroid.buffer(ctx.p.hidro_m * 1.15).envelope
    fig, ax = _page(ctx, f"{n} · Dónde está el lote en la región")
    _basemap(ax, ctx, ext, source=cx.providers.Esri.WorldTopoMap)
    hs = []
    f2 = ctx.p.out / "terrain_red_drenaje_2km2.geojson"
    if f2.exists():
        gpd.read_file(f2).plot(ax=ax, color=C_RED05, lw=1.0, alpha=0.9, zorder=3); hs.append(Line2D([], [], color=C_RED05, lw=1.0, label=LAB_RED2))
    d_osm_lote, name_lote = None, None
    if ctx.osm is not None and len(ctx.osm):
        ctx.osm.plot(ax=ax, color="#0d47a1", lw=1.4, zorder=4); hs.append(Line2D([], [], color="#0d47a1", lw=1.4, label=LAB_OSM))
        dd = ctx.osm.geometry.distance(ctx.lote).values; j = int(np.argmin(dd)); d_osm_lote = float(dd[j])
        nm = ctx.osm.iloc[j].get("name"); name_lote = nm if isinstance(nm, str) and nm else "un arroyo sin nombre"
    gpd.GeoSeries(ctx.aoi["hidro"], crs=ctx.crs).boundary.plot(ax=ax, color="#1565c0", lw=1.5, zorder=5)
    gpd.GeoSeries(ctx.aoi["aoi"], crs=ctx.crs).boundary.plot(ax=ax, color=C_AOI, lw=2, zorder=6)
    c = ctx.lote.centroid; ax.plot(c.x, c.y, marker="*", color=C_LOTE, ms=16, mec="k", zorder=7)
    hs += [Line2D([], [], marker="*", color=C_LOTE, mec="k", ms=12, lw=0, label="lote"),
           Line2D([], [], color=C_AOI, lw=2, label=f"entorno de {ctx.aoi_lab} (láminas siguientes)"),
           Line2D([], [], color="#1565c0", lw=1.5, label=f"área de análisis hidrológico ({ctx.p.hidro_m/1000:g} km)")]
    _frame(ax, ctx, ext, aoi_ring=False, lot=False, dark=False)
    cap = (f"El lote está en {ctx.lat:.6f}, {ctx.lon:.6f} (WGS84), con {fnum(ctx.lote.area, 0)} m² de superficie. "
           + (f"El arroyo mapeado más cercano es {name_lote}, a {fnum(d_osm_lote, 0)} m. " if d_osm_lote is not None else "")
           + (f"El drenaje calculado más cercano está a {fnum(dr['dist'], 0)} m al {dr['dir']} (lámina {ctx.num.get('corredor', '—')}). " if dr else "")
           + f"Dentro del círculo azul se calculó el drenaje y el HAND; el naranja es el entorno de {ctx.aoi_lab} que muestran las láminas siguientes. "
           "Mapa base: Esri World Topo.")
    _side(fig, hs, cap)
    return fig, "01_ubicacion.png"


def _lam_drenaje(ctx: _Ctx, n: int, dr, prof):
    k = ctx.k
    fig, ax = _page(ctx, f"{n} · Dónde está el lote y hacia dónde va el agua"); _basemap(ax, ctx, ctx.ext)
    hs = _streams(ax, ctx, minor=True)
    f_ = ctx.p.out / "terrain_cuenca_lote.geojson"
    if f_.exists():
        gpd.read_file(f_).plot(ax=ax, fc="#76ff03", ec="#64dd17", alpha=0.35, lw=1.5, zorder=4)
        hs.append(patches.Patch(fc="#76ff03", ec="#64dd17", alpha=0.5, label="cuenca que aporta agua al lote"))
    f_ = ctx.p.out / "terrain_flowpath_lote.geojson"
    if f_.exists():
        gpd.read_file(f_).plot(ax=ax, color="#e040fb", lw=3, zorder=5); hs.append(Line2D([], [], color="#e040fb", lw=3, label="camino del agua que sale del lote"))
    hs += [_lot_handle(), Line2D([], [], color=C_AOI, lw=1.2, linestyle="--", label=f"entorno de {ctx.aoi_lab}")]
    _frame(ax, ctx, ctx.ext)
    cuenca = float(k.get("cuenca_todo_el_lote_ha", 0) or 0)
    que = f" Esa línea es {prof['corto']} (lámina {ctx.num.get('corredor', '—')})." if prof else ""
    cap = (f"El agua que cae en el lote sale hacia {k.get('direccion_salida_flowpath', '—')} y llega a la línea de drenaje más cercana a "
           f"{ctx.kf('dist_euclid_red_05km2_m', 0)} m en línea recta ({ctx.kf('dist_flujo_red_05km2_m', 0)} m siguiendo el terreno).{que} "
           f"La cuenca que aporta agua al lote es de {ctx.kf('cuenca_celda_mas_baja_ha')} a {ctx.kf('cuenca_todo_el_lote_ha')} ha: "
           f"{'prácticamente no recibe agua de los vecinos' if cuenca < 5 else 'recibe escurrimiento de arriba'}. "
           f"Las líneas azules son por dónde escurre el agua según el DEM {ctx.prim_label}; no siempre son arroyos con cauce. "
           "Los arroyos mapeados en OpenStreetMap van punteados.")
    _side(fig, hs, cap)
    return fig, "02_lote_y_drenaje.png"


def _lam_cotas(ctx: _Ctx, n: int):
    k = ctx.k
    dem, tr = ctx.rd(ctx.T / "dem.tif")
    z = uniform_filter(np.nan_to_num(dem, nan=np.nanmean(dem)), 3)
    fig, ax = _page(ctx, f"{n} · Cotas del terreno (curvas cada 0,5 m)"); _basemap(ax, ctx, ctx.ext)
    e = plotting_extent(dem, tr)
    xs = np.linspace(e[0], e[1], dem.shape[1]); ys = np.linspace(e[3], e[2], dem.shape[0])
    zmin, zmax = float(k.get("z_min_lote")), float(k.get("z_max_lote"))
    ax.contourf(xs, ys, z, levels=[float(np.nanmin(z)) - 1, zmin], colors=["#2979ff"], alpha=0.30, zorder=2)
    lv = np.arange(math.floor(np.nanmin(z) * 2) / 2, math.ceil(np.nanmax(z) * 2) / 2 + 0.5, 0.5)
    cs = ax.contour(xs, ys, z, levels=lv, colors="#ffee58", linewidths=0.8, zorder=4); ax.clabel(cs, fmt="%.1f", fontsize=7, colors="#ffee58")
    hs = [Line2D([], [], color="#c6a700", lw=1.2, label="curvas de nivel cada 0,5 m (m snm)"),
          patches.Patch(fc="#2979ff", alpha=0.35, label=f"terreno más bajo que el lote (< {fnum(zmin)} m)"), _lot_handle()]
    _frame(ax, ctx, ctx.ext)
    alts = " · ".join(f"{d.get('dem_label')}: {fnum(d.get('z_min_lote'))} – {fnum(d.get('z_max_lote'))} m" for d in ctx.alt.values())
    cap = (f"El lote está entre {fnum(zmin)} y {fnum(zmax)} m sobre el nivel del mar (media {ctx.kf('z_mean_lote')} m) según el DEM {ctx.prim_label}, "
           f"datum {k.get('vdatum', '—')}. En azul, todo lo que está más bajo que el punto más bajo del lote: por ahí se extiende el agua antes de llegar. "
           f"El punto del drenaje más cercano está a cota {ctx.kf('z_cauce_mas_cercano')} m.\n"
           f"Las cotas absolutas tienen 1 – 2 m de error y otros modelos dan otra cosa ({alts}) porque ven copas y techos: "
           "sirven para comparar puntos entre sí, no como cota oficial. Confirmar con nivelación antes de fijar la cota de piso. "
           "Los 'cerritos' de curvas apretadas sobre galpones o arboledas son restos de edificios y copas, no lomas.")
    _side(fig, hs, cap)
    return fig, "03_cotas.png"


def _lam_hand(ctx: _Ctx, n: int):
    hand, trh = ctx.rd(ctx.T / f"hand_{ctx.k0}.tif")
    fig, ax = _page(ctx, f"{n} · Cuánto tendría que subir el agua desde el drenaje para llegar"); _basemap(ax, ctx, ctx.ext)
    hs = _classes(ax, hand, trh, [0, 0.5, 1, 2, 3], ["#b71c1c", "#e53935", "#fb8c00", "#fdd835"])
    for h_, lab in zip(hs, ["menos de 0,5 m (drenaje y su borde)", "0,5 – 1 m (muy bajo)", "1 – 2 m (bajo)", "2 – 3 m (medio)"]):
        h_.set_label(lab)
    hs.append(patches.Patch(fc="none", ec="#999", label="sin color: más de 3 m (alto)")); hs += _streams(ax, ctx); hs.append(_lot_handle())
    _frame(ax, ctx, ctx.ext)
    cap = (f"Cada color indica cuántos metros tendría que subir el agua desde la línea de drenaje más cercana, siguiendo el camino del agua, para llegar a ese punto (HAND). "
           f"En el lote son {ctx.kf('hand_min_lote')} a {ctx.kf('hand_max_lote')} m. En el entorno de {ctx.aoi_lab}, el {ctx.kf('pct_aoi_hand_le1', 0)} % está a menos de 1 m y el "
           f"{ctx.kf('pct_aoi_hand_le2', 0)} % a menos de 2 m: es una llanura, casi todo está bajo. Lo que importa es la posición relativa del lote. "
           f"Veredicto por desborde del drenaje: {ctx.ev.get('desborde', {}).get('nivel', '—')}.")
    _side(fig, hs, cap, "altura sobre el drenaje (HAND)")
    return fig, "04_altura_sobre_el_drenaje.png"


def _lam_corredor(ctx: _Ctx, n: int, dr, prof):
    k = ctx.k; near = dr["near"]; x = dr["xs"]
    ext = near.buffer(360).envelope
    fig = plt.figure(figsize=A4); fig.patch.set_facecolor("white")
    fig.text(0.03, 0.968, f"{n} · El drenaje más cercano de cerca: ¿arroyo o vaguada?", fontsize=14, fontweight="bold", va="top")
    fig.text(0.03, 0.928, f"A {fnum(dr['dist'], 0)} m al {dr['dir']} del lote el modelo marca una línea de drenaje. Es {prof['corto']}.", fontsize=10.5, va="top", color="#333")
    # --- mapa
    ax = fig.add_axes([0.03, 0.26, 0.44, 0.60]); _basemap(ax, ctx, ext)
    hand, trh = ctx.rd(ctx.T / f"hand_{ctx.k0}.tif", ext)
    ax.imshow(np.ma.masked_invalid(np.where(hand <= 0.5, 1.0, np.nan)), extent=plotting_extent(hand, trh), cmap=ListedColormap(["#ef5350"]), alpha=0.35,
              interpolation="nearest", zorder=2)
    dem, tr = ctx.rd(ctx.T / "dem.tif", ext); z = uniform_filter(np.nan_to_num(dem, nan=np.nanmean(dem)), 3)
    e = plotting_extent(dem, tr); xs = np.linspace(e[0], e[1], dem.shape[1]); ys = np.linspace(e[3], e[2], dem.shape[0])
    lv = np.arange(math.floor(np.nanmin(z) * 4) / 4, math.ceil(np.nanmax(z) * 4) / 4 + 0.25, 0.25)
    cs = ax.contour(xs, ys, z, levels=lv, colors="#ffee58", linewidths=0.7, zorder=3); ax.clabel(cs, fmt="%.2f", fontsize=6, colors="#ffee58")
    hs = _streams(ax, ctx, minor=True)
    A, B = dr["pts"][-1], dr["pts"][0]
    ax.plot([B[0], A[0]], [B[1], A[1]], color="#ff9800", lw=2.2, zorder=6); ax.plot([B[0], A[0]], [B[1], A[1]], color="white", lw=0.8, zorder=6)
    for (px, py), lab in [(A, "A"), (B, "B")]:
        ax.text(px, py, lab, color="white", fontsize=10, fontweight="bold", ha="center", va="center", zorder=8, bbox=dict(boxstyle="circle,pad=0.3", fc="#ff9800", ec="white"))
    ax.plot(near.x, near.y, "o", color="#ff9800", mec="white", ms=8, zorder=7)
    hs += [patches.Patch(fc="#ef5350", alpha=0.5, label="franja a menos de 0,5 m sobre la línea de drenaje"),
           Line2D([], [], color="#c6a700", lw=1, label=f"curvas de nivel cada 0,25 m ({ctx.prim})"),
           Line2D([], [], color="#ff9800", lw=2.2, label="perfil A–B (600 m)"), _lot_handle()]
    _frame(ax, ctx, ext, aoi_ring=False)
    ax.set_title("Zoom sobre la línea de drenaje (imagen Esri)", fontsize=10.5, loc="left", pad=6)
    axl = fig.add_axes([0.03, 0.17, 0.44, 0.08]); axl.axis("off")
    lg = axl.legend(handles=hs, loc="upper left", fontsize=7.4, ncol=2, framealpha=1, borderaxespad=0, columnspacing=1.0); lg.get_frame().set_edgecolor("#bbb")
    # --- perfil
    axp = fig.add_axes([0.54, 0.26, 0.40, 0.60])
    cols = {ctx.prim: "#1565c0"}; others = ["#ef6c00", "#2e7d32", "#6a1b9a"]
    for i, key in enumerate([kk for kk in prof["prof"] if kk != ctx.prim]):
        cols[key] = others[i % len(others)]
    for key, zz in prof["prof"].items():
        lab = ctx.prim_label if key == ctx.prim else ctx.alt.get(key, {}).get("dem_label", key)
        axp.plot(x, zz, color=cols[key], lw=2.6 if key == ctx.prim else 1.3, label=lab + (" (primario)" if key == ctx.prim else ""), zorder=4 if key == ctx.prim else 3)
    axp.axvline(0, color="#1e88e5", lw=1.4, zorder=2)
    axp.text(0, 0.015, " línea de drenaje", transform=axp.get_xaxis_transform(), va="bottom", fontsize=8, color="#1e88e5",
             bbox=dict(fc="white", ec="none", alpha=0.7, pad=1))
    zmin_lote = float(k.get("z_min_lote"))
    axp.axhline(zmin_lote, color=C_LOTE, lw=1.2, linestyle="--", zorder=2)
    axp.text(x[0] + 5, zmin_lote, f" punto más bajo del lote ({fnum(zmin_lote)} m)", va="bottom", fontsize=7.8, color=C_LOTE,
             bbox=dict(fc="white", ec="none", alpha=0.7, pad=1))
    if abs(dr["x_lote"]) <= 320:
        axp.axvspan(max(x[0], dr["x_lote"] - 25), min(x[-1], dr["x_lote"] + 25), color=C_LOTE, alpha=0.12, zorder=1)
    axp.set_xlabel("distancia perpendicular a la línea de drenaje (m)   B ←  → A (lado del lote)", fontsize=8.5)
    axp.set_ylabel("cota (m snm)", fontsize=9); axp.tick_params(labelsize=8); axp.grid(alpha=0.3)
    y0_, y1_ = axp.get_ylim(); axp.set_ylim(y0_, y1_ + 0.50 * (y1_ - y0_))   # aire arriba para la leyenda
    hl, ll_ = axp.get_legend_handles_labels()
    if prof["s1"] is not None:
        ax2 = axp.twinx(); ax2.plot(x, prof["s1"]["dif"], color="#555", lw=1, linestyle="--", label=f"radar Sentinel-1 {prof['s1']['fecha']} − ref. seca (dB)")
        ax2.set_ylabel("Δ dB radar (negativo = más húmedo / agua)", fontsize=8); ax2.tick_params(labelsize=8); ax2.axhline(-3, color="#999", lw=0.6, linestyle=":")
        h2, l2 = ax2.get_legend_handles_labels(); hl += h2; ll_ += l2
        b0, b1 = ax2.get_ylim(); ax2.set_ylim(b0, b1 + 0.50 * (b1 - b0))
    axp.legend(hl, ll_, loc="upper left", fontsize=7.6, framealpha=1)
    axp.text(0.99, 0.985, "hacia el lote →", transform=axp.transAxes, ha="right", va="top", fontsize=8.5, color=C_LOTE, fontweight="bold")
    axp.set_title("Perfil transversal A–B en cada DEM", fontsize=10.5, loc="left", pad=6)
    # --- pie
    pc = fnum(prof["prof_cm"], 0)
    if prof["tipo"] == "vaguada":
        que = (f"En la imagen no hay cauce visible y OpenStreetMap no tiene ningún arroyo mapeado a menos de {fnum(dr['d_osm'], 0)} m. "
               f"El perfil muestra una vaguada de unos {pc} cm de profundidad en 300 m: es por donde escurre el agua en una lluvia fuerte, no un arroyo con barranca. "
               "No hay un 'desborde' clásico: el agua que baja se extiende en una franja ancha y poco profunda. La nivelación en campo se hace contra el punto más bajo de esa franja.")
    elif prof["tipo"] == "cauce":
        que = (f"OpenStreetMap no tiene ningún arroyo mapeado a menos de {fnum(dr['d_osm'], 0)} m, pero el perfil muestra un cauce de unos {pc} cm de profundidad: "
               "hay un canal o zanja que conviene relevar en campo (fondo, barranca y hacia dónde va).")
    else:
        que = (f"Coincide con {dr['osm_name'] or 'un arroyo'} mapeado en OpenStreetMap (a {fnum(dr['d_osm'], 0)} m); el perfil muestra un cauce de unos {pc} cm. "
               "La nivelación en campo se hace contra el fondo y la barranca de ese arroyo.")
    s1txt = (f" La línea gris punteada es la humedad que vio el radar (Sentinel-1 {prof['s1']['fecha']} menos la referencia seca {prof['s1']['ref']}): "
             "valores negativos = suelo más húmedo o agua; por debajo de −3 dB suele haber agua." if prof["s1"] is not None else "")
    cap = (f"A {fnum(dr['dist'], 0)} m al {dr['dir']} del lote el DEM marca una línea de drenaje con más de 0,5 km² de cuenca; es la que usan el HAND y el veredicto. {que}"
           f" Las curvas rojas de los otros DEM muestran cuánto cambia el relieve entre modelos.{s1txt}")
    fig.text(0.03, 0.065, _wrap(cap, 168), fontsize=8.6, va="bottom", linespacing=1.35, bbox=dict(fc="#f6f7f9", ec="#d0d3d8", boxstyle="round,pad=0.5"))
    return fig, "05_drenaje_mas_cercano.png"


def _lam_lluvia(ctx: _Ctx, n: int):
    rog = ctx.rog
    picks = [s for s in ["P100_24h", "P150_24h_sat", "P200_24h"] if (ctx.p.data_proc / "rog" / f"{s}_hmax_dom.tif").exists() and (rog.escenario == s).any()][:3]
    if not picks:
        return None
    ext = ctx.lote.buffer(ctx.p.aoi_m + 250).envelope
    fig = plt.figure(figsize=A4); fig.patch.set_facecolor("white")
    fig.text(0.03, 0.968, f"{n} · Lluvias extremas simuladas: dónde se junta el agua", fontsize=14, fontweight="bold", va="top")
    gap = 0.015; w = (0.94 - gap * (len(picks) - 1)) / len(picks); hgt = min(0.40, w * A4[0] / A4[1])   # paneles cuadrados
    hs = None
    for i, s in enumerate(picks):
        r = rog[rog.escenario == s].iloc[0]
        ax = fig.add_axes([0.03 + i * (w + gap), 0.885 - hgt, w, hgt])
        h, trr = ctx.rd(ctx.p.data_proc / "rog" / f"{s}_hmax_dom.tif", ext); _basemap(ax, ctx, ext)
        hs_ = _classes(ax, h, trr, [0.05, 0.2, 0.5, 5], ["#90caf9", "#1565c0", "#0d47a1"], alpha=0.75)
        for h_, lab in zip(hs_, ["5 – 20 cm", "20 – 50 cm", "más de 50 cm"]):
            h_.set_label(lab)
        if ctx.osm is not None and len(ctx.osm):
            ctx.osm.plot(ax=ax, color=C_OSM, lw=1.0, linestyle=":", zorder=5)
        _frame(ax, ctx, ext)
        lab = f"{int(r['P_mm'])} mm en {r['dur_h']:g} h" + (" · suelo saturado" if s.endswith("_sat") else "")
        ax.set_title(lab, fontsize=11, loc="left", pad=6)
        npx = int(round(float(r["pct_lote_gt5cm"]) * ctx.n_pix / 100))
        ax.text(0.02, 0.98, f"lote: máx {fnum(r['hmax_lote_m']*100, 0)} cm · {npx} de {ctx.n_pix} píxeles con > 5 cm · {fnum(r['dur_max_lote_h'], 1)} h",
                transform=ax.transAxes, va="top", fontsize=8.3, color="white", bbox=dict(fc="black", alpha=0.55, ec="none"))
        hs = hs_ + [Line2D([], [], color="#777", lw=1.0, linestyle=":", label=LAB_OSM), _lot_handle(), Line2D([], [], color=C_AOI, lw=1.2, linestyle="--", label=f"entorno de {ctx.aoi_lab}")]
    top = 0.885 - hgt - 0.03
    axl = fig.add_axes([0.03, 0.07, 0.20, top - 0.07]); axl.axis("off")
    lg = axl.legend(handles=hs, loc="upper left", fontsize=8.5, title="lámina máxima de agua", title_fontsize=9, framealpha=1, borderaxespad=0); lg.get_frame().set_edgecolor("#bbb")
    # tabla con todos los escenarios
    rows = []
    for _, r in rog.iterrows():
        npx = int(round(float(r["pct_lote_gt5cm"]) * ctx.n_pix / 100))
        rows.append([f"{int(r['P_mm'])} mm / {r['dur_h']:g} h" + (" · saturado" if str(r["escenario"]).endswith("_sat") else ""),
                     fnum(r["hmax_lote_m"] * 100, 0), f"{npx} de {ctx.n_pix}", fnum(r["dur_max_lote_h"], 1),
                     fnum(r["pct_aoi_gt5cm"], 0), fnum(r["pct_aoi_gt20cm"], 0), fnum(r["hmax_aoi_m"] * 100, 0)])
    axt = fig.add_axes([0.27, top - 0.02 - 0.025 * (len(rows) + 2), 0.70, 0.025 * (len(rows) + 2)]); axt.axis("off")
    tb = axt.table(cellText=rows, colLabels=["lluvia", "lote\nmáx (cm)", "lote\npíxeles > 5 cm", "lote\nhoras > 5 cm",
                                             f"entorno {ctx.aoi_lab}\n% > 5 cm", f"entorno {ctx.aoi_lab}\n% > 20 cm", f"entorno {ctx.aoi_lab}\nmáx (cm)"],
                   colWidths=[0.22, 0.11, 0.14, 0.13, 0.14, 0.13, 0.13], loc="upper left", cellLoc="center", colLoc="center", bbox=[0, 0, 1, 1])
    tb.auto_set_font_size(False); tb.set_fontsize(8)
    for (ri, ci), cell in tb.get_celld().items():
        cell.set_edgecolor("#d0d3d8")
        if ri == 0:
            cell.set_text_props(fontweight="bold"); cell.set_facecolor("#eceff1"); cell.set_height(cell.get_height() * 2)
        elif ci == 0:
            cell.set_text_props(ha="left"); cell.get_text().set_x(0.03)
    cap = ("Simulación 2D (Landlab OverlandFlow) de la lluvia cayendo sobre el terreno, con infiltración. Muestra dónde se acumula agua y cuánto; no incluye la crecida "
           f"que puede venir por el drenaje desde fuera del dominio de ±{ctx.p.buffers.get('lluvia_m', 5000)/1000:g} km. Píxeles de 30 m: no ve zanjas ni cunetas. "
           f"El lote ocupa {ctx.n_pix} píxeles, así que cada píxel con agua es un {fnum(100/ctx.n_pix, 0)} % del lote. "
           "Sin período de retorno (no hay curva IDF local): 100 mm en 24 h es una tormenta fuerte, 200 mm un evento extremo. "
           "'Saturado' repite la lluvia con el suelo ya lleno de agua (napa alta o lluvias previas).")
    fig.text(0.27, 0.07, _wrap(cap, 132), fontsize=8.4, va="bottom", linespacing=1.35, bbox=dict(fc="#f6f7f9", ec="#d0d3d8", boxstyle="round,pad=0.5"))
    return fig, "06_lluvias_simuladas.png"


def _sat_numbers(ctx: _Ctx):
    lote_occ = float(ctx.jrc.iloc[0]["occ>0 %"]) if ctx.jrc is not None else float("nan")
    n_s1, s1_max, sin_cob = 0, float("nan"), 0
    if ctx.sar is not None:
        ev = ctx.sar[ctx.sar.evento != "referencia_seca"]
        n_s1 = int(ev.pct_agua_lote.notna().sum()); sin_cob = int((ev.escena == "SIN COBERTURA").sum())
        s1_max = float(ev.pct_agua_lote.max()) if n_s1 else float("nan")
    return lote_occ, n_s1, s1_max, sin_cob


def _lam_satelite(ctx: _Ctx, n: int):
    jrc_path = ctx.p.data_proc / "jrc" / "occurrence_hidro.tif"
    if not jrc_path.exists():
        return None
    j, trj = ctx.rd(jrc_path); j = np.where(j == 255, np.nan, j)
    fig, ax = _page(ctx, f"{n} · Agua vista por satélite, 1984-2021 (Landsat) y por radar en los eventos recientes"); _basemap(ax, ctx, ctx.ext)
    hs = _classes(ax, np.where(j > 0, j, np.nan), trj, [1, 10, 50, 101], ["#ffab91", "#ab47bc", "#1a237e"], alpha=0.8)
    for h_, lab in zip(hs, ["agua en 1 – 10 % de las imágenes", "10 – 50 %", "más del 50 % (laguna permanente)"]):
        h_.set_label(lab)
    hs += _streams(ax, ctx); hs.append(_lot_handle())
    _frame(ax, ctx, ctx.ext)
    lote_occ, n_s1, s1_max, sin_cob = _sat_numbers(ctx)
    cap = (f"Landsat (30 m, 1984-2021): {'nunca vio agua sobre el lote' if lote_occ == 0 else f'vio agua en el {fnum(lote_occ, 1)} % del lote'}. "
           f"Radar Sentinel-1 (10 m): {n_s1} escenas alrededor de los eventos de lluvia de {_lst(ctx.years)}, "
           f"{'ninguna con agua abierta sobre el lote' if s1_max == 0 else f'hasta el {fnum(s1_max, 0)} % del lote con agua'}"
           + (f"; {sin_cob} evento sin cobertura radar" if sin_cob else "") + ". "
           "Los satélites no ven agua bajo árboles ni la que dura menos que el intervalo entre pasadas (6-12 días), y el radar confunde suelo desnudo mojado con agua. "
           "Que no hayan visto agua no prueba que no se anegue: prueba que no hubo agua abierta durante días.")
    _side(fig, hs, cap, "Landsat (JRC Global Surface Water)")
    return fig, "07_agua_satelite.png"


# ---------------------------------------------------------------- resumen
def _row(fig, y, label, value, x_val=0.20, wrap=62, fs=9.4, lh=0.0225):
    txt = _wrap(value, wrap); n = txt.count("\n") + 1
    fig.text(0.03, y, label, fontsize=fs, fontweight="bold", va="top")
    fig.text(x_val, y, txt, fontsize=fs, va="top", linespacing=1.3)
    return y - lh * n - 0.012


def _resumen(ctx: _Ctx, dr, prof):
    k = ctx.k; ev = ctx.ev; g = ev.get("global", "—"); ll = ev.get("lluvia_local", {}); dd = ev.get("desborde", {})
    fig = plt.figure(figsize=A4); fig.patch.set_facecolor("white")
    fig.text(0.03, 0.958, f"Ficha de anegamiento · {ctx.p.titulo}", fontsize=17, fontweight="bold", va="top")
    col = "#b71c1c" if g in ("ALTO", "MEDIO") else "#e65100" if g == "MEDIO-BAJO" else "#2e7d32"
    fig.text(0.03, 0.90, f"Riesgo {g}   ·   por lluvia local: {ll.get('nivel', '—')}   ·   por desborde del drenaje: {dd.get('nivel', '—')}",
             fontsize=12.5, va="top", color=col)
    fig.text(0.03, 0.865, "Veredicto por reglas explícitas sobre un DEM de 30 m, sin calibración (informe completo: README.md del proyecto). Orientativo: se confirma en campo.",
             fontsize=8.3, color="#555", va="top")
    # --- columna izquierda: números clave
    y = 0.825
    y = _row(fig, y, "Ubicación", f"{ctx.lat:.6f}, {ctx.lon:.6f} (WGS84) · superficie {fnum(ctx.lote.area, 0)} m² · el lote toca {ctx.n_pix} píxeles de 30 m")
    alts = " · ".join(f"{d.get('dem_label')}: {fnum(d.get('z_min_lote'))} – {fnum(d.get('z_max_lote'))} m" for d in ctx.alt.values())
    y = _row(fig, y, "Cota del lote", f"{ctx.kf('z_min_lote')} – {ctx.kf('z_max_lote')} m snm según {ctx.prim_label}, datum {k.get('vdatum', '—')}. "
             + (f"Otros modelos: {alts}. " if alts else "") + "Las cotas absolutas tienen 1 – 2 m de error: usar sólo diferencias; la cota oficial sale de la nivelación.")
    corto = prof["corto"] if prof else "línea de drenaje calculada"
    dist_txt = (f"a {fnum(dr['dist'], 0)} m al {dr['dir']}" if dr else f"a {ctx.kf('dist_euclid_red_05km2_m', 0)} m")
    y = _row(fig, y, "Drenaje más cercano", f"{corto}; {dist_txt} en línea recta, {ctx.kf('dist_flujo_red_05km2_m', 0)} m por el camino del agua; "
             f"cota {ctx.kf('z_cauce_mas_cercano')} m (lámina {ctx.num.get('corredor', '—')})")
    y = _row(fig, y, "Desnivel lote → drenaje", f"{ctx.kf('hand_min_lote')} m sobre el punto del drenaje al que llega el agua del lote (HAND: es el valor que usa el veredicto) · "
             f"{ctx.kf('salto_lote_min_vs_cauce_m')} m sobre el punto del drenaje más cercano en línea recta")
    y = _row(fig, y, "Pendiente / escurre hacia", f"{ctx.kf('slope_mean_lote_pct')} % / {k.get('direccion_salida_flowpath', '—')}")
    dep = f"depresión cerrada en el lote de {ctx.kf('sink_depth_max_lote_m')} m" if str(k.get("lote_intersecta_depresion")) == "True" else "sin depresión cerrada en el lote"
    cuenca = float(k.get("cuenca_todo_el_lote_ha", 0) or 0)
    y = _row(fig, y, "Agua propia y de vecinos", f"{dep} · cuenca aportante {ctx.kf('cuenca_celda_mas_baja_ha')} – {ctx.kf('cuenca_todo_el_lote_ha')} ha "
             f"({'prácticamente sólo recibe la lluvia que le cae' if cuenca < 5 else 'recibe escurrimiento de arriba'})")
    lote_occ, n_s1, s1_max, sin_cob = _sat_numbers(ctx)
    if ctx.jrc is not None and lote_occ == 0 and (s1_max == 0 or math.isnan(s1_max)):
        sat = f"ninguna sobre el lote: Landsat 1984-2021 y {n_s1} escenas de radar Sentinel-1 alrededor de las lluvias de {_lst(ctx.years)}" + (f" ({sin_cob} evento sin cobertura)" if sin_cob else "")
    else:
        sat = f"ver lámina {ctx.num.get('satelite', '—')}"
    y = _row(fig, y, "Agua vista por satélite", sat)
    if ctx.rog is not None:
        for s, lab, pre in [("P100_24h", "100 mm / 24 h", ""), ("P150_24h_sat", "150 mm / 24 h", "con suelo saturado: "), ("P200_24h", "200 mm / 24 h", "")]:
            if (ctx.rog.escenario == s).any():
                r = ctx.rog[ctx.rog.escenario == s].iloc[0]; npx = int(round(float(r["pct_lote_gt5cm"]) * ctx.n_pix / 100))
                y = _row(fig, y, f"Lluvia {lab}", f"{pre}máx {fnum(r['hmax_lote_m']*100, 0)} cm en el lote, {npx} de {ctx.n_pix} píxeles con más de 5 cm durante "
                         f"{fnum(r['dur_max_lote_h'], 1)} h · entorno: {fnum(r['pct_aoi_gt5cm'], 0)} % con más de 5 cm")
    # --- columna derecha: qué hacer
    X = 0.615; yy = 0.825
    fig.text(X, yy, "Qué hacer con esto", fontsize=11, fontweight="bold", va="top"); yy -= 0.04
    if prof and prof["tipo"] == "vaguada":
        niv = (f"Nivelar en campo el punto más bajo del lote contra el punto más bajo de la vaguada ({fnum(dr['dist'], 0)} m al {dr['dir']}): el DEM estima "
               f"{ctx.kf('hand_min_lote')} m de desnivel. No hay cauce con barranca: es una franja ancha por donde escurre el agua.")
    else:
        niv = (f"Nivelar en campo el punto más bajo del lote contra el fondo y la barranca del {'arroyo' if prof and prof['tipo'] == 'arroyo' else 'cauce'} "
               f"({dist_txt}): el DEM estima {ctx.kf('hand_min_lote')} m de desnivel.")
    for t in [niv,
              "Cota de piso: al menos 0,5 m sobre el terreno natural y por encima de la cota de crecida que surja de esa nivelación.",
              "Alcantarillas y terraplenes: revisar los de caminos, rutas y vías entre el lote y el drenaje; un terraplén del lado del lote puede actuar de dique.",
              f"Vecinos y marcas: preguntar por las lluvias de {_lst(ctx.years)} y por la napa; buscar marcas de agua en postes, alambrados y troncos.",
              "Napa: en época húmeda, un pozo de 1 – 1,5 m para ver a qué profundidad está. En la llanura pampeana el anegamiento por napa alta es tan frecuente como el desborde.",
              "Recorrer el lote y el entorno después de una lluvia fuerte: el DEM de 30 m no ve zanjas, cunetas ni bajos menores que un píxel.",
              "Este diagnóstico es a 30 m de píxel, sin calibración ni microrrelieve: orientativo, no reemplaza el relevamiento topográfico."]:
        txt = _wrap("• " + t, 66); nl = txt.count("\n") + 1
        fig.text(X, yy, txt, fontsize=9.1, va="top", linespacing=1.3); yy -= 0.021 * nl + 0.011
    yy -= 0.01
    fig.text(X, yy, "Contenido", fontsize=11, fontweight="bold", va="top"); yy -= 0.038
    lams = " · ".join(f"{v} {lab}" for lab, v in sorted(((lab, v) for v, lab in ctx.num_labels.items()), key=lambda t: t[1]))
    txt = _wrap(f"Láminas: {lams}. Además: KML para Google Earth ({ctx.p.name}.kml), informe completo con las reglas del veredicto (README.md) y visor web (anega2 serve).", 66)
    fig.text(X, yy, txt, fontsize=8.8, va="top", linespacing=1.3, color="#333")
    return fig, "00_resumen.png"


# ---------------------------------------------------------------- run
def run(p: Project) -> dict:
    ctx = _Ctx(p)
    outdir = p.out / "ficha"; outdir.mkdir(exist_ok=True)
    for old in outdir.glob("*.png"):           # la carpeta es de esta fase: sin láminas viejas
        old.unlink()
    dr = _drainage(ctx); prof = _profile(ctx, dr) if dr else None
    plan = [("ubicacion", "ubicación", lambda n: _lam_ubicacion(ctx, n, dr)),
            ("drenaje", "lote y drenaje", lambda n: _lam_drenaje(ctx, n, dr, prof)),
            ("cotas", "cotas", lambda n: _lam_cotas(ctx, n)),
            ("hand", "altura sobre el drenaje", lambda n: _lam_hand(ctx, n))]
    if prof:
        plan.append(("corredor", "el drenaje más cercano de cerca", lambda n: _lam_corredor(ctx, n, dr, prof)))
    if ctx.rog is not None:
        plan.append(("lluvia", "lluvias simuladas", lambda n: _lam_lluvia(ctx, n)))
    plan.append(("satelite", "agua vista por satélite", lambda n: _lam_satelite(ctx, n)))
    # numeración primero (las láminas se citan entre sí), después dibujo
    avail = [(key, lab, fn) for key, lab, fn in plan if not (key == "satelite" and not (p.data_proc / "jrc" / "occurrence_hidro.tif").exists())]
    ctx.num = {key: i for i, (key, _, _) in enumerate(avail, 1)}; ctx.num_labels = {i: lab for i, (_, lab, _) in enumerate(avail, 1)}
    pages = []
    for key, lab, fn in avail:
        print(f"  lámina {ctx.num[key]} · {lab}")
        r = fn(ctx.num[key])
        if r is not None:
            pages.append(r)
    pages.insert(0, _resumen(ctx, dr, prof))
    n = len(pages); pdf = p.out / f"ficha_{p.name}.pdf"
    meta = {"Title": f"Ficha de anegamiento · {p.titulo}", "Author": f"anega2 {__version__}", "Subject": f"Riesgo {ctx.ev.get('global', '—')} · análisis {ctx.fecha}"}
    with PdfPages(pdf, metadata=meta) as pp:
        for i, (fig, name) in enumerate(pages, 1):
            _footer(fig, ctx, i, n)
            fig.savefig(outdir / name, dpi=150); pp.savefig(fig); plt.close(fig)
    p.summary_line("FICHA", [f"{n} páginas A4 apaisadas en {outdir} · PDF: {pdf.name}",
                             "Páginas: resumen · " + " · ".join(f"{i} {lab}" for i, lab in ctx.num_labels.items()),
                             (f"Drenaje más cercano: {prof['corto']} a {fnum(dr['dist'], 0)} m al {dr['dir']}" if prof else "Drenaje más cercano: sin perfil (falta la red vectorial)"),
                             "Todas con leyenda, escala, pie de figura y pie de página (proyecto, fecha, DEM, página)",
                             "Aptas para compartir con arquitecto / ingeniero"])
    return dict(pdf=str(pdf), figs=[str(outdir / name) for _, name in pages])
