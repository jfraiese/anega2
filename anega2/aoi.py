"""Fase 0: geometrías de referencia (lote, buffer AOI, buffer hidrológico) y PNG de ubicación.

Genera en p.out: aoi.gpkg (capa 'aoi': lote / aoi / hidro en p.crs), aoi_4326.geojson,
aoi_4326.kml y 00_ubicacion.png (tres paneles sobre basemaps Esri).
"""
from __future__ import annotations

import math
from pathlib import Path

import geopandas as gpd
from pyproj import Transformer

from .common import CRS_WGS84, read_lot_polygon
from .project import Project


def build_aoi(p: Project) -> tuple[gpd.GeoDataFrame, str]:
    lote, descr = read_lot_polygon(p.kml_path, p.crs)
    c = lote.centroid
    aoi = c.buffer(p.aoi_m, quad_segs=64)
    hidro = c.buffer(p.hidro_m, quad_segs=64)
    gdf = gpd.GeoDataFrame(
        {
            "name": ["lote", "aoi", "hidro"],
            "label": ["Lote", f"Buffer {p.aoi_m:.0f} m (AOI)", f"Buffer {p.hidro_m/1000:g} km (análisis hidrológico)"],
            "descr": [descr, f"Radio {p.aoi_m:.0f} m alrededor del centroide del lote",
                      f"Radio {p.hidro_m:.0f} m alrededor del centroide del lote"],
            "radius_m": [None, p.aoi_m, p.hidro_m],
        },
        geometry=[lote, aoi, hidro], crs=p.crs,
    )
    gdf["area_m2"] = gdf.geometry.area.round(1)
    return gdf, descr


def save(p: Project, gdf: gpd.GeoDataFrame) -> None:
    if p.aoi_gpkg.exists():
        p.aoi_gpkg.unlink()
    gdf.to_file(p.aoi_gpkg, layer="aoi", driver="GPKG")
    g84 = gdf.to_crs(CRS_WGS84)
    g84.to_file(p.out / "aoi_4326.geojson", driver="GeoJSON")
    g84.rename(columns={"label": "Name", "descr": "Description"})[["Name", "Description", "geometry"]].to_file(
        p.out / "aoi_4326.kml", driver="KML")


def _scalebar(ax, length_m: float, label: str) -> None:
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
    xs = x0 + 0.05 * (x1 - x0); ys = y0 + 0.05 * (y1 - y0)
    ax.plot([xs, xs + length_m], [ys, ys], color="k", lw=3, solid_capstyle="butt")
    ax.text(xs + length_m / 2, ys + 0.015 * (y1 - y0), label, ha="center", va="bottom", fontsize=8, color="k",
            bbox=dict(fc="white", ec="none", alpha=0.7, pad=1))


def _nice(m: float) -> tuple[float, str]:
    """Longitud 'redonda' de barra de escala ≈ m/4."""
    cands = [10, 20, 50, 100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000, 20000]
    v = min(cands, key=lambda c: abs(c - m / 4))
    return v, (f"{v/1000:g} km" if v >= 1000 else f"{v:g} m")


def _zoom(width_m: float, lat: float, px: int = 800) -> int:
    """Zoom de tiles tal que el ancho del panel ocupe ~px píxeles."""
    m_per_px = width_m / px
    z = math.log2(156543.03 * math.cos(math.radians(lat)) / m_per_px)
    return min(17, int(min(19, max(6, round(z)))))  # Esri no sirve zoom 18 en zonas rurales


