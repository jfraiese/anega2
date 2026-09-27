from anega2 import rog


def test_ensemble_ids():
    cfg = dict(ensamble=dict(P_mm=[50, 100], dur_h=[24], suelo=["normal"]))
    assert rog.ensemble_ids(cfg) == ["P050_24h", "P100_24h"]
    assert rog.ensemble_ids({}) == []


def test_ensemble_dems(tmp_project):
    for d in ["fabdem", "glo30", "ign30"]:
        q = tmp_project.data_proc / "terrain" / d; q.mkdir(parents=True)
        if d != "ign30":
            (q / "dem_breach.tif").write_bytes(b"x")
    assert rog.ensemble_dems(tmp_project, "fabdem") == ["glo30"]
