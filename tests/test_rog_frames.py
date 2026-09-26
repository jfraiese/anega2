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


def test_run_scenario_lluvia_debil_larga_no_borra_infiltracion(tmp_project):
    """Lluvia liviana y larga: el incremento de lámina por paso de integración (<=60 s) queda por debajo
    de H_FILM (1e-5 m). Si Green-Ampt sólo infiltra hasta H_FILM, esa lluvia nunca llega a infiltrarse y
    el piso de steep_slopes de OverlandFlow (h_init*1e-3) la borra al final de cada paso: el balance no cierra."""
    z = np.fromfunction(lambda r, c: 10 + 0.01 * c + 0.3 * ((r - 7) ** 2 + (c - 7) ** 2) ** 0.5 / 10, (15, 15)).astype("float32")
    tr = from_origin(5_500_000, 6_200_000, 30, 30); lot = np.zeros_like(z, bool); lot[6:9, 6:9] = True
    sc = rog.build_scenarios(dict(grilla=dict(P_mm=[10], dur_h=[24], suelo=["normal"]), Ks_mm_h=10, Ks_sat_mm_h=2, drenaje_h=2))["P010_24h"]
    params = dict(manning=0.05, psi_m=0.17, dtheta=0.15)
    rog.run_scenario(tmp_project, "P010_24h", sc, z, tr, params, 600, lot)
    meta = json.loads((tmp_project.data_proc / "rog" / "P010_24h_meta.json").read_text())
    b = meta["balance"]
    assert abs(b["error_pct"]) < 1
    # De la lluvia que cae sobre nodos "core" (no de borde) debe infiltrarse ≥95 %: Ks (10 mm/h) >> intensidad
    # media (10 mm / 24 h). La lluvia que cae sobre el anillo de borde (13*13=169 de los 225 nodos son core;
    # el resto es el perímetro de 1 celda) nunca infiltra por diseño (sale por "salida_bordes_m3"), así que
    # comparamos contra la lluvia caída sólo sobre el core, no contra el total del dominio.
    core_frac = (15 - 2) * (15 - 2) / (15 * 15)
    assert b["infiltrado_m3"] >= 0.95 * b["lluvia_m3"] * core_frac


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


def _chico():
    z = np.fromfunction(lambda r, c: 10 + 0.01 * c + 0.3 * ((r - 7) ** 2 + (c - 7) ** 2) ** 0.5 / 10, (15, 15)).astype("float32")
    z[7, 7] -= 0.5
    tr = from_origin(5_500_000, 6_200_000, 30, 30); lot = np.zeros_like(z, bool); lot[6:9, 6:9] = True
    return z, tr, lot


def _sc(ks):
    return rog.build_scenarios(dict(grilla=dict(P_mm=[100], dur_h=[3], suelo=["normal"]), Ks_mm_h=ks, Ks_sat_mm_h=2, drenaje_h=1))["P100_3h"]


def test_cache_con_huella(tmp_project):
    z, tr, lot = _chico(); params = dict(manning=0.05, psi_m=0.17, dtheta=0.15, dem="fabdem")
    meta_p = tmp_project.data_proc / "rog" / "P100_3h_meta.json"
    r = rog.run_scenario(tmp_project, "P100_3h", _sc(10), z, tr, params, 600, lot)
    h1 = json.loads(meta_p.read_text())["huella"]; m1 = meta_p.stat().st_mtime_ns
    assert isinstance(h1, str) and len(h1) == 12 and not r.get("sin_huella")
    r2 = rog.run_scenario(tmp_project, "P100_3h", _sc(10), z, tr, params, 600, lot)       # mismos parámetros: caché
    assert meta_p.stat().st_mtime_ns == m1 and not r2.get("sin_huella")
    r3 = rog.run_scenario(tmp_project, "P100_3h", _sc(2), z, tr, params, 600, lot)        # Ks distinto: recalcula
    meta = json.loads(meta_p.read_text())
    assert meta["huella"] != h1 and meta["Ks_mm_h"] == pytest.approx(2) and r3["Ks_mm_h"] == pytest.approx(2)
    h3 = meta["huella"]
    rog.run_scenario(tmp_project, "P100_3h", _sc(2), z, tr, dict(params, dem="glo30"), 600, lot)   # otro DEM: recalcula
    assert json.loads(meta_p.read_text())["huella"] != h3


def test_cache_legado_sin_huella_se_reusa(tmp_project):
    z, tr, lot = _chico(); params = dict(manning=0.05, psi_m=0.17, dtheta=0.15, dem="fabdem")
    meta_p = tmp_project.data_proc / "rog" / "P100_3h_meta.json"
    rog.run_scenario(tmp_project, "P100_3h", _sc(10), z, tr, params, 600, lot)
    meta = json.loads(meta_p.read_text()); meta.pop("huella"); meta_p.write_text(json.dumps(meta))
    m1 = meta_p.stat().st_mtime_ns
    r = rog.run_scenario(tmp_project, "P100_3h", _sc(2), z, tr, params, 600, lot)         # aunque cambie Ks: legado, se reusa
    assert r["sin_huella"] is True and r["Ks_mm_h"] == pytest.approx(10) and meta_p.stat().st_mtime_ns == m1


def test_podar_salidas_de_escenarios_no_configurados(tmp_path):
    for n in ["40_rog_P060_2h.png", "40_rog_P060_2h_dom.png", "40_rog_P100_24h.png", "40_rog_P100_24h_dom.png", "40_rog_P100_24h_sat.png",
              "rog_P060_2h_agua5cm.geojson", "rog_P060_2h_agua5cm.kml", "rog_P100_24h_agua5cm.geojson", "rog_P060_2h_hmax_aoi.tif",
              "rog_P060_2h_dur5cm_aoi.tif", "rog_P025_3h_hmax_aoi.tif", "rog_stats.csv", "10_terrain_dem.png"]:
        (tmp_path / n).write_text("x")
    borr = rog.podar_salidas(tmp_path, ficha={"P100_24h"}, configurados={"P100_24h", "P025_3h"})
    quedan = sorted(q.name for q in tmp_path.iterdir())
    assert quedan == ["10_terrain_dem.png", "40_rog_P100_24h.png", "40_rog_P100_24h_dom.png", "rog_P025_3h_hmax_aoi.tif",
                      "rog_P100_24h_agua5cm.geojson", "rog_stats.csv"]
    assert len(borr) == 7
