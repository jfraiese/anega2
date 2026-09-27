"""CLI de anega2: init · run · serve · list · doctor."""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

from .project import PROJECTS_DIR, REPO_ROOT, Project

FASES = [  # (nombre CLI, descripción, módulo)
    ("aoi", "geometrías del lote y buffers + PNG de ubicación", "aoi"),
    ("dem", "descarga de DEMs (IGN, Copernicus GLO-30, FABDEM)", "dem"),
    ("terreno", "análisis de terreno con WhiteboxTools (red, HAND, depresiones, cuenca)", "terrain"),
    ("agua", "histórico de agua superficial (JRC Global Surface Water)", "water"),
    ("clima", "lluvia histórica en el lote (ERA5 + CHIRPS): máximos, período de retorno, tormentas", "clima"),
    ("sar", "detección de agua por evento con Sentinel-1", "sar"),
    ("lluvia", "simulación lluvia → lámina (Landlab rain-on-grid)", "rog"),
    ("informe", "informe automático out/README.md (veredicto por reglas)", "report"),
    ("ficha", "ficha para arquitecto/ingeniero: láminas con leyenda sobre imagen satelital + PDF", "ficha"),
    ("kml", "KML único para Google Earth / My Maps", "kml"),
    ("web", "datos del visor web (projects/<nombre>/web)", "webdata"),
]


def write_index() -> Path:
    rows = []
    for lj in sorted(PROJECTS_DIR.glob("*/web/layers.json")):
        try:
            d = json.load(open(lj))
        except Exception:  # noqa: BLE001
            d = {}
        rows.append(dict(nombre=lj.parent.parent.name, titulo=d.get("titulo", lj.parent.parent.name),
                         actualizado=datetime.fromtimestamp(lj.stat().st_mtime).isoformat(timespec="minutes")))
    PROJECTS_DIR.mkdir(exist_ok=True)
    out = PROJECTS_DIR / "index.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    return out


def cmd_init(a) -> int:
    p = Project.create(a.nombre, Path(a.kml), a.titulo, overwrite=a.sobrescribir)
    print(f"Proyecto creado: {p.dir}\n  KML: {p.kml_path.name} · CRS: {p.crs} ({p.crs_descr}) · Argentina: {p.es_argentina}")
    print(f"Editá {p.dir / 'project.yml'} si querés cambiar radios, eventos o escenarios; después: anega2 run {a.nombre}")
    return 0


def cmd_run(a) -> int:
    import importlib
    p = Project.load(a.nombre, yes=a.si)
    fases = [f for f, _, _ in FASES] if (not a.fase or "todo" in a.fase) else a.fase
    print(f"anega2 · {p.titulo} · CRS {p.crs} · fases: {', '.join(fases)}")
    for name, descr, mod in FASES:
        if name not in fases:
            continue
        print(f"\n=== {name}: {descr} ===")
        m = importlib.import_module(f"anega2.{mod}")
        try:
            m.run(p)
        except KeyboardInterrupt:
            print("interrumpido"); return 130
    return 0


def cmd_serve(a) -> int:
    write_index()
    projects = Project.list_projects()
    name = a.proyecto or (projects[0] if projects else "")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(REPO_ROOT))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", a.puerto), handler)
    url = f"http://localhost:{a.puerto}/webapp/?project={name}"
    print(f"Visor en {url}  (Ctrl+C para cortar)")
    if not a.no_abrir:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_list(a) -> int:
    for n in Project.list_projects():
        p = Project.load(n)
        done = [f for f, _, mod in FASES if (p.out / {"aoi": "aoi.gpkg", "dem": "../data/raw/dem_inventory.json", "terreno": "terrain_stats.csv",
                                                     "agua": "jrc_stats.csv", "clima": "clima.json", "sar": "sar_stats.csv", "lluvia": "rog_stats.csv", "informe": "README.md", "ficha": f"ficha_{n}.pdf",
                                                     "kml": f"{n}.kml", "web": "../web/layers.json"}[f]).exists()]
        print(f"{n:<24} {p.titulo:<40} fases listas: {', '.join(done) or '-'}")
    return 0


