"""Ficha para arquitecto / ingeniero: láminas entendibles sobre imagen satelital, con leyenda, escala y
pie de figura con los números clave, más un PDF que las junta (out/ficha/ y out/ficha_<nombre>.pdf)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import patches  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from rasterio.plot import plotting_extent  # noqa: E402
from scipy.ndimage import uniform_filter  # noqa: E402

from .common import read_window  # noqa: E402
from .project import Project  # noqa: E402
from .report import f as fnum  # noqa: E402


def _basemap(ax, crs, zoom, ext):
    x0, y0, x1, y1 = ext.bounds
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal")
    try:
        import contextily as cx
        cx.add_basemap(ax, crs=crs, source=cx.providers.Esri.WorldImagery, zoom=zoom, attribution=False)
        for im in ax.images:
            im.set_zorder(0)
    except Exception as e:  # noqa: BLE001
        print("  [aviso] sin mapa base:", e)
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)


def _streams(ax, p):
    """Arroyos de referencia (red ≥ 2 km² y OSM) en trazo fino."""
    f2 = p.out / "terrain_red_drenaje_2km2.geojson"
    if f2.exists():
        gpd.read_file(f2).plot(ax=ax, color="#1e88e5", lw=1.6, zorder=4)
    fo = p.out / "osm_waterways.geojson"
    if fo.exists():
        g = gpd.read_file(fo)
        if len(g):
            g.plot(ax=ax, color="white", lw=1.0, linestyle=":", zorder=4)
    return [Line2D([], [], color="#1e88e5", lw=1.6, label="arroyos (≥ 2 km² de cuenca)"),
            Line2D([], [], color="white", lw=1.0, linestyle=":", label="arroyos según OpenStreetMap")]


def _frame(ax, aoi, ext, title, crs):
    x0, y0, x1, y1 = ext.bounds
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    gpd.GeoSeries(aoi["aoi"], crs=crs).boundary.plot(ax=ax, color="#ffb300", lw=1.2, linestyle="--")
    gpd.GeoSeries(aoi["lote"], crs=crs).boundary.plot(ax=ax, color="#ff1744", lw=2.5)
    # escala
    L = 200 if (x1 - x0) < 3000 else 500
    xs = x0 + 0.04 * (x1 - x0); ys = y0 + 0.05 * (y1 - y0)
    ax.plot([xs, xs + L], [ys, ys], color="white", lw=4, solid_capstyle="butt"); ax.plot([xs, xs + L], [ys, ys], color="k", lw=1.5)
    ax.text(xs + L / 2, ys + 0.012 * (y1 - y0), f"{L} m", ha="center", va="bottom", fontsize=8, color="white",
            bbox=dict(fc="black", alpha=0.5, ec="none", pad=1.5))
    # norte
    ax.annotate("N", xy=(x1 - 0.05 * (x1 - x0), y1 - 0.05 * (y1 - y0)), xytext=(x1 - 0.05 * (x1 - x0), y1 - 0.14 * (y1 - y0)),
                ha="center", color="white", fontsize=11, fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", color="white", lw=1.5))
    ax.set_title(title, fontsize=13, loc="left", pad=8)


def _caption(fig, text):
    fig.text(0.02, 0.012, text, ha="left", va="bottom", fontsize=9.2, wrap=True,
             bbox=dict(fc="#f6f7f9", ec="#d0d3d8", boxstyle="round,pad=0.5"))


def _legend(ax, handles, title=None):
    lg = ax.legend(handles=handles, loc="lower right", fontsize=8.5, title=title, title_fontsize=9, framealpha=0.92)
    lg.get_frame().set_edgecolor("#999")


def _classes(ax, arr, tr, bounds, colors, alpha=0.65):
    a = np.array(arr, dtype=float)
    cmap = ListedColormap(colors); norm = BoundaryNorm(bounds, cmap.N)
    m = np.ma.masked_invalid(np.where((a >= bounds[0]) & (a < bounds[-1]), a, np.nan))
    ax.imshow(m, extent=plotting_extent(a, tr), cmap=cmap, norm=norm, alpha=alpha, interpolation="nearest", zorder=3)
    return [patches.Patch(fc=c, ec="none", alpha=0.85, label=lab) for c, lab in zip(colors, [f"{bounds[i]:g} – {bounds[i+1]:g}" for i in range(len(bounds) - 1)])]


def run(p: Project) -> dict:
    aoi = p.load_aoi(); crs = p.crs
    prim = json.load(open(p.out / "terrain_primary.json"))["primary"]
    T = p.data_proc / "terrain" / prim
    ts = pd.read_csv(p.out / "terrain_stats.csv"); pc = [c for c in ts.columns if "(primario)" in c][0]
    k = dict(zip(ts["variable"], ts[pc]))
    ver = json.load(open(p.out / "veredicto.json")) if (p.out / "veredicto.json").exists() else {}
    ev = ver.get("veredicto", {})
    outdir = p.out / "ficha"; outdir.mkdir(exist_ok=True)
    ext = aoi["lote"].buffer(p.aoi_m + 700).envelope
    zoom = 16
    aoi_lab = f"{p.aoi_m:.0f} m"
    figs = []

    def rd(path):
        return read_window(path, ext)

    def osm():
        f_ = p.out / "osm_waterways.geojson"
        return gpd.read_file(f_) if f_.exists() else None

    # ---------------- 1. dónde está y hacia dónde va el agua
    fig, ax = plt.subplots(figsize=(11, 10)); _basemap(ax, crs, zoom, ext)
    hs = []
    for fn, col, lw, lab in [("terrain_red_drenaje_05km2.geojson", "#4fc3f7", 1.5, "cauces menores (≥ 0,5 km² de cuenca)"),
                             ("terrain_red_drenaje_2km2.geojson", "#1e88e5", 2.5, "arroyos (≥ 2 km² de cuenca)")]:
        f_ = p.out / fn
        if f_.exists():
            gpd.read_file(f_).plot(ax=ax, color=col, lw=lw, zorder=4); hs.append(Line2D([], [], color=col, lw=lw, label=lab))
    o = osm()
    if o is not None and len(o):
        o.plot(ax=ax, color="white", lw=1.2, linestyle=":", zorder=4); hs.append(Line2D([], [], color="white", lw=1.2, linestyle=":", label="arroyos según OpenStreetMap"))
    f_ = p.out / "terrain_cuenca_lote.geojson"
    if f_.exists():
        gpd.read_file(f_).plot(ax=ax, fc="#76ff03", ec="#64dd17", alpha=0.35, lw=1.5, zorder=4); hs.append(patches.Patch(fc="#76ff03", ec="#64dd17", alpha=0.5, label="cuenca que aporta agua al lote"))
    f_ = p.out / "terrain_flowpath_lote.geojson"
    if f_.exists():
        gpd.read_file(f_).plot(ax=ax, color="#e040fb", lw=3, zorder=5); hs.append(Line2D([], [], color="#e040fb", lw=3, label="camino del agua que sale del lote"))
    hs += [Line2D([], [], color="#ff1744", lw=2.5, label="lote"), Line2D([], [], color="#ffb300", lw=1.2, linestyle="--", label=f"entorno de {aoi_lab}")]
    _frame(ax, aoi, ext, "1 · Dónde está el lote y hacia dónde va el agua", crs); _legend(ax, hs)
    _caption(fig, f"El agua que cae en el lote sale hacia {k.get('direccion_salida_flowpath', '—')} y llega al cauce más cercano a "
                  f"{fnum(k.get('dist_euclid_red_05km2_m'), 0)} m en línea recta ({fnum(k.get('dist_flujo_red_05km2_m'), 0)} m siguiendo el terreno). "
                  f"La cuenca que aporta agua al lote es de {fnum(k.get('cuenca_celda_mas_baja_ha'))} a {fnum(k.get('cuenca_todo_el_lote_ha'))} ha: "
                  f"{'prácticamente no recibe agua de los vecinos' if float(k.get('cuenca_todo_el_lote_ha', 0)) < 5 else 'recibe escurrimiento de arriba'}. "
                  f"Fuente: DEM {prim} (30 m) y OpenStreetMap.")
    fig.tight_layout(rect=(0, 0.07, 1, 1)); f1 = outdir / "01_ubicacion_y_drenaje.png"; fig.savefig(f1, dpi=150); figs.append((fig, f1))

    # ---------------- 2. cotas
    dem, tr = rd(T / "dem.tif")
    z = uniform_filter(np.nan_to_num(dem, nan=np.nanmean(dem)), 3)
    fig, ax = plt.subplots(figsize=(11, 10)); _basemap(ax, crs, zoom, ext)
    e = plotting_extent(dem, tr)
    xs = np.linspace(e[0], e[1], dem.shape[1]); ys = np.linspace(e[3], e[2], dem.shape[0])
    lv = np.arange(math.floor(np.nanmin(z) * 2) / 2, math.ceil(np.nanmax(z) * 2) / 2 + 0.5, 0.5)
    cs = ax.contour(xs, ys, z, levels=lv, colors="#ffee58", linewidths=0.8, zorder=4)
    ax.clabel(cs, fmt="%.1f", fontsize=7, colors="#ffee58")
    zmin, zmax = float(k.get("z_min_lote")), float(k.get("z_max_lote"))
    csl = ax.contour(xs, ys, z, levels=[zmin], colors="#ff1744", linewidths=2, linestyles="--", zorder=5)
    hs = [Line2D([], [], color="#c6a700", lw=1.2, label="curvas de nivel cada 0,5 m (m snm)"),
          Line2D([], [], color="#ff1744", lw=2, linestyle="--", label=f"cota del punto más bajo del lote ({fnum(zmin)} m)"),
          Line2D([], [], color="#ff1744", lw=2.5, label="lote")]
    _frame(ax, aoi, ext, "2 · Cotas del terreno (curvas cada 0,5 m)", crs); _legend(ax, hs)
    _caption(fig, f"El lote está entre {fnum(zmin)} y {fnum(zmax)} m sobre el nivel del mar (media {fnum(k.get('z_mean_lote'))} m). "
                  f"El cauce más cercano está a cota {fnum(k.get('z_cauce_mas_cercano'))} m, es decir {fnum(k.get('salto_lote_min_vs_cauce_m'))} m por debajo del punto más bajo del lote. "
                  f"Alturas relativas al DEM {prim} (30 m, datum EGM2008/SRVN16): sirven para comparar puntos entre sí, no como cota IGN oficial; "
                  f"confirmar con nivelación en campo antes de fijar la cota de piso. Los 'cerritos' de curvas muy apretadas sobre galpones o arboledas "
                  f"son restos de edificios y copas que el modelo no eliminó del todo, no lomas reales.")
    fig.tight_layout(rect=(0, 0.07, 1, 1)); f2 = outdir / "02_cotas.png"; fig.savefig(f2, dpi=150); figs.append((fig, f2))

    # ---------------- 3. HAND
    hand, trh = rd(T / "hand_05km2.tif")
    fig, ax = plt.subplots(figsize=(11, 10)); _basemap(ax, crs, zoom, ext)
    hs = _classes(ax, hand, trh, [0, 0.5, 1, 2, 3], ["#b71c1c", "#e53935", "#fb8c00", "#fdd835"]); hs_st = _streams(ax, p)
    for h_, lab in zip(hs, ["menos de 0,5 m (cauce y su borde)", "0,5 – 1 m (muy bajo)", "1 – 2 m (bajo)", "2 – 3 m (medio)"]):
        h_.set_label(lab)
    hs.append(patches.Patch(fc="none", ec="#999", label="sin color: más de 3 m (alto)")); hs += hs_st; hs.append(Line2D([], [], color="#ff1744", lw=2.5, label="lote"))
    _frame(ax, aoi, ext, "3 · Cuánto tendría que subir el agua desde el arroyo para llegar", crs); _legend(ax, hs, "altura sobre el drenaje (HAND)")
    _caption(fig, f"Cada color indica cuántos metros tendría que subir el agua desde el cauce más cercano, siguiendo el camino del agua, para llegar a ese punto. "
                  f"En el lote son {fnum(k.get('hand_min_lote'))} a {fnum(k.get('hand_max_lote'))} m. En el entorno de {aoi_lab}, el {fnum(k.get('pct_aoi_hand_le1'), 0)} % está a menos de 1 m y el "
                  f"{fnum(k.get('pct_aoi_hand_le2'), 0)} % a menos de 2 m. Desborde del arroyo: {ev.get('desborde', {}).get('nivel', '—')}.")
    fig.tight_layout(rect=(0, 0.07, 1, 1)); f3 = outdir / "03_altura_sobre_el_arroyo.png"; fig.savefig(f3, dpi=150); figs.append((fig, f3))

    # ---------------- 4. lluvia simulada (dos escenarios)
    rog = pd.read_csv(p.out / "rog_stats.csv") if (p.out / "rog_stats.csv").exists() else None
    if rog is not None:
        picks = [s for s in ["P100_24h", "P150_24h_sat", "P200_24h"] if (p.data_proc / "rog" / f"{s}_hmax_dom.tif").exists()][:3]
        fig, axes = plt.subplots(1, len(picks), figsize=(6.2 * len(picks), 7.2))
        axes = np.atleast_1d(axes)
        for ax, s in zip(axes, picks):
            r = rog[rog.escenario == s].iloc[0]
            h, trr = rd(p.data_proc / "rog" / f"{s}_hmax_dom.tif")
            _basemap(ax, crs, zoom, ext)
            hs = _classes(ax, h, trr, [0.05, 0.2, 0.5, 5], ["#90caf9", "#1565c0", "#0d47a1"], alpha=0.75); hs += _streams(ax, p)[1:]
            for h_, lab in zip(hs, ["5 – 20 cm", "20 – 50 cm", "más de 50 cm"]):
                h_.set_label(lab)
            hs.append(Line2D([], [], color="#ff1744", lw=2.5, label="lote"))
            lab = f"{int(r['P_mm'])} mm en {r['dur_h']:g} h" + (" · suelo saturado" if s.endswith("_sat") else "")
            _frame(ax, aoi, ext, lab, crs); _legend(ax, hs, "lámina máxima de agua")
            ax.text(0.02, 0.98, f"en el lote: máx {fnum(r['hmax_lote_m']*100, 0)} cm · {fnum(r['pct_lote_gt5cm'], 0)} % con > 5 cm",
                    transform=ax.transAxes, va="top", fontsize=9, color="white", bbox=dict(fc="black", alpha=0.55, ec="none"))
        fig.suptitle("4 · Lluvias extremas simuladas: dónde se junta el agua", fontsize=14, x=0.02, ha="left")
        _caption(fig, "Simulación 2D (Landlab) de lluvia sobre el terreno con infiltración. Muestra dónde se acumula agua y cuánto, no el desborde del arroyo que "
                      "viene de aguas arriba. Píxeles de 30 m: no ve zanjas ni cunetas. Sin período de retorno (no hay curva IDF local).")
        fig.tight_layout(rect=(0, 0.08, 1, 0.94)); f4 = outdir / "04_lluvias_simuladas.png"; fig.savefig(f4, dpi=150); figs.append((fig, f4))

    # ---------------- 5. agua vista por satélite
    jrc_path = p.data_proc / "jrc" / "occurrence_hidro.tif"
    sar = pd.read_csv(p.out / "sar_stats.csv") if (p.out / "sar_stats.csv").exists() else None
    if jrc_path.exists():
        j, trj = rd(jrc_path); j = np.where(j == 255, np.nan, j)
        fig, ax = plt.subplots(figsize=(11, 10)); _basemap(ax, crs, zoom, ext)
        hs = _classes(ax, np.where(j > 0, j, np.nan), trj, [1, 10, 50, 101], ["#ffab91", "#ab47bc", "#1a237e"], alpha=0.8)
        for h_, lab in zip(hs, ["agua en 1 – 10 % de las imágenes", "10 – 50 %", "más del 50 % (laguna permanente)"]):
            h_.set_label(lab)
        hs.append(Line2D([], [], color="#ff1744", lw=2.5, label="lote"))
        _frame(ax, aoi, ext, "5 · Agua vista por satélite, 1984-2021", crs); _legend(ax, hs, "Landsat (JRC)")
        jr = pd.read_csv(p.out / "jrc_stats.csv") if (p.out / "jrc_stats.csv").exists() else None
        lote_occ = float(jr.iloc[0]["occ>0 %"]) if jr is not None else float("nan")
        n_s1 = int((sar["evento"] != "referencia_seca").sum()) if sar is not None else 0
        s1_max = float(sar[sar["evento"] != "referencia_seca"]["pct_agua_lote"].max()) if sar is not None and n_s1 else float("nan")
        _caption(fig, f"Landsat (30 m, 1984-2021): {'nunca vio agua sobre el lote' if lote_occ == 0 else f'vio agua en el {fnum(lote_occ, 1)} % del lote'}. "
                      f"Radar Sentinel-1 (10 m): {n_s1} escenas alrededor de los eventos de lluvia analizados, "
                      f"{'ninguna con agua abierta sobre el lote' if s1_max == 0 else f'hasta el {fnum(s1_max, 0)} % del lote con agua'}. "
                      "Los satélites no ven agua bajo árboles ni la que dura menos que el intervalo entre pasadas.")
        fig.tight_layout(rect=(0, 0.07, 1, 1)); f5 = outdir / "05_agua_satelite.png"; fig.savefig(f5, dpi=150); figs.append((fig, f5))

    # ---------------- 6. ficha resumen
    fig = plt.figure(figsize=(11, 8)); fig.patch.set_facecolor("white")
    ax = fig.add_axes([0.04, 0.04, 0.92, 0.9]); ax.axis("off")
    g = ev.get("global", "—"); ll = ev.get("lluvia_local", {}); dd = ev.get("desborde", {})
    lon, lat = p.lot_centroid_wgs84()
    rows = [
        ("Ubicación", f"{lat:.6f}, {lon:.6f} · superficie {fnum(aoi['lote'].area, 0)} m²"),
        ("Cota del lote", f"{fnum(k.get('z_min_lote'))} – {fnum(k.get('z_max_lote'))} m snm (DEM {prim}, 30 m)"),
        ("Altura sobre el arroyo (HAND)", f"{fnum(k.get('hand_min_lote'))} – {fnum(k.get('hand_max_lote'))} m"),
        ("Cauce más cercano", f"a {fnum(k.get('dist_euclid_red_05km2_m'), 0)} m; cota {fnum(k.get('z_cauce_mas_cercano'))} m ({fnum(k.get('salto_lote_min_vs_cauce_m'))} m por debajo del lote)"),
        ("Pendiente media / hacia dónde escurre", f"{fnum(k.get('slope_mean_lote_pct'))} % / {k.get('direccion_salida_flowpath', '—')}"),
        ("Depresión cerrada en el lote", "sí, " + fnum(k.get('sink_depth_max_lote_m')) + " m" if str(k.get('lote_intersecta_depresion')) == "True" else "no"),
        ("Cuenca que aporta agua", f"{fnum(k.get('cuenca_celda_mas_baja_ha'))} – {fnum(k.get('cuenca_todo_el_lote_ha'))} ha"),
        ("Agua vista por satélite (1984-2026)", "ninguna sobre el lote" if (jrc_path.exists() and lote_occ == 0 and (s1_max == 0 or math.isnan(s1_max))) else "ver lámina 5"),
    ]
    if rog is not None:
        for s, lab in [("P100_24h", "100 mm/24 h"), ("P150_24h_sat", "150 mm/24 h, saturado"), ("P200_24h", "200 mm/24 h")]:
            if (rog.escenario == s).any():
                r = rog[rog.escenario == s].iloc[0]
                rows.append((f"Lluvia simulada · {lab}", f"máx {fnum(r['hmax_lote_m']*100, 0)} cm en el lote ({fnum(r['pct_lote_gt5cm'], 0)} % con > 5 cm), "
                                                        f"{fnum(r['dur_max_lote_h'], 1)} h con más de 5 cm"))
    y = 0.96
    ax.text(0, y, f"Ficha de anegamiento · {p.titulo}", fontsize=16, fontweight="bold", va="top"); y -= 0.07
    ax.text(0, y, f"Riesgo {g}   ·   por lluvia local: {ll.get('nivel', '—')}   ·   por desborde del drenaje: {dd.get('nivel', '—')}",
            fontsize=12.5, va="top", color="#b71c1c" if g in ("ALTO", "MEDIO") else "#e65100" if g == "MEDIO-BAJO" else "#2e7d32"); y -= 0.06
    for a, b in rows:
        ax.text(0, y, a, fontsize=10.5, fontweight="bold", va="top"); ax.text(0.40, y, b, fontsize=10.5, va="top", wrap=True); y -= 0.052
    y -= 0.01
    ax.text(0, y, "Qué hacer con esto", fontsize=11.5, fontweight="bold", va="top"); y -= 0.045
    for t in [f"• Nivelar en campo el punto más bajo del lote contra el fondo y la barranca del cauce ({fnum(k.get('dist_euclid_red_05km2_m'), 0)} m): el DEM estima {fnum(k.get('hand_min_lote'))} m de desnivel.",
              "• Cota de piso ≥ 0,5 m sobre el terreno natural y por encima de la cota de crecida que surja de esa nivelación.",
              "• Revisar alcantarillas de caminos y rutas entre el lote y el arroyo, y preguntar a vecinos por los eventos de 2015, 2016 y 2025.",
              "• Diagnóstico a 30 m de píxel, sin calibración ni microrrelieve: es orientativo, no reemplaza el relevamiento topográfico."]:
        ax.text(0, y, t, fontsize=10, va="top", wrap=True); y -= 0.045
    ax.text(0, 0.0, "Generado con anega2 (código MIT). Datos: FABDEM (CC BY-NC-SA), Copernicus DEM, IGN, JRC GSW, Sentinel-1, OpenStreetMap, imagen Esri.", fontsize=8, color="#666", va="bottom")
    f6 = outdir / "00_ficha_resumen.png"; fig.savefig(f6, dpi=150); figs.insert(0, (fig, f6))

    pdf = p.out / f"ficha_{p.name}.pdf"
    with PdfPages(pdf) as pp:
        for fig_, _ in figs:
            pp.savefig(fig_)
    for fig_, _ in figs:
        plt.close(fig_)
    p.summary_line("FICHA", [f"{len(figs)} láminas en {outdir}", f"PDF: {pdf.name}", "Láminas: resumen, ubicación y drenaje, cotas, altura sobre el arroyo, lluvias simuladas, agua por satélite",
                             "Todas sobre imagen satelital Esri, con leyenda, escala y pie de figura", "Aptas para compartir con arquitecto / ingeniero"])
    return dict(pdf=str(pdf), figs=[str(f_) for _, f_ in figs])
