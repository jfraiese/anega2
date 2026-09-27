from pathlib import Path

import numpy as np
import pytest
import yaml

from anega2 import paletas


def test_cortes_desde_rules_yml():
    rules = yaml.safe_load((Path(paletas.__file__).parent / "rules.yml").read_text())
    esperado = sorted(rules["desborde"]["hand_min_m"]["umbrales"].values())
    assert [hi for _, hi, _, _ in paletas.HAND_CLASES[:-1]] == esperado


def test_hand_para_figura_recorta_arriba_del_techo():
    a = np.array([0.1, 4.9, 5.0, 8.0, np.nan])
    out = paletas.hand_para_figura(a)
    assert out[:2].tolist() == [0.1, 4.9] and np.isnan(out[2:]).all()


def test_hand_clase():
    a = np.array([0.1, 0.5, 0.99, 1.5, 4.9, 5.0, 8.0, np.nan])
    c = paletas.hand_clase(a)
    assert c[:5].tolist() == [0, 1, 1, 2, 3] and np.isnan(c[5:]).all()


def test_colores_sin_azul():
    for _, _, col, _ in paletas.HAND_CLASES:
        r, g, b = (int(col[i:i + 2], 16) for i in (1, 3, 5))
        assert b < max(r, g)


def test_hand_incertidumbre():
    d = paletas.hand_incertidumbre(0.6, [0.6, 0.7, 2.9], 1.0)
    assert d["sigma"] == pytest.approx(round(float(np.std([0.6, 0.7, 2.9], ddof=1)), 2))
    d = paletas.hand_incertidumbre(0.6, [0.6], 1.0)
    assert d["sigma"] == 1.0 and d["p_lt1"] == pytest.approx(65.5, abs=0.2)