def plot(p: Project, gdf: gpd.GeoDataFrame) -> Path:
    import contextily as cx
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    lote = gdf[gdf.name == "lote"]; aoi = gdf[gdf.name == "aoi"]; hidro = gdf[gdf.name == "hidro"]
    c = lote.geometry.iloc[0].centroid
    clon, clat = Transformer.from_crs(p.crs, CRS_WGS84, always_xy=True).transform(c.x, c.y)
    lx0, ly0, lx1, ly1 = lote.geometry.iloc[0].bounds
    lot_half = max(lx1 - lx0, ly1 - ly0) / 2 * 1.8 + 30

    fig, axes = plt.subplots(1, 3, figsize=(18, 6.5))
    panels = [
        (axes[0], p.hidro_m * 1.1, cx.providers.Esri.WorldTopoMap, f"Buffer {p.hidro_m/1000:g} km (análisis hidrológico) · Esri World Topo"),
        (axes[1], p.aoi_m * 1.4, cx.providers.Esri.WorldStreetMap, f"Buffer {p.aoi_m:.0f} m (AOI) y lote · Esri World Street Map"),
        (axes[2], lot_half, cx.providers.Esri.WorldImagery, "Lote · Esri World Imagery"),
    ]
    for i, (ax, pad, src, title) in enumerate(panels):
        if i == 0:
            hidro.boundary.plot(ax=ax, color="tab:blue", lw=1.5)
            aoi.boundary.plot(ax=ax, color="tab:orange", lw=1.5)
            ax.plot(c.x, c.y, marker="*", color="red", ms=14, mec="k")
        elif i == 1:
            aoi.boundary.plot(ax=ax, color="tab:orange", lw=2)
            lote.boundary.plot(ax=ax, color="red", lw=2)
        else:
            lote.boundary.plot(ax=ax, color="red", lw=2.5)
            ax.plot(c.x, c.y, marker="+", color="yellow", ms=12, mew=2)
        ax.set_xlim(c.x - pad, c.x + pad); ax.set_ylim(c.y - pad, c.y + pad)
        try:
            cx.add_basemap(ax, crs=gdf.crs, source=src, zoom=_zoom(2 * pad, clat), attribution=False)
        except Exception as e:  # noqa: BLE001
            print(f"  basemap no disponible ({e.__class__.__name__}): panel sin fondo")
        v, lab = _nice(2 * pad); _scalebar(ax, v, lab)
        ax.set_title(title); ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle(f"{p.titulo} · centroide del lote {clat:.6f}, {clon:.6f} (WGS84) · E={c.x:.1f} N={c.y:.1f} ({p.crs})", fontsize=12)
    fig.text(0.5, 0.01, "Basemaps: Esri World Topo / World Street Map / World Imagery (Esri, HERE, Garmin, Maxar, Earthstar Geographics, © OpenStreetMap contributors)",
             ha="center", fontsize=8, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    png = p.out / "00_ubicacion.png"
    fig.savefig(png, dpi=130); plt.close(fig)
    return png


def run(p: Project) -> dict:
    gdf, descr = build_aoi(p)
    save(p, gdf)
    png = plot(p, gdf)
    lote = gdf[gdf.name == "lote"].geometry.iloc[0]
    c = lote.centroid
    clon, clat = Transformer.from_crs(p.crs, CRS_WGS84, always_xy=True).transform(c.x, c.y)
    mrr = lote.minimum_rotated_rectangle
    xs, ys = mrr.exterior.coords.xy
    sides = sorted({round(math.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i]), 1) for i in range(4)})
    res = dict(centroide_wgs84=[clat, clon], E=c.x, N=c.y, crs=p.crs, crs_descr=p.crs_descr, area_m2=lote.area,
               lados_m=[sides[0], sides[-1]], descr=descr, aoi_ha=gdf.loc[gdf.name == "aoi", "area_m2"].iloc[0] / 1e4,
               hidro_km2=gdf.loc[gdf.name == "hidro", "area_m2"].iloc[0] / 1e6, png=str(png))
    p.summary_line("FASE 0 (AOI)", [
        f"Centroide del lote: {clat:.6f}, {clon:.6f} (WGS84) -> E={c.x:.2f} N={c.y:.2f} ({p.crs}, {p.crs_descr})",
        f"Lote: {descr} · área {lote.area:.0f} m² · rectángulo envolvente ≈ {sides[0]:.0f} x {sides[-1]:.0f} m",
        f"Buffer AOI {p.aoi_m:.0f} m: {res['aoi_ha']:.1f} ha · buffer hidrológico {p.hidro_m/1000:g} km: {res['hidro_km2']:.0f} km²",
        f"Argentina: {p.es_argentina} (fuentes IGN {'habilitadas' if p.es_argentina else 'omitidas'})",
        f"Salidas: {p.aoi_gpkg.name}, aoi_4326.geojson, aoi_4326.kml, {png.name}",
    ])
    return res
