from datetime import date

import numpy as np
import pytest

from anega2 import clima, sar


def _bimodal_db(water_db: float, land_db: float, frac_water: float, n: int = 100_000, noise: float = 1.0, seed: int = 0) -> np.ndarray:
    """Serie sintética dB con dos poblaciones gaussianas (agua/tierra) en las proporciones dadas."""
    rng = np.random.default_rng(seed)
    n_water = int(n * frac_water)
    water = rng.normal(water_db, noise, n_water)
    land = rng.normal(land_db, noise, n - n_water)
    db = np.concatenate([water, land])
    rng.shuffle(db)
    return db


def test_otsu_db_bimodal_agua_plausible_mantiene_otsu():
    """~5 % de agua a -22 dB, tierra a -8 dB: bimodal plausible, se mantiene el umbral de Otsu."""
    db = _bimodal_db(water_db=-22, land_db=-8, frac_water=0.05)
    mask = np.ones_like(db, dtype=bool)
    t, note = sar.otsu_db(db, mask, fixed=-18.0)
    assert t < -13.0
    assert t == pytest.approx(-18.8, abs=0.5)
    assert "Otsu" in note
    assert "fijo" not in note


def test_otsu_db_bimodal_fraccion_no_plausible_cae_a_fijo():
    """~55 % 'agua' a -20 dB, tierra a -8 dB: Otsu < -13 dB pero marca demasiado buffer como agua -> umbral fijo."""
    db = _bimodal_db(water_db=-20, land_db=-8, frac_water=0.55)
    mask = np.ones_like(db, dtype=bool)
    t, note = sar.otsu_db(db, mask, fixed=-18.0)
    assert t == -18.0
    assert "marca" in note
    assert "55 %" in note
    assert "umbral fijo -18 dB" in note


def test_otsu_db_unimodal_usa_fijo():
    """Sólo tierra (unimodal): comportamiento existente, Otsu > -13 dB -> umbral fijo con la nota antigua."""
    db = _bimodal_db(water_db=-8, land_db=-8, frac_water=0.0)
    mask = np.ones_like(db, dtype=bool)
    t, note = sar.otsu_db(db, mask, fixed=-18.0)
    assert t == -18.0
    assert "no plausible para agua" in note
    assert "marca" not in note


def test_plan_pre_y_post_dentro_de_ventana():
    fechas = [date(2024, 3, 1), date(2024, 3, 3), date(2024, 3, 13), date(2024, 3, 27)]
    assert sar.plan_escenas(fechas, date(2024, 3, 12), 12, 3) == (date(2024, 3, 3), date(2024, 3, 13))


def test_plan_sin_post_a_tiempo():
    fechas = [date(2024, 3, 3), date(2024, 3, 27)]
    assert sar.plan_escenas(fechas, date(2024, 3, 12), 12, 3) == (date(2024, 3, 3), None)


def test_plan_misma_fecha_es_post():
    assert sar.plan_escenas([date(2024, 3, 12)], date(2024, 3, 12), 12, 3) == (None, date(2024, 3, 12))


def test_resolve_events_auto_sin_clima(tmp_project, capsys):
    tmp_project.cfg["sar"]["eventos"] = "auto"
    assert clima.resolve_events(tmp_project) == []
    assert "correr la fase clima" in capsys.readouterr().out


def test_borrar_sar_viejo(tmp_path, capsys):
    for n in ["sar_stats.csv", "sar_stats.md", "jrc_stats.csv"]:
        (tmp_path / n).write_text("x")
    sar.borrar_stats_viejas(tmp_path)
    assert sorted(q.name for q in tmp_path.iterdir()) == ["jrc_stats.csv"]
    assert "[aviso]" in capsys.readouterr().out
    sar.borrar_stats_viejas(tmp_path)                        # sin nada que borrar: no falla ni avisa
    assert "[aviso]" not in capsys.readouterr().out
