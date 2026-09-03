"""Fase 1 · descarga de DEMs para el buffer hidrológico.

Fuentes (según p.cfg['dem']['fuentes']):
  ign30  IGN MDE-Ar v2.1 30 m (capa WFS mde_v2_30m)         -> data_raw/mde_ar/30m/<hoja>/<hoja>.img
  ign5   IGN MDE 5 m aerofotogramétrico (capa mde_5m)        -> data_raw/mde_ar/5m/<hoja>/...
  glo30  Copernicus DEM GLO-30 (AWS, COG, ventana /vsicurl/) -> data_raw/copdem/glo30_hidro_4326.tif
  fabdem FABDEM V1-2 (Bristol; una hoja extraída del zip por rangos HTTP) -> cache/<tile>_FABDEM_V1-2.tif
Las hojas IGN se identifican consultando el WFS público del IGN e intersectando con el buffer.
Los zips IGN y las hojas FABDEM se guardan en la caché compartida (p.cache). Sólo en Argentina se usan fuentes IGN.
Escribe data_raw/dem_inventory.json con {"sources": {clave: [archivos]}, ...} que usa terrain.py.
"""
from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import requests
from rasterio.windows import from_bounds

from .common import CRS_WGS84, bounds_wgs84, download, fetch_zip_member
from .project import Project

WFS = "https://wms.ign.gob.ar/geoserver/modelos-digitales-elevaciones/wfs"
IGN_DL = "https://dnsg.ign.gob.ar/apps/mapas-geodesia/mde_mapa_geoserver_descarga.php"
UA = {"User-Agent": "Mozilla/5.0 (anega2; analisis hidrologico)"}
COP_BASE = "https://copernicus-dem-30m.s3.amazonaws.com"
FAB_BASE = "https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn"  # FABDEM V1-2 (Hawker et al. 2022), CC BY-NC-SA 4.0
IGN_LAYERS = {"ign30": ("mde_v2_30m", "30m", "IGN MDE-Ar v2.1 30 m"), "ign5": ("mde_5m", "5m", "IGN MDE 5 m aerofotogramétrico")}


# ------------------------------------------------------------------ IGN
def wfs_coverage(p: Project, layer: str, bbox4326) -> gpd.GeoDataFrame:
    cache = p.data_raw / "mde_ar" / f"cobertura_{layer}.geojson"
    if cache.exists():
        return gpd.read_file(cache)
    minx, miny, maxx, maxy = bbox4326
    params = dict(service="WFS", version="1.1.0", request="GetFeature", typeName=f"modelos-digitales-elevaciones:{layer}",
                  outputFormat="application/json", srsName="EPSG:4326",
                  CQL_FILTER=f"BBOX(geom,{minx},{miny},{maxx},{maxy},'EPSG:4326')")
    r = requests.get(WFS, params=params, headers=UA, timeout=300)
    r.raise_for_status()
    g = gpd.read_file(r.text)
    if len(g):
        g["url"] = g["link"].str.extract(r'href="([^"]+)"')
        g = g.drop(columns=["link"])
    cache.parent.mkdir(parents=True, exist_ok=True)
    g.to_file(cache, driver="GeoJSON")
    return g


def _unzip(zp: Path, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zp) as z:
        z.extractall(dest)
    return sorted(f for f in dest.rglob("*") if f.suffix.lower() in (".img", ".tif", ".tiff"))


