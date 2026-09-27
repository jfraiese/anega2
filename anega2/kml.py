"""Entregable: KML único para Google Earth / My Maps.

Carpetas: lote, buffer AOI, centro del lote (con resumen), arroyos OSM, red de drenaje (dos umbrales),
cuenca aportante y camino de flujo del lote, depresiones cerradas (AOI), HAND ≤ 1 m y ≤ 2 m (recortado
a 3 km del lote para mantener el archivo liviano) y manchas de agua (h > 5 cm) de los escenarios de
100 y 150 mm (o los disponibles, hasta 3).

Salida: out/<nombre>.kml
"""
from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

import geopandas as gpd

from .common import CRS_WGS84
from .project import Project
from .rog import ficha_ids, scenario_specs


def kml_color(hex_rgb: str, alpha: str = "ff") -> str:
    """'#RRGGBB' -> 'aabbggrr' (formato KML)."""
    r, g, b = hex_rgb[1:3], hex_rgb[3:5], hex_rgb[5:7]
    return f"{alpha}{b}{g}{r}"


def coords(seq):
    return " ".join(f"{c[0]:.6f},{c[1]:.6f},0" for c in seq)  # ignora z si la geometría es 3D


def geom_kml(g) -> str:
    t = g.geom_type
    if t == "Point":
        return f"<Point><coordinates>{g.x:.6f},{g.y:.6f},0</coordinates></Point>"
    if t == "LineString":
        return f"<LineString><tessellate>1</tessellate><coordinates>{coords(g.coords)}</coordinates></LineString>"
    if t == "Polygon":
        s = f"<Polygon><tessellate>1</tessellate><outerBoundaryIs><LinearRing><coordinates>{coords(g.exterior.coords)}</coordinates></LinearRing></outerBoundaryIs>"
        for r in g.interiors:
            s += f"<innerBoundaryIs><LinearRing><coordinates>{coords(r.coords)}</coordinates></LinearRing></innerBoundaryIs>"
        return s + "</Polygon>"
    if t.startswith("Multi") or t == "GeometryCollection":
        return "<MultiGeometry>" + "".join(geom_kml(pg) for pg in g.geoms) + "</MultiGeometry>"
    raise ValueError(t)


def folder(name, gdf, style_id, name_col=None, descr_col=None, visible=True):
    if gdf is None or len(gdf) == 0:
        return ""
    g84 = gdf.to_crs(CRS_WGS84)
    pm = []
    for _, r in g84.iterrows():
        nm = escape(str(r[name_col])) if name_col and name_col in r and r[name_col] is not None else name
        ds = f"<description>{escape(str(r[descr_col]))}</description>" if descr_col and descr_col in r else ""
        pm.append(f"<Placemark><name>{nm}</name>{ds}<styleUrl>#{style_id}</styleUrl>{geom_kml(r.geometry)}</Placemark>")
    vis = "" if visible else "<visibility>0</visibility>"
    return f"<Folder><name>{escape(name)}</name>{vis}{''.join(pm)}</Folder>"


def style(sid, line="#ffffff", width=2, fill=None, fill_alpha="66", icon=None):
    s = f'<Style id="{sid}"><LineStyle><color>{kml_color(line)}</color><width>{width}</width></LineStyle>'
    if fill:
        s += f"<PolyStyle><color>{kml_color(fill, fill_alpha)}</color><outline>1</outline></PolyStyle>"
    else:
        s += "<PolyStyle><fill>0</fill><outline>1</outline></PolyStyle>"
    if icon:
        s += f"<IconStyle><color>{kml_color(icon)}</color><scale>1.3</scale></IconStyle>"
    return s + "</Style>"


def _rd(path: Path):
    return gpd.read_file(path) if path.exists() else None


