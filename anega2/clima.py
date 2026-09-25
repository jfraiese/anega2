"""Fase clima · lluvia histórica en el lote: máximos anuales, período de retorno y tormentas mayores.

Fuentes (punto = centroide del lote; sin cuentas):
  ERA5 horaria vía Open-Meteo (archive-api, models=era5, desde 1940; 0,25°). ERA5-Land no se usa: Open-Meteo
  devuelve precipitación nula para ese modelo.
  CHIRPS v2.0 diaria p05 (COG en data.chc.ucsb.edu, desde 1981; 0,05°; sólo entre 50°S y 50°N), un píxel por día.

Salidas: data/raw/clima/era5_<lat>_<lon>.csv (caché horaria), cache/chirps/<lat>_<lon>.csv (caché compartida);
         out/clima_serie_diaria.csv, clima_maximos_anuales.csv, clima_retorno.csv, clima_eventos.csv, clima_stats.md, clima.json
"""
from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .common import df_to_md
from .project import Project

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


# ------------------------------------------------------------------ fuentes
OPENMETEO = "https://archive-api.open-meteo.com/v1/archive"
CHIRPS_URL = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/cogs/p05/{y}/chirps-v2.0.{y}.{m:02d}.{d:02d}.cog"
TZ = "America/Argentina/Buenos_Aires"
ERA5_DESDE = date(1940, 1, 1)
CHIRPS_DESDE = date(1981, 1, 1)


def parse_openmeteo(j: dict) -> pd.Series:
    h = j["hourly"]
    return pd.Series([np.nan if v is None else float(v) for v in h["precipitation"]],
                     index=pd.to_datetime(h["time"]), name="mm", dtype=float).rename_axis("t")


def _read_cache(path: Path) -> pd.Series:
    if not path.exists():
        return pd.Series(dtype=float, name="mm")
    return pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0].rename("mm")


def era5_horaria(lat, lon, cache_csv: Path, hasta: date, get=requests.get) -> pd.Series:
    s = _read_cache(cache_csv)
    ini = s.index.max().date() if len(s) else ERA5_DESDE
    if hasta < ini:
        return s
    partes = [s[s.index < pd.Timestamp(ini)]] if len(s) else []
    d0 = ini
    fetched_any = False
    try:
        while d0 <= hasta:
            d1 = min(hasta, date(d0.year + 10, 1, 1) - timedelta(days=1))
            r = get(OPENMETEO, params=dict(latitude=lat, longitude=lon, start_date=d0.isoformat(), end_date=d1.isoformat(),
                                           hourly="precipitation", models="era5", timezone=TZ), timeout=120)
            r.raise_for_status(); partes.append(parse_openmeteo(r.json()))
            print(f"  ERA5 {d0} → {d1}")
            fetched_any = True
            d0 = d1 + timedelta(days=1)
    except Exception as e:  # noqa: BLE001
        print(f"  [aviso] ERA5 (Open-Meteo) no respondió: {e}; se usa lo que haya en caché")
    if not fetched_any:
        return s
    out = pd.concat(partes); out = out[~out.index.duplicated(keep="last")].sort_index()
    cache_csv.parent.mkdir(parents=True, exist_ok=True); out.rename_axis("t").to_csv(cache_csv)
    return out


def chirps_pixel(lat: float, lon: float) -> tuple[float, float]:
    f = lambda v: math.floor(v / 0.05) * 0.05 + 0.025  # noqa: E731
    return round(f(lat), 3), round(f(lon), 3)


def _leer_chirps_dia(fecha: date, lon: float, lat: float) -> float | None:
    import rasterio
    url = CHIRPS_URL.format(y=fecha.year, m=fecha.month, d=fecha.day)
    try:
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT="30"):
            with rasterio.open(f"/vsicurl/{url}") as s:
                v = float(next(s.sample([(lon, lat)]))[0])
        return None if v < -9000 else v
    except Exception:  # noqa: BLE001
        return None