def ign_layer(p: Project, key: str, aoi: dict, bbox) -> list[dict]:
    layer, subdir, label = IGN_LAYERS[key]
    try:
        g = wfs_coverage(p, layer, bbox)
    except Exception as e:  # noqa: BLE001
        print(f"  {label}: WFS del IGN no disponible ({e})"); return []
    if len(g) == 0:
        print(f"  {label}: sin hojas en el bbox"); return []
    g = g.to_crs(p.crs)
    hit = g[g.intersects(aoi["hidro"])]
    print(f"  {label}: {len(hit)} hojas intersectan el buffer hidrológico")
    if len(hit) == 0:
        return []
    u = hit.geometry.union_all()
    print(f"    unión: cubre lote={u.contains(aoi['lote'])}, cubre AOI={u.contains(aoi['aoi'])}, "
          f"{100*u.intersection(aoi['hidro']).area/aoi['hidro'].area:.1f}% del buffer, distancia lote→cobertura {aoi['lote'].distance(u):.0f} m")
    if key == "ign5" and not u.intersects(aoi["aoi"]):
        print("    el MDE 5 m no toca el AOI: no se descarga (sólo serviría fuera del área de interés)")
        return [dict(layer=layer, hoja=Path(r["archivo"]).stem, nombre=r["nombre"], url=r["url"], disponible=False, files=[],
                     cubre_lote=False, toca_aoi=False, pct_hidro=round(100 * r.geometry.intersection(aoi["hidro"]).area / aoi["hidro"].area, 1))
                for _, r in hit.iterrows()]
    to_get = [Path(r["archivo"]).stem for _, r in hit.iterrows()]
    if not p.confirm(f"Descargar {len(hit)} hoja(s) del {label} del IGN ({', '.join(to_get)}) a {p.cache}/ign/{subdir}/ (≈ 7-30 MB c/u)"):
        print("    omitido por el usuario"); return []
    out = []
    dest_root = p.data_raw / "mde_ar" / subdir
    for _, r in hit.iterrows():
        name = Path(r["archivo"]).stem
        cov = 100 * r.geometry.intersection(aoi["hidro"]).area / aoi["hidro"].area
        rec = dict(layer=layer, hoja=name, proyecto=r.get("proyecto"), nombre=r["nombre"], url=r["url"],
                   cubre_lote=bool(r.geometry.contains(aoi["lote"])), toca_aoi=bool(r.geometry.intersects(aoi["aoi"])), pct_hidro=round(cov, 1))
        print(f"    {name:<16} {str(r['nombre']):<34} lote={rec['cubre_lote']!s:<5} AOI={rec['toca_aoi']!s:<5} buffer={cov:5.1f}%")
        cache_zip = p.cache / "ign" / subdir / f"{name}.zip"
        legacy_zip = dest_root / f"{name}.zip"
        zp = cache_zip if cache_zip.exists() else (legacy_zip if legacy_zip.exists() else None)
        if zp is None:
            cache_zip.parent.mkdir(parents=True, exist_ok=True)
            zp = download(r["url"], cache_zip, headers=UA)
        files = []
        if zp is not None:
            existing = sorted(f for f in (dest_root / name).rglob("*") if f.suffix.lower() in (".img", ".tif", ".tiff")) if (dest_root / name).exists() else []
            try:
                files = existing or _unzip(zp, dest_root / name)
            except zipfile.BadZipFile:
                print(f"    {name}: la respuesta no es un zip; se descarta"); zp.unlink(missing_ok=True)
        rec.update(disponible=bool(files), zip=str(zp) if files else None, files=[str(f) for f in files],
                   mb=round(zp.stat().st_size / 1e6, 1) if (zp and files) else None)
        if files:
            print(f"      {rec['mb']} MB -> {[Path(f).name for f in files]}")
        out.append(rec)
    return out


# ------------------------------------------------------------------ Copernicus GLO-30
def copdem_tiles(bbox4326):
    minx, miny, maxx, maxy = bbox4326
    names = []
    for lat in range(int(math.floor(miny)), int(math.floor(maxy)) + 1):
        for lon in range(int(math.floor(minx)), int(math.floor(maxx)) + 1):
            la = f"{'S' if lat < 0 else 'N'}{abs(lat):02d}_00"; lo = f"{'W' if lon < 0 else 'E'}{abs(lon):03d}_00"
            names.append(f"Copernicus_DSM_COG_10_{la}_{lo}_DEM")
    return names


def copdem_window(p: Project, bbox4326) -> Path | None:
    d = p.data_raw / "copdem"; d.mkdir(parents=True, exist_ok=True)
    dst = d / "glo30_hidro_4326.tif"
    legacy = d / "glo30_10km_4326.tif"
    if not dst.exists() and legacy.exists():
        legacy.rename(dst)
    if dst.exists():
        return dst
    tiles = copdem_tiles(bbox4326)
    if not p.confirm(f"Leer ventana de Copernicus DEM GLO-30 desde AWS (tiles {tiles}, ≈ 2 MB)"):
        return None
    srcs = [rasterio.open(f"/vsicurl/{COP_BASE}/{t}/{t}.tif") for t in tiles]
    if len(srcs) == 1:
        src = srcs[0]
        win = from_bounds(*bbox4326, transform=src.transform).round_offsets().round_lengths()
        arr = src.read(1, window=win); tr = src.window_transform(win); prof = src.profile.copy()
    else:
        from rasterio.merge import merge
        arr, tr = merge(srcs, bounds=bbox4326); arr = arr[0]; prof = srcs[0].profile.copy()
    prof.update(height=arr.shape[0], width=arr.shape[1], transform=tr, driver="GTiff", compress="deflate", tiled=False)
    prof.pop("blockxsize", None); prof.pop("blockysize", None)
    with rasterio.open(dst, "w", **prof) as o:
        o.write(arr, 1)
    for s in srcs:
        s.close()
    print(f"  Copernicus GLO-30: tiles {tiles} -> {dst.name} ({arr.shape[1]}x{arr.shape[0]} px)")
    return dst


