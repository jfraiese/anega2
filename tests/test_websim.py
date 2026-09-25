import gzip

import numpy as np
from rasterio.transform import from_origin
from shapely.geometry import box

from anega2 import websim

CRS = "EPSG:5347"; TR = from_origin(5_550_000, 6_190_000, 30, 30)


def test_grilla_3857_resolucion():
    g = websim.grilla_3857(TR, CRS, (100, 100), lat=-34.4)
    assert abs(g["res_m"] - 30 / np.cos(np.radians(34.4))) < 0.5
    (s, w), (n, e) = g["bounds_wgs84"]
    assert s < n and w < e and -35 < s < -33


def test_a_3857_conserva_valores():
    fr = np.zeros((2, 100, 100), np.uint8); fr[1, 40:60, 40:60] = 50
    g = websim.grilla_3857(TR, CRS, (100, 100), lat=-34.4)
    out = websim.a_3857(fr, TR, CRS, g)
    assert out.shape == (2, g["rows"], g["cols"]) and out.dtype == np.uint8
    assert out[0].max() == 0 and set(np.unique(out[1])) == {0, 50}


def test_certeza_un_solo_dem():
    f = np.zeros((1, 5, 5), np.uint8); f[0, 1:4, 1:4] = 10
    c = websim.certeza([f], 5)
    assert c[0, 2, 2] == 100 and c[0, 1, 1] == 44 and c[0, 0, 0] == 11   # 9/9, 4/9, 1/9
    assert websim.certeza([f], 20).max() == 0


def test_certeza_promedia_dems():
    a = np.zeros((1, 3, 3), np.uint8); a[:] = 10; b = np.zeros_like(a)
    assert websim.certeza([a, b], 5)[0, 1, 1] == 50


def test_certeza_realinea_shapes():
    a = np.full((1, 4, 4), 10, np.uint8); b = np.full((1, 5, 3), 10, np.uint8)
    assert websim.certeza([a, b], 5).shape == (1, 4, 4)


def test_lote_idx():
    g = websim.grilla_3857(TR, CRS, (100, 100), lat=-34.4)
    lote = box(5_551_400, 6_188_400, 5_551_500, 6_188_500)
    idx = websim.lote_idx(lote, CRS, g)
    assert 4 <= len(idx) <= 25 and all(0 <= i < g["rows"] * g["cols"] for i in idx)


def test_escribir_bin_gz(tmp_path):
    a = np.arange(24, dtype=np.uint8).reshape(2, 3, 4)
    websim.escribir_gz(tmp_path / "x.bin.gz", a)
    assert np.frombuffer(gzip.decompress((tmp_path / "x.bin.gz").read_bytes()), np.uint8).reshape(2, 3, 4).tolist() == a.tolist()
