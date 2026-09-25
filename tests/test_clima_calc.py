"""Cálculos puros de la fase clima (sin red)."""
import numpy as np
import pandas as pd
import pytest

from anega2 import clima


def _serie_horaria(anios=(2000, 2001, 2002), picos=None):
    idx = pd.date_range(f"{anios[0]}-01-01", f"{anios[-1]}-12-31 23:00", freq="h")
    s = pd.Series(0.0, index=idx)
    for t, mm in (picos or {}).items():
        s[pd.Timestamp(t)] = mm
    return s


def test_rolling_max_anual_24h_suma_ventana_y_fecha_fin():
    s = _serie_horaria(picos={"2000-03-10 10:00": 30, "2000-03-10 20:00": 20, "2001-07-01 00:00": 5, "2002-02-02 02:00": 80})
    df = clima.rolling_max_anual(s, 24)
    assert list(df.anio) == [2000, 2001, 2002]
    assert df.loc[df.anio == 2000, "mm"].item() == pytest.approx(50)
    assert df.loc[df.anio == 2002, "mm"].item() == pytest.approx(80)
    # la fecha es el fin de la primera ventana que alcanza el máximo
    assert df.loc[df.anio == 2000, "fecha"].item() == pd.Timestamp("2000-03-10 20:00")


def test_rolling_max_anual_descarta_anios_incompletos():
    s = _serie_horaria(picos={"2001-05-05 05:00": 10})
    s["2001-01-01":"2001-12-01"] = np.nan          # 2001 queda con 30 días
    df = clima.rolling_max_anual(s, 24)
    assert 2001 not in set(df.anio)


def test_rolling_max_anual_diaria_72h():
    idx = pd.date_range("2000-01-01", "2000-12-31", freq="D")
    s = pd.Series(0.0, index=idx); s["2000-04-01"] = 10; s["2000-04-02"] = 20; s["2000-04-03"] = 30
    df = clima.rolling_max_anual(s, 72)
    assert df.mm.item() == pytest.approx(60)


def test_gumbel_ida_y_vuelta():
    rng = np.random.default_rng(1)
    x = rng.gumbel(80, 25, 60)
    fit = clima.gumbel_fit(x)
    assert fit["n"] == 60
    for T in clima.TS:
        assert clima.gumbel_T(fit, clima.gumbel_mm(fit, T)) == pytest.approx(T, rel=1e-6)
    assert clima.gumbel_mm(fit, 100) > clima.gumbel_mm(fit, 10) > clima.gumbel_mm(fit, 2)


def test_gumbel_T_fuera_de_rango():
    fit = {"mu": 80.0, "beta": 20.0, "n": 50}
    assert clima.gumbel_T(fit, 10_000) == float("inf")
    assert clima.gumbel_T(fit, 0) == pytest.approx(1.0, abs=1e-6)


def test_gumbel_ic_reproducible_y_contiene_estimacion():
    rng = np.random.default_rng(2); x = rng.gumbel(80, 25, 50)
    a = clima.gumbel_ic(x, [10, 100], n_boot=200, seed=0)
    b = clima.gumbel_ic(x, [10, 100], n_boot=200, seed=0)
    assert a == b
    fit = clima.gumbel_fit(x)
    lo, hi = a[10]
    assert lo < clima.gumbel_mm(fit, 10) < hi


def test_desagrupar_separa_y_ordena():
    idx = pd.date_range("2010-01-01", "2010-12-31", freq="h")
    s72 = pd.Series(0.0, index=idx)
    s72["2010-03-01"] = 100; s72["2010-03-03"] = 90   # mismo evento (2 días)
    s72["2010-06-01"] = 80; s72["2010-09-01"] = 120
    picos = clima.desagrupar(s72, n=5, separacion_d=7)
    assert picos == [pd.Timestamp("2010-09-01"), pd.Timestamp("2010-03-01"), pd.Timestamp("2010-06-01")]


def test_desagrupar_desde():
    idx = pd.date_range("2010-01-01", "2016-12-31", freq="D")
    s72 = pd.Series(0.0, index=idx); s72["2012-01-01"] = 200; s72["2015-01-01"] = 50
    assert clima.desagrupar(s72, n=3, separacion_d=7, desde="2014-10-03") == [pd.Timestamp("2015-01-01")]
