"""Fase clima de punta a punta con series sintéticas (sin red)."""
import json
from datetime import date

import numpy as np
import pandas as pd

from anega2 import clima

CFG = dict(fuentes=["era5", "chirps"], hilos_chirps=2, eventos_n=3, separacion_d=7)


def _era5(anios=range(1990, 2021), seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{anios[0]}-01-01", f"{anios[-1]}-12-31 23:00", freq="h")
    s = pd.Series(0.0, index=idx)
    for a in anios:
        t = pd.Timestamp(f"{a}-{rng.integers(1, 13):02d}-10 12:00")
        s[t] = rng.gumbel(60, 20)
    s[pd.Timestamp("2016-04-05 12:00")] = 300.0     # la mayor, post-2014
    return s


def _chirps(anios=range(1990, 2021)):
    idx = pd.date_range(f"{anios[0]}-01-01", f"{anios[-1]}-12-31", freq="D")
    s = pd.Series(0.0, index=idx)
    s[pd.Timestamp("2016-04-05")] = 300.0            # la mayor, post-2014, sin dato ERA5
    return s


def test_build_estructura_y_retorno():
    j = clima.build(_era5(), pd.Series(dtype=float), CFG)
    assert j["disponible"] and j["fuentes"]["chirps"] is None
    assert set(j["gumbel"]["era5"]) == {"3", "24", "72"}
    r10 = next(r for r in j["retorno"] if r["fuente"] == "era5" and r["dur_h"] == 24 and r["T"] == 10)
    assert r10["lo"] < r10["mm"] < r10["hi"]
    assert j["eventos"]["historicos"][0]["fecha"] == "2016-04-05"
    assert all(e["fecha"] >= "2014-10-03" for e in j["eventos"]["sentinel"])
    assert j["eventos"]["sentinel"][0]["id"] == "2016-04-05_era5"


def test_build_sin_fuentes():
    assert clima.build(pd.Series(dtype=float), pd.Series(dtype=float), CFG) == {"disponible": False}


def test_run_sin_fuentes(tmp_project, monkeypatch):
    monkeypatch.setattr(clima, "era5_horaria", lambda *a, **k: pd.Series(dtype=float))
    monkeypatch.setattr(clima, "chirps_diaria", lambda *a, **k: pd.Series(dtype=float))
    out = clima.run(tmp_project)
    assert out == {"disponible": False}
    assert json.loads((tmp_project.out / "clima.json").read_text()) == {"disponible": False}


def test_run_escribe_salidas(tmp_project, monkeypatch):
    monkeypatch.setattr(clima, "era5_horaria", lambda *a, **k: _era5())
    monkeypatch.setattr(clima, "chirps_diaria", lambda *a, **k: _era5().resample("D").sum())
    clima.run(tmp_project)
    for f in ["clima_serie_diaria.csv", "clima_maximos_anuales.csv", "clima_retorno.csv", "clima_eventos.csv", "clima_stats.md", "clima.json"]:
        assert (tmp_project.out / f).exists(), f


def test_resolve_events_manual_y_auto(tmp_project):
    tmp_project.cfg["sar"]["eventos"] = [{"id": "x", "fecha": "2020-01-01"}]
    assert clima.resolve_events(tmp_project) == [{"id": "x", "fecha": "2020-01-01"}]
    tmp_project.cfg["sar"]["eventos"] = "auto"
    (tmp_project.out / "clima.json").write_text(json.dumps(clima.build(_era5(), pd.Series(dtype=float), CFG)))
    ev = clima.resolve_events(tmp_project)
    assert ev[0] == {"id": "2016-04-05_era5", "fecha": "2016-04-05", "descr": "Tormenta de 300 mm en 72 h (ERA5)"}


def test_resolve_events_auto_sin_era5_usa_chirps(tmp_project):
    """ERA5 caído (disponible sólo por CHIRPS): resolve_events no debe reventar por era5_72 == None."""
    tmp_project.cfg["sar"]["eventos"] = "auto"
    j = clima.build(pd.Series(dtype=float), _chirps(), CFG)
    (tmp_project.out / "clima.json").write_text(json.dumps(j))
    ev = clima.resolve_events(tmp_project)
    assert ev
    assert all(e["descr"].endswith("(CHIRPS)") for e in ev)
