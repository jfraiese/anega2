"""Fuentes de lluvia de la fase clima, sin red (respuestas simuladas)."""
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from anega2 import clima

FIX = Path(__file__).parent / "fixtures"


class _Resp:
    def __init__(self, j, status=200): self._j = j; self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f"HTTP {self.status_code}")
    def json(self): return self._j


def test_parse_openmeteo_hora_local_y_nulos():
    s = clima.parse_openmeteo(json.loads((FIX / "openmeteo_era5.json").read_text()))
    assert s.index[0] == pd.Timestamp("2015-08-09 00:00")
    assert s.iloc[1] == 12.0 and np.isnan(s.iloc[2])


def test_era5_pide_solo_lo_faltante(tmp_path):
    cache = tmp_path / "era5.csv"
    pd.Series([1.0, 2.0], index=pd.to_datetime(["2020-01-01 00:00", "2020-01-01 01:00"]), name="mm").rename_axis("t").to_csv(cache)
    pedidos = []
    def get(url, params, timeout):
        pedidos.append((params["start_date"], params["end_date"]))
        t = pd.date_range(params["start_date"], f"{params['end_date']} 23:00", freq="h")
        return _Resp({"hourly": {"time": [x.strftime("%Y-%m-%dT%H:%M") for x in t], "precipitation": [0.0] * len(t)}})
    s = clima.era5_horaria(-34.4, -59.42, cache, hasta=date(2020, 1, 3), get=get)
    assert pedidos == [("2020-01-01", "2020-01-03")]          # re-pide desde el último día cacheado
    assert s.index.max() == pd.Timestamp("2020-01-03 23:00")
    assert pd.read_csv(cache, index_col=0, parse_dates=True).shape[0] == len(s)



def test_era5_retoma_desde_el_ultimo_dato_valido(tmp_path):
    """Si la cola de la caché es NaN (ERA5 todavía sin publicar esas horas), se re-pide desde el último dato válido."""
    cache = tmp_path / "era5.csv"
    t = pd.date_range("2020-01-01 00:00", "2020-01-03 23:00", freq="h")
    v = np.where(t < pd.Timestamp("2020-01-02"), 1.0, np.nan)
    pd.Series(v, index=t, name="mm").rename_axis("t").to_csv(cache)
    pedidos = []
    def get(url, params, timeout):
        pedidos.append((params["start_date"], params["end_date"]))
        tt = pd.date_range(params["start_date"], f"{params['end_date']} 23:00", freq="h")
        return _Resp({"hourly": {"time": [x.strftime("%Y-%m-%dT%H:%M") for x in tt], "precipitation": [0.0] * len(tt)}})
    s = clima.era5_horaria(-34.4, -59.42, cache, hasta=date(2020, 1, 3), get=get)
    assert pedidos == [("2020-01-01", "2020-01-03")]
    assert s.notna().all() and s.index.max() == pd.Timestamp("2020-01-03 23:00")

def test_era5_sin_red_devuelve_cache(tmp_path, capsys):
    cache = tmp_path / "era5.csv"
    def get(url, params, timeout): raise ConnectionError("sin red")
    s = clima.era5_horaria(-34.4, -59.42, cache, hasta=date(1941, 1, 1), get=get)
    assert len(s) == 0
    assert "sin red" in capsys.readouterr().out


def test_chirps_pixel_centro():
    assert clima.chirps_pixel(-34.4038, -59.4205) == pytest.approx((-34.425, -59.425))


def test_chirps_diaria_cachea_y_no_guarda_fallas(tmp_path):
    cache = tmp_path / "c.csv"
    llamadas = []
    def leer(f, lon, lat):
        llamadas.append(f)
        return None if f == date(2000, 1, 2) else 3.0
    s = clima.chirps_diaria(-34.4, -59.4, cache, hasta=date(2000, 1, 3), hilos=2, leer=leer, desde=date(2000, 1, 1))
    assert s.loc["2000-01-01"] == 3.0 and np.isnan(s.loc["2000-01-02"])
    llamadas.clear()
    clima.chirps_diaria(-34.4, -59.4, cache, hasta=date(2000, 1, 3), hilos=2, leer=leer, desde=date(2000, 1, 1))
    assert llamadas == [date(2000, 1, 2)]                     # sólo reintenta el día que falló


def test_chirps_fuera_de_cobertura(tmp_path):
    s = clima.chirps_diaria(-54.8, -68.3, tmp_path / "c.csv", hasta=date(2000, 1, 3), hilos=1, leer=lambda *a: 1.0)
    assert len(s) == 0


def test_era5_sin_reescribir_cache_si_falla(tmp_path, capsys):
    cache = tmp_path / "era5.csv"
    # Create cache with 3 full days (72 hours)
    orig_data = pd.Series([1.0] * 72,
                          index=pd.date_range("2020-01-01", periods=72, freq="h"),
                          name="mm").rename_axis("t")
    orig_data.to_csv(cache)

    def get(url, params, timeout):
        raise ConnectionError("sin red")

    s = clima.era5_horaria(-34.4, -59.42, cache, hasta=date(2020, 1, 5), get=get)
    assert len(s) == 72
    assert pd.read_csv(cache, index_col=0, parse_dates=True).shape[0] == 72
    assert "sin red" in capsys.readouterr().out


def test_era5_no_reescribir_si_hasta_menor(tmp_path):
    cache = tmp_path / "era5.csv"
    # Create cache with 3 full days
    orig_data = pd.Series([1.0] * 72,
                          index=pd.date_range("2020-01-01", periods=72, freq="h"),
                          name="mm").rename_axis("t")
    orig_data.to_csv(cache)

    get_called = []
    def get(url, params, timeout):
        get_called.append(True)
        raise RuntimeError("should not be called")

    s = clima.era5_horaria(-34.4, -59.42, cache, hasta=date(2019, 12, 15), get=get)
    assert len(s) == 72
    assert len(get_called) == 0
    assert pd.read_csv(cache, index_col=0, parse_dates=True).shape[0] == 72


def test_chirps_diaria_probe_falla_sin_pool(tmp_path, capsys):
    cache = tmp_path / "c.csv"
    leer_calls = []
    def leer(f, lon, lat):
        leer_calls.append(f)
        return None  # Probe fails

    s = clima.chirps_diaria(-34.4, -59.4, cache, hasta=date(2000, 1, 3), hilos=2, leer=leer, desde=date(2000, 1, 1))
    assert len(leer_calls) == 1  # Only the probe call
    assert "CHIRPS no respondió" in capsys.readouterr().out


def test_chirps_diaria_aviso_dias_sin_dato(tmp_path, capsys):
    cache = tmp_path / "c.csv"
    llamadas = []
    def leer(f, lon, lat):
        llamadas.append(f)
        # First day succeeds (probe), next days: 2nd fails, 3rd succeeds
        if f == date(2000, 1, 2):
            return None
        return 3.0

    s = clima.chirps_diaria(-34.4, -59.4, cache, hasta=date(2000, 1, 3), hilos=2, leer=leer, desde=date(2000, 1, 1))
    output = capsys.readouterr().out
    assert "1 días sin dato" in output
