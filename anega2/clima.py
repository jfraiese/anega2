"""Fase clima · lluvia histórica en el lote: máximos anuales, período de retorno y tormentas mayores.

Fuentes (punto = centroide del lote; sin cuentas):
  ERA5 horaria vía Open-Meteo (archive-api, models=era5, desde 1940; 0,25°). ERA5-Land no se usa: Open-Meteo
  devuelve precipitación nula para ese modelo.
  CHIRPS v2.0 diaria p05 (COG en data.chc.ucsb.edu, desde 1981; 0,05°; sólo entre 50°S y 50°N), un píxel por día.

Salidas: data/raw/clima/era5_<lat>_<lon>.csv (caché horaria), cache/chirps/<lat>_<lon>.csv (caché compartida);
         out/clima_serie_diaria.csv, clima_maximos_anuales.csv, clima_retorno.csv, clima_eventos.csv, clima_stats.md, clima.json
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

TS = [2, 5, 10, 25, 50, 100]
EULER = 0.5772156649


# ------------------------------------------------------------------ cálculos puros
def _paso_h(s: pd.Series) -> float:
    return (s.index[1] - s.index[0]) / pd.Timedelta(hours=1)


def rolling_max_anual(s: pd.Series, horas: int, min_dias: int = 300) -> pd.DataFrame:
    """Máximo anual de la suma móvil de `horas` (serie horaria o diaria, índice regular). fecha = fin de la ventana."""
    n = max(1, int(round(horas / _paso_h(s))))
    r = s.rolling(n, min_periods=n).sum()
    dias_ok = s.notna().groupby(s.index.year).sum() * _paso_h(s) / 24
    rows = []
    for anio, g in r.groupby(r.index.year):
        if dias_ok.get(anio, 0) < min_dias or g.notna().sum() == 0:
            continue
        rows.append(dict(anio=int(anio), mm=float(g.max()), fecha=g.idxmax()))
    return pd.DataFrame(rows, columns=["anio", "mm", "fecha"])


def gumbel_fit(x) -> dict:
    x = np.asarray(x, dtype=float); x = x[np.isfinite(x)]
    beta = float(np.std(x, ddof=1) * math.sqrt(6) / math.pi)
    return dict(mu=float(np.mean(x) - EULER * beta), beta=beta, n=int(len(x)))


def gumbel_mm(fit: dict, T: float) -> float:
    return float(fit["mu"] - fit["beta"] * math.log(-math.log(1 - 1 / T)))


def gumbel_T(fit: dict, mm: float) -> float:
    p_exc = 1 - math.exp(-math.exp(-(mm - fit["mu"]) / fit["beta"]))
    return float("inf") if p_exc <= 0 else float(1 / p_exc)


def gumbel_ic(x, Ts, n_boot: int = 1000, seed: int = 0, nivel: float = 0.9) -> dict:
    x = np.asarray(x, dtype=float); x = x[np.isfinite(x)]
    rng = np.random.default_rng(seed)
    sims = np.array([[gumbel_mm(gumbel_fit(rng.choice(x, len(x), replace=True)), T) for T in Ts] for _ in range(n_boot)])
    a = (1 - nivel) / 2
    return {T: (float(np.quantile(sims[:, i], a)), float(np.quantile(sims[:, i], 1 - a))) for i, T in enumerate(Ts)}


def desagrupar(s72: pd.Series, n: int, separacion_d: int, desde: str | None = None) -> list:
    """Picos de la serie de sumas de 72 h separados al menos `separacion_d` días, de mayor a menor."""
    s = s72.dropna()
    if desde:
        s = s[s.index >= pd.Timestamp(desde)]
    s = s[s > 0].sort_values(ascending=False, kind="stable")     # empates: gana el primero en el tiempo
    sep = pd.Timedelta(days=separacion_d); picos = []
    for t in s.index:
        if all(abs(t - q) >= sep for q in picos):
            picos.append(t)
            if len(picos) == n:
                break
    return picos
