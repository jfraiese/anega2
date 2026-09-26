import pandas as pd

from anega2 import report


def test_eventos_analizados_desde_sar_stats():
    R = {"sar": pd.DataFrame({"evento": ["referencia_seca", "2016-04-05_era5", "2016-04-05_era5", "2024-03-12_era5"]})}
    assert report.eventos_analizados(R) == ["2016-04-05", "2024-03-12"]


def test_eventos_analizados_sin_sar():
    assert report.eventos_analizados({"sar": None}) == []


def test_etiqueta():
    assert report.etiqueta("MEDIO-BAJO") == ("Riesgo medio-bajo", "Con lluvias muy grandes puede juntar algo de agua.")
    assert report.etiqueta("ALTO")[0] == "Riesgo alto"


CL = {"disponible": True, "gumbel": {"era5": {"24": {"mu": 70.0, "beta": 13.0}}, "chirps": {"24": {"mu": 50.0, "beta": 8.0}}}}


def test_anios_txt_tope():
    assert report.anios_txt(12.4) == "12"
    assert report.anios_txt(100) == "100"
    assert report.anios_txt(518548) == "más de 100"
    assert report.anios_txt(float("inf")) == "más de 100"


def test_frecuencia_100mm_con_tope():
    s = report.frecuencia_100mm(CL)                       # ERA5 ≈ 10,6 años; CHIRPS ≈ 500 años → tope
    assert s.startswith("100 mm en 24 h ≈ cada 11 años (ERA5; CHIRPS: más de 100)")
    assert report.frecuencia_100mm({"disponible": True, "gumbel": {"era5": {"24": {"mu": 20.0, "beta": 5.0}}}}) == \
        "100 mm en 24 h ≈ más rara que una vez cada 100 años (ERA5)"


def test_frecuencia_100mm_sin_datos():
    assert report.frecuencia_100mm(None) is None
    assert report.frecuencia_100mm({"disponible": False}) is None
    assert report.frecuencia_100mm({"disponible": True, "gumbel": {"era5": {"24": {"mu": 70.0, "beta": 0.0}}}}) is None


def test_etiqueta_sentinel_analizados():
    import inspect
    src = inspect.getsource(report.build)
    assert "Eventos Sentinel-1 analizados" in src and "configurados" not in src
