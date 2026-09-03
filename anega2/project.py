"""Proyecto anega2: configuración (defaults + project.yml), rutas, CRS automático y AOI."""
from __future__ import annotations

import copy
import math
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECTS_DIR = REPO_ROOT / "projects"
CACHE_DIR = REPO_ROOT / "cache"
CRS_WGS84 = "EPSG:4326"


def _deep_merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in (b or {}).items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def load_defaults() -> dict:
    return yaml.safe_load((Path(__file__).parent / "defaults.yml").read_text())


def in_argentina(lon: float, lat: float) -> bool:
    return -74.5 <= lon <= -53.0 and -55.5 <= lat <= -21.5


def resolve_crs(lon: float, lat: float) -> tuple[str, str]:
    """(código EPSG, descripción). Faja POSGAR 2007 en Argentina; UTM en el resto."""
    if in_argentina(lon, lat):
        faja = int(min(7, max(1, round((lon + 72) / 3) + 1)))
        return f"EPSG:{5342 + faja}", f"POSGAR 2007 / Argentina faja {faja}"
    zone = int(math.floor((lon + 180) / 6) + 1)
    epsg = (32700 if lat < 0 else 32600) + zone
    return f"EPSG:{epsg}", f"WGS 84 / UTM zona {zone}{'S' if lat < 0 else 'N'}"


@dataclass
class Project:
    name: str
    cfg: dict
    dir: Path
    yes: bool = False                 # --si: no pedir confirmación antes de descargas grandes
    _crs: str | None = field(default=None, repr=False)

    # ---------------------------------------------------------------- carga
    @classmethod
    def load(cls, name: str, yes: bool = False) -> "Project":
        d = PROJECTS_DIR / name
        f = d / "project.yml"
        if not f.exists():
            raise FileNotFoundError(f"no existe {f}; crealo con: anega2 init {name} --kml <archivo.kml>")
        cfg = _deep_merge(load_defaults(), yaml.safe_load(f.read_text()) or {})
        cfg["nombre"] = name
        return cls(name=name, cfg=cfg, dir=d, yes=yes)

    @classmethod
    def create(cls, name: str, kml: Path, titulo: str | None = None, overwrite: bool = False) -> "Project":
        d = PROJECTS_DIR / name
        if (d / "project.yml").exists() and not overwrite:
            raise FileExistsError(f"ya existe {d / 'project.yml'} (usá --sobrescribir)")
        d.mkdir(parents=True, exist_ok=True)
        kml = Path(kml)
        if not kml.exists():
            raise FileNotFoundError(kml)
        shutil.copy(kml, d / "lote.kml")
        cfg = load_defaults()
        cfg["nombre"] = name
        cfg["titulo"] = titulo or name
        cfg["kml"] = "lote.kml"
        (d / "project.yml").write_text(
            "# Proyecto anega2. Editá lo que necesites; lo que no esté acá toma el valor de anega2/defaults.yml\n"
            + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
        return cls.load(name)

    @staticmethod
    def list_projects() -> list[str]:
        return sorted(p.parent.name for p in PROJECTS_DIR.glob("*/project.yml"))

    # ---------------------------------------------------------------- rutas
    @property
    def titulo(self) -> str:
        return self.cfg.get("titulo") or self.name

    @property
    def kml_path(self) -> Path:
        return self.dir / self.cfg["kml"]

    def _d(self, *parts) -> Path:
        p = self.dir.joinpath(*parts); p.mkdir(parents=True, exist_ok=True); return p

    @property
    def data_raw(self) -> Path: return self._d("data", "raw")
    @property
    def data_proc(self) -> Path: return self._d("data", "proc")
    @property
    def out(self) -> Path: return self._d("out")
    @property
    def web(self) -> Path: return self._d("web")
    @property
    def cache(self) -> Path: CACHE_DIR.mkdir(exist_ok=True); return CACHE_DIR
    @property
    def aoi_gpkg(self) -> Path: return self.out / "aoi.gpkg"
    @property
    def buffers(self) -> dict: return self.cfg["buffers"]
    @property
    def aoi_m(self) -> float: return float(self.cfg["buffers"]["aoi_m"])
    @property
    def hidro_m(self) -> float: return float(self.cfg["buffers"]["hidro_m"])

    # ---------------------------------------------------------------- CRS
    def lot_centroid_wgs84(self) -> tuple[float, float]:
        import geopandas as gpd
        g = gpd.read_file(self.kml_path)
        g = g[g.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
        if len(g) == 0:
            raise ValueError(f"{self.kml_path.name} no tiene polígonos")
        c = g.to_crs(CRS_WGS84).geometry.union_all().centroid
        return float(c.x), float(c.y)

    @property
    def crs(self) -> str:
        if self._crs is None:
            c = self.cfg.get("crs", "auto")
            if isinstance(c, str) and c.lower() != "auto":
                self._crs = c
            else:
                lon, lat = self.lot_centroid_wgs84()
                self._crs, _ = resolve_crs(lon, lat)
        return self._crs

    @property
    def crs_descr(self) -> str:
        lon, lat = self.lot_centroid_wgs84()
        code, descr = resolve_crs(lon, lat)
        return descr if code == self.crs else self.crs

    @property
    def es_argentina(self) -> bool:
        return in_argentina(*self.lot_centroid_wgs84())

    # ---------------------------------------------------------------- AOI
    def load_aoi(self) -> dict:
        """{'lote','aoi','hidro'} (shapely en self.crs), 'gdf', 'crs', 'aoi_m', 'hidro_m'. Requiere aoi.run()."""
        import geopandas as gpd
        if not self.aoi_gpkg.exists():
            from . import aoi as _aoi
            _aoi.run(self)
        gdf = gpd.read_file(self.aoi_gpkg, layer="aoi")
        d = {r["name"]: r.geometry for _, r in gdf.iterrows()}
        d.update(gdf=gdf, crs=self.crs, aoi_m=self.aoi_m, hidro_m=self.hidro_m)
        return d

    # ---------------------------------------------------------------- interacción
    def confirm(self, msg: str) -> bool:
        """Pide confirmación antes de una descarga grande o paso costoso (salvo --si o stdin no interactivo)."""
        if self.yes:
            print(f"[auto-OK] {msg}"); return True
        if not sys.stdin.isatty():
            print(f"[sin terminal, se asume OK] {msg}"); return True
        r = input(f"{msg}\n¿Continuar? [S/n] ").strip().lower()
        return r in ("", "s", "si", "sí", "y", "yes")

    def summary_line(self, phase: str, lines: list[str]) -> None:
        print(f"\nRESUMEN {phase} · {self.titulo}")
        for i, l in enumerate(lines, 1):
            print(f"{i}. {l}")
