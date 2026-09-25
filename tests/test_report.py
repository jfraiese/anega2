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
