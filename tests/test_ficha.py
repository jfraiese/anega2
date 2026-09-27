import json
from types import SimpleNamespace

import pandas as pd

from anega2 import ficha


def test_frecuencia_ficha_desde_clima(tmp_path):
    p = SimpleNamespace(out=tmp_path)
    assert ficha._frecuencia(p) == "Sin datos de frecuencia de lluvias."
    (tmp_path / "clima.json").write_text(json.dumps({"disponible": True, "gumbel": {"era5": {"24": {"mu": 70.0, "beta": 13.0}}}}))
    assert ficha._frecuencia(p) == "Frecuencia: 100 mm en 24 h ≈ cada 11 años (ERA5)."


def test_sat_numbers_cuenta_sin_pasada():
    sar = pd.DataFrame(dict(evento=["referencia_seca", "a", "a", "b", "c"],
                            escena=["S1_ref", "S1_pre", "S1_post", "SIN COBERTURA", "SIN PASADA A TIEMPO"],
                            pct_agua_lote=[0.0, 0.0, 2.0, None, None]))
    ctx = SimpleNamespace(jrc=pd.DataFrame({"occ>0 %": [0.0]}), sar=sar)
    lote_occ, n_s1, s1_max, sin_cob, sin_pasada = ficha._sat_numbers(ctx)
    assert (lote_occ, n_s1, s1_max, sin_cob, sin_pasada) == (0.0, 2, 2.0, 1, 1)
    assert ficha._sin_radar_txt(1, 1) == "1 evento sin cobertura radar, 1 sin pasada a tiempo"
    assert ficha._sin_radar_txt(2, 0) == "2 eventos sin cobertura radar"
    assert ficha._sin_radar_txt(0, 3) == "3 sin pasada a tiempo"
    assert ficha._sin_radar_txt(0, 0) == ""
