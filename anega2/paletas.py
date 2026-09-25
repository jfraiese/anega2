"""Paletas compartidas (figuras, ficha y visor). Azul reservado para agua."""
from __future__ import annotations

import math

import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap

HAND_CLASES = [(0.0, 0.5, "#b71c1c", "menos de 0,5 m"), (0.5, 1.0, "#f4511e", "0,5 – 1 m"),
               (1.0, 2.0, "#ffb300", "1 – 2 m"), (2.0, 5.0, "#fff3c4", "2 – 5 m")]
HAND_CMAP = ListedColormap([c for _, _, c, _ in HAND_CLASES])
HAND_NORM = BoundaryNorm([lo for lo, _, _, _ in HAND_CLASES] + [HAND_CLASES[-1][1]], HAND_CMAP.N)


def hand_clase(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=float); out = np.full(a.shape, np.nan)
    for i, (lo, hi, _, _) in enumerate(HAND_CLASES):
        out[(a >= lo) & (a < hi)] = i
    return out


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def hand_incertidumbre(hand_min: float, hand_min_por_dem: list, sigma_min: float) -> dict:
    v = [x for x in hand_min_por_dem if x is not None and np.isfinite(x)]
    sd = float(np.std(v, ddof=1)) if len(v) > 1 else 0.0
    s = max(float(sigma_min), sd)
    return dict(sigma=round(s, 2), p_lt05=round(100 * _phi((0.5 - hand_min) / s), 1), p_lt1=round(100 * _phi((1.0 - hand_min) / s), 1))
