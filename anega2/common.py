"""Utilidades compartidas: lote desde KML, estadísticas zonales, GeoTIFF, PNG con lote superpuesto,
OSM Overpass, zip remoto. Todas reciben el CRS/rutas explícitamente (no hay globales de proyecto)."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio import features
from rasterio.mask import mask as rio_mask
from rasterio.warp import transform_bounds

CRS_WGS84 = "EPSG:4326"


# --- Lote / AOI -----------------------------------------------------------
def read_lot_polygon(kml_path: Path, crs: str):
    """Devuelve (polígono shapely en crs, descripción). Usa el polígono más grande si hay varios."""
    g = gpd.read_file(kml_path)
    g = g[g.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    if len(g) == 0:
        raise SystemExit(f"{kml_path.name} no contiene polígonos")
    g = g.to_crs(crs)
    poly = g.geometry.union_all()
    if poly.geom_type == "MultiPolygon":
        poly = max(poly.geoms, key=lambda p: p.area)
    poly = poly.buffer(0)
    # sin coordenada z
    from shapely import force_2d
    poly = force_2d(poly)
    name = g.iloc[0].get("Name") or g.iloc[0].get("name") or kml_path.stem
    return poly, f"Polígono KML '{name}' ({len(poly.exterior.coords) - 1} vértices)"


def bounds_wgs84(geom, crs: str, pad_deg: float = 0.0):
    b = transform_bounds(crs, CRS_WGS84, *geom.bounds)
    return (b[0] - pad_deg, b[1] - pad_deg, b[2] + pad_deg, b[3] + pad_deg)


# --- Raster helpers -------------------------------------------------------
def write_gtiff(path: Path, arr: np.ndarray, transform, crs: str, nodata=None, dtype=None) -> Path:
    """Sin compresión ni tiling: WhiteboxTools decodifica mal GeoTIFF float32 con deflate+predictor."""
    dtype = dtype or arr.dtype
    prof = dict(driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype=dtype,
                crs=crs, transform=transform, nodata=nodata, tiled=False)
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(arr.astype(dtype), 1)
    return path


def clip_raster(src_path: Path, geom, dst_path: Path, all_touched=False, nodata=None) -> Path:
    with rasterio.open(src_path) as src:
        nd = nodata if nodata is not None else src.nodata
        arr, tr = rio_mask(src, [geom], crop=True, all_touched=all_touched, nodata=nd, filled=True)
        prof = src.profile.copy()
        prof.update(height=arr.shape[1], width=arr.shape[2], transform=tr, nodata=nd, compress="deflate", tiled=False)
        prof.pop("blockxsize", None); prof.pop("blockysize", None)
        with rasterio.open(dst_path, "w", **prof) as dst:
            dst.write(arr)
    return dst_path


def zonal_values(src_path: Path, geom, all_touched=True, band=1) -> np.ndarray:
    with rasterio.open(src_path) as src:
        arr, _ = rio_mask(src, [geom], crop=True, all_touched=all_touched, indexes=band, filled=False)
    return np.asarray(arr.compressed())


def rasterize_geom(geom, shape, transform, all_touched=True) -> np.ndarray:
    return features.rasterize([(geom, 1)], out_shape=shape, transform=transform,
                              all_touched=all_touched, fill=0, dtype="uint8").astype(bool)


def read_raster(path: Path):
    """(array float64 con NaN en nodata, transform)."""
    with rasterio.open(path) as src:
        a = src.read(1).astype("float64"); nd = src.nodata; tr = src.transform
    if nd is not None:
        a[a == nd] = np.nan
    return a, tr


def read_window(path: Path, geom):
    """Ventana de un raster que contiene a geom: (array con NaN, transform)."""
    from rasterio.windows import from_bounds
    with rasterio.open(path) as s:
        win = from_bounds(*geom.bounds, transform=s.transform).round_offsets().round_lengths()
        arr = s.read(1, window=win).astype("float64"); tr = s.window_transform(win); nd = s.nodata
    if nd is not None:
        arr[arr == nd] = np.nan
    return arr, tr


# --- Plot -----------------------------------------------------------------
def plot_map(arr, transform, aoi: dict, title: str, out_png: Path, cmap="viridis", vmin=None, vmax=None,
             cbar_label="", extent_geom=None, overlays=None, discrete_labels=None, figsize=(9, 8),
             hillshade=None, nodata_color="white"):
    """PNG con raster + lote (rojo) + buffer AOI (naranja). overlays: [(GeoSeries/geom, kwargs)]."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from rasterio.plot import plotting_extent

    crs = aoi["crs"]
    fig, ax = plt.subplots(figsize=figsize)
    ext = plotting_extent(arr, transform)
    if hillshade is not None:
        ax.imshow(hillshade, extent=ext, cmap="gray", vmin=0, vmax=255, interpolation="nearest")
    a = np.ma.masked_invalid(arr) if np.issubdtype(np.asarray(arr).dtype, np.floating) else np.ma.asarray(arr)
    norm = None
    if discrete_labels:
        vals = sorted(discrete_labels)
        cmap = ListedColormap([discrete_labels[v][1] for v in vals])
        norm = BoundaryNorm([v - 0.5 for v in vals] + [vals[-1] + 0.5], cmap.N)
    im = ax.imshow(a, extent=ext, cmap=cmap, vmin=vmin, vmax=vmax, norm=norm, interpolation="nearest",
                   alpha=0.85 if hillshade is not None else 1.0)
    im.cmap.set_bad(nodata_color, alpha=0)
    for g, kw in (overlays or []):
        gs = g if isinstance(g, gpd.GeoSeries) else gpd.GeoSeries(g, crs=crs)
        gs.plot(ax=ax, **kw)
    gpd.GeoSeries(aoi["aoi"], crs=crs).boundary.plot(ax=ax, color="tab:orange", lw=1.5)
    gpd.GeoSeries(aoi["lote"], crs=crs).boundary.plot(ax=ax, color="red", lw=2)
    g0 = extent_geom if extent_geom is not None else aoi["aoi"]
    x0, y0, x1, y1 = g0.bounds
    pad = 0.05 * max(x1 - x0, y1 - y0)
    ax.set_xlim(x0 - pad, x1 + pad); ax.set_ylim(y0 - pad, y1 + pad)
    ax.set_aspect("equal")
    ax.set_xlabel(f"E (m, {crs})"); ax.set_ylabel(f"N (m, {crs})")
    ax.ticklabel_format(useOffset=False, style="plain"); ax.tick_params(labelsize=7)
    if discrete_labels:
        cb = fig.colorbar(im, ax=ax, ticks=vals, shrink=0.8)
        cb.ax.set_yticklabels([discrete_labels[v][0] for v in vals], fontsize=8)
    else:
        cb = fig.colorbar(im, ax=ax, shrink=0.8)
    cb.set_label(cbar_label)
    ax.set_title(title, fontsize=11)
    fig.tight_layout(); fig.savefig(out_png, dpi=140); plt.close(fig)
    return out_png