def run(p: Project) -> dict:
    aoi = p.load_aoi(); crs = p.crs; out = p.out
    lote = aoi["lote"]; c = lote.centroid
    aoi_lab = f"{p.aoi_m:.0f} m"
    thr = p.cfg.get("dem", {}).get("umbrales_red_km2", [0.5, 2.0])
    thr_tags = [f"{t:g}".replace(".", "") + "km2" for t in thr]  # 0.5 -> "05km2", 2.0 -> "2km2"
    prim = json.load(open(out / "terrain_primary.json")) if (out / "terrain_primary.json").exists() else {}
    ts = {}
    try:
        import pandas as pd
        t = pd.read_csv(out / "terrain_stats.csv", index_col=0)
        col = [cc for cc in t.columns if "(primario)" in cc][0]
        ts = t[col].to_dict()
    except Exception:  # noqa: BLE001
        pass
    clip3 = lote.buffer(3000)

    def clip(g):
        if g is None or len(g) == 0:
            return g
        g = g[g.intersects(clip3)].copy(); g["geometry"] = g.geometry.intersection(clip3); return g[~g.is_empty]

    lote_g = gpd.GeoDataFrame({"n": ["Lote"]}, geometry=[lote], crs=crs)
    aoi_g = gpd.GeoDataFrame({"n": [f"Buffer {aoi_lab}"]}, geometry=[aoi["aoi"]], crs=crs)
    resumen = (f"DEM {prim.get('primary', '?')} · cota lote {ts.get('z_min_lote', '?')}-{ts.get('z_max_lote', '?')} m · "
               f"HAND {ts.get('hand_min_lote', '?')}-{ts.get('hand_max_lote', '?')} m · drenaje mas cercano "
               f"{ts.get('dist_euclid_red_05km2_m', '?')} m · cuenca aportante {ts.get('cuenca_celda_mas_baja_ha', '?')} ha. Ver out/README.md")
    centro = gpd.GeoDataFrame({"n": ["Centro del lote"], "d": [resumen]}, geometry=[c], crs=crs)

    # escenarios para las manchas: P_mm 100 y 150 de la config; si no hay, los disponibles (máx. 3)
    esc = [i for i in ficha_ids(p.cfg.get("lluvia", {})) if i in ("P100_24h", "P150_24h")]
    esc = [e for e in esc if (out / f"rog_{e}_agua5cm.geojson").exists()]
    if not esc:
        esc = sorted(x.name[len("rog_"):-len("_agua5cm.geojson")] for x in out.glob("rog_*_agua5cm.geojson"))[:3]
    esc_colors = ["#3366ff", "#000099", "#660066"]

    doc = ['<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
           f"<name>{escape(p.titulo)} · riesgo de anegamiento (anega2)</name>",
           style("lote", "#ff0000", 3), style("aoi", "#ff9900", 2), style("centro", "#ffffff", 1, icon="#ff0000"),
           style("osm", "#00ffff", 3), style("red0", "#66ccff", 2), style("red1", "#0033ff", 3),
           style("cuenca", "#00ff00", 2, fill="#00ff00", fill_alpha="33"), style("flujo", "#ff00ff", 3),
           style("dep", "#9900cc", 1, fill="#9900cc", fill_alpha="80"),
           style("hand1", "#cc0000", 1, fill="#cc0000", fill_alpha="66"), style("hand2", "#ff9933", 1, fill="#ff9933", fill_alpha="55")]
    for i, _ in enumerate(esc):
        doc.append(style(f"esc{i}", esc_colors[i % 3], 1, fill=esc_colors[i % 3], fill_alpha="80"))
    doc.append(folder("Lote", lote_g, "lote"))
    doc.append(folder(f"Buffer {aoi_lab} (AOI)", aoi_g, "aoi"))
    doc.append(folder("Centro del lote (resumen)", centro, "centro", "n", "d"))
    osm = _rd(out / "osm_waterways.geojson")
    if osm is not None and len(osm):
        osm["Name"] = osm["name"].fillna("sin nombre") + " (" + osm["waterway"].fillna("") + ")"
    doc.append(folder("Arroyos OSM", osm, "osm", "Name"))
    if len(thr_tags) > 1:
        doc.append(folder(f"Red de drenaje ≥ {thr[1]:g} km² (DEM)".replace(".", ","), _rd(out / f"terrain_red_drenaje_{thr_tags[1]}.geojson"), "red1"))
    doc.append(folder(f"Red de drenaje ≥ {thr[0]:g} km² (DEM)".replace(".", ","), _rd(out / f"terrain_red_drenaje_{thr_tags[0]}.geojson"), "red0", visible=len(thr_tags) == 1))
    doc.append(folder("Cuenca aportante al lote", _rd(out / "terrain_cuenca_lote.geojson"), "cuenca", "Name"))
    doc.append(folder("Camino de flujo desde el lote", _rd(out / "terrain_flowpath_lote.geojson"), "flujo", "Name"))
    doc.append(folder(f"Depresiones cerradas ({aoi_lab})", _rd(out / "terrain_depresiones_aoi.geojson"), "dep", "Name"))
    doc.append(folder("HAND ≤ 1 m (3 km)", clip(_rd(out / "terrain_hand_le1m.geojson")), "hand1", visible=False))
    doc.append(folder("HAND ≤ 2 m (3 km)", clip(_rd(out / "terrain_hand_le2m.geojson")), "hand2", visible=False))
    for i, e in enumerate(esc):
        cfg_e = next((x for x in scenario_specs(p.cfg.get("lluvia", {})) if x["id"] == e), None)
        lab = f"{cfg_e['P_mm']} mm/{cfg_e['dur_h']} h" if cfg_e else e
        doc.append(folder(f"Agua > 5 cm · {lab}", _rd(out / f"rog_{e}_agua5cm.geojson"), f"esc{i}", visible=(i == 0)))
    doc.append("</Document></kml>")
    dst = out / f"{p.name}.kml"
    dst.write_text("".join(doc), encoding="utf-8")
    n_folders = sum(1 for d in doc if d.startswith("<Folder>"))
    print(f"KML: {dst} ({dst.stat().st_size/1e6:.2f} MB, {n_folders} carpetas)")
    p.summary_line("KML", [f"Archivo: {dst.name} ({dst.stat().st_size/1e6:.2f} MB)", f"Carpetas: {n_folders}",
                           f"Escenarios de lluvia incluidos: {esc or 'ninguno'}",
                           f"HAND ≤1/≤2 m recortado a 3 km del lote", "Abrir en Google Earth / My Maps"])
    return dict(kml=str(dst), carpetas=n_folders, escenarios=esc)
