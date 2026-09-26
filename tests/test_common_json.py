import json
import math

import numpy as np

from anega2.common import json_limpio


def test_json_limpio_nan_inf_a_none():
    o = {"a": float("nan"), "b": [1.0, float("inf"), {"c": -math.inf}], "d": np.float32("nan"), "e": np.float64(2.5), "f": "NaN", "g": (1, float("nan"))}
    r = json_limpio(o)
    assert r == {"a": None, "b": [1.0, None, {"c": None}], "d": None, "e": 2.5, "f": "NaN", "g": [1, None]}
    json.dumps(r, allow_nan=False)                         # JSON estricto: sin NaN desnudo
