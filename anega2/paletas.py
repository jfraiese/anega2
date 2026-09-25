"""Paletas compartidas (figuras, ficha y visor). Azul reservado para agua.

Los cortes de HAND_CLASES vienen de rules.yml (desborde.hand_min_m.umbrales), más un techo fijo:
por encima de él el HAND no tiene color (riesgo de desborde despreciable a esa altura).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import yaml
from matplotlib.colors import BoundaryNorm, ListedColormap

_HAND_COLORES = ["#b71c1c", "#f4511e", "#ffb300", "#fff3c4"]  # más rojo = HAND más bajo = más riesgo
_HAND_TECHO_M = 5.0  # por encima de esto, sin color


def _fmt(x: float) -> str:
    """Número con coma decimal y sin '.0' de más (1.0 -> '1', 0.5 -> '0,5')."""
    return f"{x:g}".replace(".", ",")


def _hand_cortes() -> list[float]:
    rules = yaml.safe_load((Path(__file__).parent / "rules.yml").read_text())
    umbrales = rules["desborde"]["hand_min_m"]["umbrales"]
    return sorted(umbrales.values())


def _hand_clases() -> list[tuple[float, float, str, str]]:
    cortes = _hand_cortes() + [_HAND_TECHO_M]
    out = []
    lo = 0.0
    for i, hi in enumerate(cortes):
        lab = f"menos de {_fmt(hi)} m" if i == 0 else f"{_fmt(lo)} – {_fmt(hi)} m"
        out.append((lo, hi, _HAND_COLORES[i], lab))
        lo = hi
    return out


HAND_CLASES = _hand_clases()
HAND_CMAP = ListedColormap([c for _, _, c, _ in HAND_CLASES])
HAND_NORM = BoundaryNorm([lo for lo, _, _, _ in HAND_CLASES] + [HAND_CLASES[-1][1]], HAND_CMAP.N)


def hand_clase(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=float); out = np.full(a.shape, np.nan)
    for i, (lo, hi, _, _) in enumerate(HAND_CLASES):
        out[(a >= lo) & (a < hi)] = i
    return out


def hand_para_figura(a: np.ndarray) -> np.ndarray:
    """HAND para graficar con HAND_CMAP/HAND_NORM: NaN (transparente) a partir del techo de clase."""
    a = np.asarray(a, dtype=float)
    return np.where(a < HAND_CLASES[-1][1], a, np.nan)


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def hand_incertidumbre(hand_min: float, hand_min_por_dem: list, sigma_min: float) -> dict:
    v = [x for x in hand_min_por_dem if x is not None and np.isfinite(x)]
    sd = float(np.std(v, ddof=1)) if len(v) > 1 else 0.0
    s = max(float(sigma_min), sd)
    return dict(sigma=round(s, 2), p_lt05=round(100 * _phi((0.5 - hand_min) / s), 1), p_lt1=round(100 * _phi((1.0 - hand_min) / s), 1))