def chirps_diaria(lat, lon, cache_csv: Path, hasta: date, hilos: int, leer=_leer_chirps_dia, desde: date = CHIRPS_DESDE) -> pd.Series:
    if lat < -50 or lat > 50:
        print("  CHIRPS no cubre latitudes fuera de ±50°: se usa sólo ERA5")
        return pd.Series(dtype=float, name="mm")
    s = _read_cache(cache_csv).dropna()
    faltan = [d.date() for d in pd.date_range(desde, hasta, freq="D") if pd.Timestamp(d) not in s.index]
    if faltan:
        # Probe the first missing day to detect full outages early
        probe_val = leer(faltan[0], lon, lat)
        if probe_val is None:
            print("  [aviso] CHIRPS no respondió; se usa lo que haya en caché (se reintenta en la próxima corrida)")
            return s.reindex(pd.date_range(desde, hasta, freq="D")).rename("mm")
        # First day succeeded, add it and continue with the rest
        nuevos_dict = {pd.Timestamp(faltan[0]): probe_val}
        if len(faltan) > 1:
            print(f"  CHIRPS: {len(faltan) - 1} días por leer ({hilos} hilos)…")
            with ThreadPoolExecutor(hilos) as ex:
                vals = list(ex.map(lambda d: leer(d, lon, lat), faltan[1:]))
            nuevos_dict.update({pd.Timestamp(d): v for d, v in zip(faltan[1:], vals) if v is not None})
            # Warn about failed days
            n_fallos = sum(1 for v in vals if v is None)
            if n_fallos > 0:
                print(f"  [aviso] CHIRPS: {n_fallos} días sin dato (se reintentan en la próxima corrida)")
        nuevos = pd.Series(nuevos_dict, dtype=float, name="mm")
        s = pd.concat([s, nuevos]).sort_index()
        cache_csv.parent.mkdir(parents=True, exist_ok=True); s.rename_axis("t").to_csv(cache_csv)
    return s.reindex(pd.date_range(desde, hasta, freq="D")).rename("mm")


# ------------------------------------------------------------------ fase
DUR_ERA5 = [3, 24, 72]
DUR_CHIRPS = [24, 72]
S1_DESDE = "2014-10-03"


def _diaria(s: pd.Series) -> pd.Series:
    return s.resample("D").sum(min_count=1) if len(s) and _paso_h(s) < 24 else s


def _evento(t, era5, chirps) -> dict:
    t = pd.Timestamp(t); d = t.normalize()
    e24 = era5[t - pd.Timedelta(hours=71):t].rolling(24, min_periods=1).sum().max() if len(era5) else np.nan
    e72 = era5[t - pd.Timedelta(hours=71):t].sum() if len(era5) else np.nan
    c = chirps[d - pd.Timedelta(days=2):d] if len(chirps) else pd.Series(dtype=float)
    r = lambda v: None if v is None or not np.isfinite(v) else round(float(v), 1)  # noqa: E731
    return dict(id=f"{d.date()}_era5", fecha=str(d.date()), era5_24=r(e24), era5_72=r(e72),
                chirps_24=r(c.max()) if len(c) else None, chirps_72=r(c.sum(min_count=1)) if len(c) else None)


def build(era5: pd.Series, chirps: pd.Series, cfg: dict) -> dict:
    era5 = era5.dropna() if len(era5) else era5
    fuentes = {"era5": (era5, DUR_ERA5), "chirps": (chirps.dropna() if len(chirps) else chirps, DUR_CHIRPS)}
    if all(len(s) == 0 for s, _ in fuentes.values()):
        return {"disponible": False}
    out = dict(disponible=True, fuentes={}, gumbel={}, retorno=[], maximos={})
    for nom, (s, durs) in fuentes.items():
        if len(s) == 0:
            out["fuentes"][nom] = out["gumbel"][nom] = out["maximos"][nom] = None; continue
        s = s.asfreq("h" if nom == "era5" else "D")
        out["fuentes"][nom] = dict(desde=str(s.index.min().date()), hasta=str(s.index.max().date()), anios=int(s.index.year.nunique()))
        out["gumbel"][nom] = {}; out["maximos"][nom] = {}
        for dur in durs:
            am = rolling_max_anual(s, dur)
            if len(am) < 10:
                continue
            fit = gumbel_fit(am.mm.values); ic = gumbel_ic(am.mm.values, TS)
            out["gumbel"][nom][str(dur)] = fit
            out["maximos"][nom][str(dur)] = [[int(a), round(float(m), 1), str(pd.Timestamp(f).date())] for a, m, f in am.itertuples(index=False)]
            out["retorno"] += [dict(fuente=nom, dur_h=dur, T=T, mm=round(gumbel_mm(fit, T), 1), lo=round(ic[T][0], 1), hi=round(ic[T][1], 1)) for T in TS]
    base = era5.asfreq("h") if len(era5) else _diaria(chirps).asfreq("D")
    s72 = base.rolling(72 if len(era5) else 3, min_periods=1).sum()
    n, sep = int(cfg.get("eventos_n", 10)), int(cfg.get("separacion_d", 7))
    ev = lambda desde: [_evento(t, era5.asfreq("h") if len(era5) else era5, _diaria(chirps)) for t in desagrupar(s72, n, sep, desde)]  # noqa: E731
    out["eventos"] = dict(historicos=ev(None), sentinel=ev(S1_DESDE))
    return out


