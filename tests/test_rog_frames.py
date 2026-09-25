import json

import numpy as np
import pytest
from rasterio.transform import from_origin

from anega2 import rog


def test_encode_frame_satura_y_redondea():
    h = np.array([[rog.H_FILM, 0.054 + rog.H_FILM], [0.2 + rog.H_FILM, 9.0]])
    assert rog.encode_frame(h).tolist() == [[0, 5], [20, 255]]
    assert rog.encode_frame(h).dtype == np.uint8


def test_lote_por_hora():
    fr = np.zeros((4, 2, 2), np.uint8); lot = np.array([[True, True], [False, False]])
    fr[1, 0, 0] = 10; fr[2, 0, :] = [30, 6]; fr[2, 1, 1] = 200    # la celda fuera del lote no cuenta
    d = rog.lote_por_hora(fr, lot)
    assert d["hmax_lote_cm"] == [0, 10, 30, 0]
    assert d["pct_lote_gt5cm"] == [0, 50, 100, 0] and d["pct_lote_gt20cm"] == [0, 0, 50, 0]
    assert d["horas_con_agua_lote"] == 2 and d["hora_pico_lote"] == 2


def test_run_scenario_chico_guarda_cuadros(tmp_project):
    z = np.fromfunction(lambda r, c: 10 + 0.01 * c + 0.3 * ((r - 7) ** 2 + (c - 7) ** 2) ** 0.5 / 10, (15, 15)).astype("float32")
    z[7, 7] -= 0.5                                        # un pozo donde se junta agua
    tr = from_origin(5_500_000, 6_200_000, 30, 30); lot = np.zeros_like(z, bool); lot[6:9, 6:9] = True
    sc = rog.build_scenarios(dict(grilla=dict(P_mm=[100], dur_h=[3], suelo=["normal"]), Ks_mm_h=10, Ks_sat_mm_h=2, drenaje_h=2))["P100_3h"]
    params = dict(manning=0.05, psi_m=0.17, dtheta=0.15)
    r = rog.run_scenario(tmp_project, "P100_3h", sc, z, tr, params, 600, lot)
    f = np.load(tmp_project.data_proc / "rog" / "P100_3h_frames.npz")
    assert f["h_cm"].shape == (6, 15, 15) and f["h_cm"].dtype == np.uint8          # horas 0..5
    assert list(f["t_h"]) == [0, 1, 2, 3, 4, 5]
    assert f["lluvia_acum_mm"][3] == pytest.approx(100, rel=1e-3)
    assert f["h_cm"][:, 7, 7].max() > 0                                              # el pozo junta agua
    meta = json.loads((tmp_project.data_proc / "rog" / "P100_3h_meta.json").read_text())
    assert meta["hmax_lote_cm"][0] == 0 and len(meta["hmax_lote_cm"]) == 6
    assert abs(meta["balance"]["error_pct"]) < 1
    # segunda llamada: sale de caché, mismo resultado
    r2 = rog.run_scenario(tmp_project, "P100_3h", sc, z, tr, params, 600, lot)
    assert np.array_equal(r["hmax"], r2["hmax"])


def test_run_scenario_presupuesto_agotado_repite_ultimo_cuadro(tmp_project):
    z = np.fromfunction(lambda r, c: 10 + 0.01 * c + 0.3 * ((r - 7) ** 2 + (c - 7) ** 2) ** 0.5 / 10, (15, 15)).astype("float32")
    z[7, 7] -= 0.5
    tr = from_origin(5_500_000, 6_200_000, 30, 30); lot = np.zeros_like(z, bool); lot[6:9, 6:9] = True
    sc = rog.build_scenarios(dict(grilla=dict(P_mm=[100], dur_h=[3], suelo=["normal"]), Ks_mm_h=10, Ks_sat_mm_h=2, drenaje_h=2))["P100_3h"]
    params = dict(manning=0.05, psi_m=0.17, dtheta=0.15)
    r = rog.run_scenario(tmp_project, "P100_3h", sc, z, tr, params, 0, lot)   # presupuesto 0: corta en el primer chequeo (t=1 h)
    f = np.load(tmp_project.data_proc / "rog" / "P100_3h_frames.npz")
    n_expected = int(round(sc["t_end_h"])) + 1
    assert f["h_cm"].shape[0] == n_expected
    assert np.array_equal(f["h_cm"][-1], f["h_cm"][-2])          # el último cuadro se repite (no hubo más simulación)
    meta = json.loads((tmp_project.data_proc / "rog" / "P100_3h_meta.json").read_text())
    assert meta["cortado"] is True
    assert meta["horas_simuladas"] < sc["t_end_h"]
    assert r["hmax"].shape == z.shape