# ------------------------------------------------------------------ FABDEM
def fabdem_tiles(bbox4326):
    minx, miny, maxx, maxy = bbox4326
    def f(v, neg, pos, w):
        return f"{neg if v < 0 else pos}{abs(v):0{w}d}"
    out = []
    for lat in range(int(math.floor(miny)), int(math.floor(maxy)) + 1):
        for lon in range(int(math.floor(minx)), int(math.floor(maxx)) + 1):
            la0 = math.floor(lat / 10) * 10; lo0 = math.floor(lon / 10) * 10
            zipname = f"{f(la0,'S','N',2)}{f(lo0,'W','E',3)}-{f(la0+10,'S','N',2)}{f(lo0+10,'W','E',3)}_FABDEM_V1-2.zip"
            out.append((f"{f(lat,'S','N',2)}{f(lon,'W','E',3)}_FABDEM_V1-2.tif", zipname))
    return out


def fabdem_download(p: Project, bbox4326) -> list[Path]:
    tiles = fabdem_tiles(bbox4326)
    files = []
    missing = []
    for tif, zipname in tiles:
        cached = p.cache / tif
        legacy = p.data_raw / "fabdem" / tif
        if cached.exists():
            files.append(cached)
        elif legacy.exists():
            files.append(legacy)
        else:
            missing.append((tif, zipname))
    if missing:
        if not p.confirm(f"Extraer {len(missing)} hoja(s) FABDEM ({', '.join(t for t, _ in missing)}) del zip de Bristol por rangos HTTP "
                         f"(≈ 15-20 MB transferidos por hoja; licencia CC BY-NC-SA 4.0, uso no comercial)"):
            return files
        for tif, zipname in missing:
            print(f"  FABDEM: extrayendo {tif} de {zipname} ...")
            files.append(fetch_zip_member(f"{FAB_BASE}/{zipname}", lambda n, t=tif: n.endswith(t), p.cache / tif, headers=UA))
    return files


# ------------------------------------------------------------------ main
def run(p: Project) -> dict:
    aoi = p.load_aoi()
    bbox = bounds_wgs84(aoi["hidro"], p.crs, pad_deg=0.01)
    fuentes = list(p.cfg["dem"]["fuentes"])
    print("bbox buffer hidrológico (WGS84):", np.round(bbox, 4).tolist(), "· fuentes:", fuentes)
    inv: dict = {"bbox_wgs84": list(bbox), "sources": {}}
    if not p.es_argentina:
        for k in ("ign30", "ign5"):
            if k in fuentes:
                print(f"  {k}: el polígono no está en Argentina, se omite"); fuentes.remove(k)
    for key in ("ign30", "ign5"):
        if key in fuentes:
            print(f"{IGN_LAYERS[key][2]}")
            recs = ign_layer(p, key, aoi, bbox)
            inv[key] = recs
            inv["sources"][key] = [f for r in recs for f in r.get("files", [])]
    if "glo30" in fuentes:
        print("Copernicus DEM GLO-30")
        cop = copdem_window(p, bbox)
        inv["sources"]["glo30"] = [str(cop)] if cop else []
        inv["glo30"] = dict(tiles=copdem_tiles(bbox), url=f"{COP_BASE}/<tile>/<tile>.tif")
    if "fabdem" in fuentes:
        print("FABDEM V1-2 (Copernicus GLO-30 sin árboles ni edificios)")
        try:
            fab = fabdem_download(p, bbox)
        except Exception as e:  # noqa: BLE001
            print("  FABDEM no disponible:", e); fab = []
        inv["sources"]["fabdem"] = [str(f) for f in fab]
        inv["fabdem"] = dict(url=f"{FAB_BASE}/<zip>", licencia="CC BY-NC-SA 4.0")
    (p.data_raw / "dem_inventory.json").write_text(json.dumps(inv, indent=1, ensure_ascii=False))

    def n(k):
        return len(inv["sources"].get(k, []))
    lines = [
        f"IGN MDE-Ar 30 m: {n('ign30')} archivo(s)" + (f" ({', '.join(r['hoja'] for r in inv.get('ign30', []))})" if inv.get("ign30") else "")
        + (f" · cubre lote: {any(r['cubre_lote'] for r in inv.get('ign30', []))}" if inv.get("ign30") else ""),
        f"IGN MDE 5 m: {len(inv.get('ign5', []))} hoja(s) en el buffer, {n('ign5')} descargable(s)"
        + (f" · cubre lote: {any(r['cubre_lote'] for r in inv.get('ign5', []))}" if inv.get("ign5") else ""),
        f"Copernicus GLO-30: {'ventana lista' if n('glo30') else 'no'} · FABDEM: {n('fabdem')} hoja(s)",
        f"Inventario: {p.data_raw / 'dem_inventory.json'}",
        "DEM primario: se elige en la fase de terreno (fidelidad de la red vs. arroyos OSM; preferencia por terreno desnudo)",
    ]
    p.summary_line("FASE 1 (descarga DEM)", lines)
    return inv