def run(p: Project) -> dict:
    cfg = p.cfg.get("clima", {}); fuentes = cfg.get("fuentes", ["era5", "chirps"])
    lon, lat = p.lot_centroid_wgs84(); hasta = date.today() - timedelta(days=6)
    era5 = era5_horaria(lat, lon, p.data_raw / "clima" / f"era5_{lat:.3f}_{lon:.3f}.csv", hasta) if "era5" in fuentes else pd.Series(dtype=float)
    chirps = pd.Series(dtype=float)
    if "chirps" in fuentes:
        clat, clon = chirps_pixel(lat, lon); cache = p.cache / "chirps" / f"{clat:.3f}_{clon:.3f}.csv"
        if cache.exists() or p.confirm(f"Leer CHIRPS diario 1981-hoy para el píxel {clat}, {clon} (≈ 16.000 lecturas, ~25 min la primera vez; queda en {cache})"):
            chirps = chirps_diaria(lat, lon, cache, date.today() - timedelta(days=45), int(cfg.get("hilos_chirps", 16)))
    j = build(era5, chirps, cfg)
    if j.get("disponible"):
        j["punto"] = dict(lat=round(lat, 5), lon=round(lon, 5))
        if j["fuentes"].get("chirps"):
            j["fuentes"]["chirps"]["pixel"] = list(chirps_pixel(lat, lon))
    o = p.out
    json.dump(j, open(o / "clima.json", "w"), ensure_ascii=False, indent=1)
    if not j.get("disponible"):
        print("CLIMA: sin datos de lluvia (sin red o fuentes caídas); el visor lo informa y sar con eventos: auto se saltea.")
        return j
    pd.DataFrame({"era5_mm": _diaria(era5) if len(era5) else pd.Series(dtype=float), "chirps_mm": chirps}).rename_axis("fecha").to_csv(o / "clima_serie_diaria.csv", float_format="%.1f")
    am = pd.DataFrame([dict(fuente=f, dur_h=int(d), anio=a, mm=m, fecha=fe) for f, g in j["maximos"].items() if g for d, rows in g.items() for a, m, fe in rows])
    am.to_csv(o / "clima_maximos_anuales.csv", index=False)
    rt = pd.DataFrame(j["retorno"]); rt.to_csv(o / "clima_retorno.csv", index=False)
    evs = pd.DataFrame([dict(tipo=k, **e) for k, lst in j["eventos"].items() for e in lst]); evs.to_csv(o / "clima_eventos.csv", index=False)
    (o / "clima_stats.md").write_text(
        "# Lluvia histórica en el lote\n\n"
        f"ERA5 (Open-Meteo, 0,25°): {j['fuentes'].get('era5') or 'sin datos'} · CHIRPS v2 (0,05°): {j['fuentes'].get('chirps') or 'sin datos'}.\n"
        "Período de retorno por Gumbel (momentos) sobre máximos anuales; intervalo 90 % por bootstrap. ERA5 subestima picos "
        "convectivos: comparar con CHIRPS.\n\n## Período de retorno (mm)\n\n" + df_to_md(rt) + "\n\n## Tormentas mayores\n\n" + df_to_md(evs) + "\n")
    r24 = {r["T"]: r["mm"] for r in j["retorno"] if r["fuente"] == "era5" and r["dur_h"] == 24}
    p.summary_line("CLIMA (lluvia histórica)", [
        f"ERA5 {j['fuentes'].get('era5')} · CHIRPS {j['fuentes'].get('chirps')}",
        "24 h (ERA5): " + " · ".join(f"T{T}={mm:.0f} mm" for T, mm in r24.items()),
        "Mayores: " + ", ".join(f"{e['fecha']} ({e['era5_72']} mm/72 h)" for e in j["eventos"]["historicos"][:5])])
    return j


def resolve_events(p: Project) -> list[dict]:
    ev = p.cfg.get("sar", {}).get("eventos", "auto")
    if ev != "auto":
        return list(ev or [])
    f = p.out / "clima.json"
    j = json.loads(f.read_text()) if f.exists() else {}
    if not j.get("disponible"):
        print("  [aviso] sar.eventos = auto pero no hay out/clima.json con datos (correr la fase clima)")
        return []
    def _descr(e: dict) -> str:
        if e.get("era5_72") is not None:
            return f"Tormenta de {e['era5_72']:.0f} mm en 72 h (ERA5)"
        if e.get("chirps_72") is not None:
            return f"Tormenta de {e['chirps_72']:.0f} mm en 72 h (CHIRPS)"
        return "Tormenta (sin dato de mm)"
    return [dict(id=e["id"], fecha=e["fecha"], descr=_descr(e)) for e in j["eventos"]["sentinel"]]