def cmd_doctor(a) -> int:
    import platform, tempfile
    import numpy as np
    print(f"Python {sys.version.split()[0]} · {platform.system()} {platform.machine()}")
    ok = True
    for m in ["osgeo.gdal", "rasterio", "geopandas", "pyogrio", "shapely", "pyproj", "numpy", "scipy", "pandas", "matplotlib",
              "contextily", "requests", "yaml", "whitebox", "landlab", "pystac_client", "planetary_computer", "skimage", "PIL"]:
        try:
            mod = __import__(m, fromlist=["__version__"]); ver = getattr(mod, "__version__", "") or getattr(mod, "VersionInfo", lambda: "")()
            print(f"  {m:<20} {ver}")
        except Exception as e:  # noqa: BLE001
            ok = False; print(f"  {m:<20} ERROR: {e}")
    try:
        import rasterio, whitebox
        from rasterio.transform import from_origin
        wbt = whitebox.WhiteboxTools(); wbt.set_verbose_mode(False)
        print("WhiteboxTools:", wbt.version().strip().splitlines()[0])
        with tempfile.TemporaryDirectory() as td:
            dem = Path(td) / "dem.tif"; slope = Path(td) / "slope.tif"
            yy, xx = np.mgrid[0:50, 0:50]; z = (50 + 0.1 * xx + 0.05 * yy).astype("float32")
            with rasterio.open(dem, "w", driver="GTiff", height=50, width=50, count=1, dtype="float32", crs="EPSG:5347",
                               transform=from_origin(5500000, 6200000, 5, 5), nodata=-9999) as d:
                d.write(z, 1)
            wbt.slope(str(dem), str(slope), units="degrees")
            with rasterio.open(slope) as s:
                v = s.read(1)[1:-1, 1:-1]
            print(f"  slope test: {np.nanmean(v):.3f}° (esperado ≈ {np.degrees(np.arctan(np.hypot(0.02, 0.01))):.3f}°)")
    except Exception as e:  # noqa: BLE001
        ok = False; print("  WhiteboxTools ERROR:", e)
    import requests
    for name, url in [("IGN WFS", "https://wms.ign.gob.ar/geoserver/modelos-digitales-elevaciones/wfs?service=WFS&request=GetCapabilities"),
                      ("Planetary Computer STAC", "https://planetarycomputer.microsoft.com/api/stac/v1"),
                      ("Copernicus DEM (AWS)", "https://copernicus-dem-30m.s3.amazonaws.com/"),
                      ("JRC GSW", "https://storage.googleapis.com/global-surface-water/downloads2021/occurrence/occurrence_60W_30Sv1_4_2021.tif"),
                      ("FABDEM (Bristol)", "https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn/FABDEM_v1-2_tiles.geojson"),
                      ("Overpass (OSM)", "https://overpass-api.de/api/status")]:
        try:
            r = requests.get(url, timeout=20, allow_redirects=True, stream=True); r.close()
            print(f"  red {name:<24} HTTP {r.status_code}{'' if r.ok else '  (revisar)'}")
        except Exception as e:  # noqa: BLE001
            print(f"  red {name:<24} ERROR {e}")
    print("RESULTADO:", "OK" if ok else "CON ERRORES")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="anega2", description="Análisis de riesgo de anegamiento por lluvia para un polígono KML (Argentina).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init", help="crear un proyecto a partir de un KML"); s.add_argument("nombre"); s.add_argument("--kml", required=True)
    s.add_argument("--titulo"); s.add_argument("--sobrescribir", action="store_true"); s.set_defaults(fn=cmd_init)
    s = sub.add_parser("run", help="correr fases de un proyecto"); s.add_argument("nombre")
    s.add_argument("--fase", nargs="*", choices=[f for f, _, _ in FASES] + ["todo"], help="una o más fases (default: todo)")
    s.add_argument("--si", action="store_true", help="no pedir confirmación antes de descargas grandes"); s.set_defaults(fn=cmd_run)
    s = sub.add_parser("serve", help="servir el visor web y abrir el navegador"); s.add_argument("--puerto", type=int, default=8000)
    s.add_argument("--proyecto"); s.add_argument("--no-abrir", action="store_true"); s.set_defaults(fn=cmd_serve)
    s = sub.add_parser("list", help="listar proyectos y fases listas"); s.set_defaults(fn=cmd_list)
    s = sub.add_parser("doctor", help="verificar entorno, WhiteboxTools y acceso a las fuentes"); s.set_defaults(fn=cmd_doctor)
    a = ap.parse_args(argv)
    return a.fn(a)