def pct(mask_true: np.ndarray, mask_valid: np.ndarray) -> float:
    n = int(mask_valid.sum())
    return 100.0 * float((mask_true & mask_valid).sum()) / n if n else float("nan")


def df_to_md(df, floatfmt=".2f") -> str:
    cols = list(df.columns)
    def fmt(v):
        if isinstance(v, float):
            return "nan" if np.isnan(v) else format(v, floatfmt)
        return str(v)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(fmt(r[c]) for c in cols) + " |")
    return "\n".join(lines)


# --- OSM ------------------------------------------------------------------
def fetch_osm_waterways(bbox4326, cache: Path, crs: str, timeout=180) -> gpd.GeoDataFrame:
    """Cursos de agua OSM (waterway=river|stream|canal|drain|ditch) vía Overpass. GeoDataFrame en crs; caché GeoJSON WGS84."""
    import requests
    from shapely.geometry import LineString
    if cache.exists():
        return gpd.read_file(cache).to_crs(crs)
    minx, miny, maxx, maxy = bbox4326
    q = f"""[out:json][timeout:{timeout}];
(way["waterway"~"^(river|stream|canal|drain|ditch)$"]({miny},{minx},{maxy},{maxx}););
out geom;"""
    r = requests.post("https://overpass-api.de/api/interpreter", data={"data": q}, timeout=timeout + 30,
                      headers={"User-Agent": "anega2 (analisis hidrologico)"})
    r.raise_for_status()
    rows = []
    for e in r.json().get("elements", []):
        if e.get("type") != "way" or "geometry" not in e or len(e["geometry"]) < 2:
            continue
        t = e.get("tags", {})
        rows.append(dict(osm_id=e["id"], waterway=t.get("waterway"), name=t.get("name"),
                         geometry=LineString([(g["lon"], g["lat"]) for g in e["geometry"]])))
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=CRS_WGS84) if rows else gpd.GeoDataFrame(
        {"osm_id": [], "waterway": [], "name": []}, geometry=[], crs=CRS_WGS84)
    cache.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(cache, driver="GeoJSON")
    return gdf.to_crs(crs)


