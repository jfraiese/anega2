import pytest

from anega2 import rog

GRILLA = dict(grilla=dict(P_mm=[25, 100], dur_h=[3, 24], suelo=["normal", "saturado"]), Ks_mm_h=10, Ks_sat_mm_h=2, drenaje_h=24)


def test_scen_id():
    assert rog.scen_id(25, 3, False) == "P025_3h"
    assert rog.scen_id(100, 24, True) == "P100_24h_sat"


def test_scenario_specs_grilla():
    ids = [s["id"] for s in rog.scenario_specs(GRILLA)]
    assert ids == ["P025_3h", "P025_3h_sat", "P025_24h", "P025_24h_sat", "P100_3h", "P100_3h_sat", "P100_24h", "P100_24h_sat"]


def test_scenario_specs_formato_viejo(capsys):
    viejo = dict(escenarios=[{"id": "P100_24h", "P_mm": 100, "dur_h": 24}, {"id": "P060_2h", "P_mm": 60, "dur_h": 2}], saturado=["P100_24h"],
                 grilla=GRILLA["grilla"])
    specs = rog.scenario_specs(viejo)
    assert [s["id"] for s in specs] == ["P100_24h", "P060_2h", "P100_24h_sat"]
    assert specs[2]["suelo"] == "saturado"
    assert "formato viejo" in capsys.readouterr().out


def test_build_scenarios_t_end_y_ks():
    sc = rog.build_scenarios(GRILLA)
    assert sc["P100_24h"]["t_end_h"] == 48 and sc["P100_24h"]["Ks_mm_h"] == 10
    assert sc["P100_24h_sat"]["Ks_mm_h"] == 2
    assert sc["P025_3h"]["dt_h"] == pytest.approx(1 / 6)


@pytest.mark.parametrize("P,dur", [(25, 3), (100, 24), (250, 72)])
def test_hietograma_suma_P(P, dur):
    sc = rog.build_scenarios(dict(GRILLA, grilla=dict(P_mm=[P], dur_h=[dur], suelo=["normal"])))[rog.scen_id(P, dur, False)]
    assert rog.alternating_block(sc["P_mm"], sc["dur_h"], sc["dt_h"], sc["ratios"]).sum() == pytest.approx(P)


def test_ficha_ids_default():
    assert rog.ficha_ids(GRILLA) == ["P025_24h", "P025_24h_sat", "P100_24h", "P100_24h_sat"]