# --- HTTP -----------------------------------------------------------------
class RemoteFile:
    """Archivo remoto de sólo lectura con seek/read vía HTTP Range (para abrir zips remotos con zipfile)."""

    def __init__(self, url: str, headers: dict | None = None, chunk: int = 4 << 20):
        import requests
        self.url = url; self.s = requests.Session(); self.h = headers or {}
        r = self.s.head(url, headers=self.h, allow_redirects=True, timeout=60); r.raise_for_status()
        self.size = int(r.headers["Content-Length"]); self.pos = 0; self.chunk = chunk
        self.cache_start = -1; self.cache = b""; self.bytes_fetched = 0

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]; return self.pos

    def tell(self): return self.pos
    def seekable(self): return True

    def _fetch(self, start, end):
        r = self.s.get(self.url, headers={**self.h, "Range": f"bytes={start}-{end}"}, timeout=300)
        if r.status_code != 206:
            raise IOError(f"el servidor no soporta Range (HTTP {r.status_code})")
        self.bytes_fetched += len(r.content); return r.content

    def read(self, n=-1):
        if n < 0:
            n = self.size - self.pos
        end = min(self.pos + n, self.size)
        if not (self.cache_start <= self.pos and end <= self.cache_start + len(self.cache)):
            cs = self.pos; ce = min(max(end, cs + self.chunk), self.size) - 1
            self.cache = self._fetch(cs, ce); self.cache_start = cs
        off = self.pos - self.cache_start
        data = self.cache[off:off + (end - self.pos)]
        self.pos += len(data); return data


def fetch_zip_member(url: str, member_pred, dst: Path, headers=None) -> Path:
    """Extrae de un zip remoto (sin bajarlo entero) el primer miembro que cumpla member_pred(nombre)."""
    import zipfile
    rf = RemoteFile(url, headers)
    with zipfile.ZipFile(rf) as z:
        names = [n for n in z.namelist() if member_pred(n)]
        if not names:
            raise FileNotFoundError(f"ningún miembro cumple el predicado en {url}")
        info = z.getinfo(names[0])
        with z.open(info) as src, open(dst, "wb") as f:
            while True:
                b = src.read(1 << 20)
                if not b:
                    break
                f.write(b)
    print(f"  {names[0]} ({info.file_size/1e6:.1f} MB) extraído; transferidos {rf.bytes_fetched/1e6:.1f} MB de {rf.size/1e6:.0f} MB")
    return dst


def download(url: str, dst: Path, headers=None, allow_redirect_fail=True) -> Path | None:
    """Descarga a dst (con .part). Devuelve None si el servidor redirige a HTML (producto no descargable)."""
    import requests
    if dst.exists() and dst.stat().st_size > 0:
        return dst
    with requests.get(url, headers=headers or {}, stream=True, timeout=900, allow_redirects=False) as r:
        if r.status_code in (301, 302, 303, 307, 308) and allow_redirect_fail:
            print(f"    NO DISPONIBLE: {url}\n      -> redirige a {r.headers.get('Location')}"); return None
        r.raise_for_status()
        if "text/html" in r.headers.get("content-type", ""):
            print(f"    NO DISPONIBLE (HTML): {url}"); return None
        tmp = dst.with_suffix(".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        tmp.rename(dst)
    return dst
