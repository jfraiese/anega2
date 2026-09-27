import gzip
import json

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from anega2 import webdata, websim
from anega2.project import Project

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


def test_vista_resumen_no_propaga_error(tmp_path, monkeypatch):
    """webdata._vista_resumen no debe abortar la fase web si websim.run() falla: se registra como aviso."""
    p = Project(name="x", cfg={}, dir=tmp_path)
    B = webdata.Builder(p)

    def _boom(_p):
        raise RuntimeError("boom")

    monkeypatch.setattr(websim, "run", _boom)
    webdata._vista_resumen(p, B)  # no debe propagar
    assert any("vista Resumen no generada" in w and "boom" in w for w in B.warnings)


def _proyecto_sintetico(tmp_path, monkeypatch) -> Project:
    """Proyecto sintético mínimo (grilla 4x4, 2 DEM, 1 escenario) para probar websim.run() de punta a punta."""
    monkeypatch.setattr(Project, "lot_centroid_wgs84", lambda self: (-59.5, -34.4))
    cfg = dict(buffers=dict(lluvia_m=1000, aoi_m=50, hidro_m=500, grilla_m=100),
               lluvia=dict(grilla=dict(P_mm=[100], dur_h=[24], suelo=["normal"])), crs=CRS)
    p = Project(name="synt", cfg=cfg, dir=tmp_path)

    for dem in ("demA", "demB"):
        d = p.data_proc / "terrain" / dem; d.mkdir(parents=True, exist_ok=True)
        with rasterio.open(d / "dem_breach.tif", "w", driver="GTiff", height=4, width=4, count=1,
                            dtype="float32", crs=CRS, transform=TR, nodata=-9999) as dst:
            dst.write(np.full((4, 4), 10.0, "float32"), 1)
    (p.out / "terrain_primary.json").write_text(json.dumps({"primary": "demA"}))

    lote = box(5_550_050, 6_189_930, 5_550_070, 6_189_950)
    gpd.GeoDataFrame({"name": ["lote", "aoi", "hidro"]}, geometry=[lote, lote.buffer(20), lote.buffer(80)],
                      crs=CRS).to_file(p.aoi_gpkg, layer="aoi", driver="GPKG")

    rogd = p.data_proc / "rog"; (rogd / "ens").mkdir(parents=True, exist_ok=True)
    h_cm = np.zeros((2, 4, 4), np.uint8); h_cm[1] = 12
    np.savez_compressed(rogd / "P100_24h_frames.npz", h_cm=h_cm, t_h=np.arange(2), lluvia_acum_mm=np.array([0.0, 100.0]))
    (rogd / "P100_24h_meta.json").write_text(json.dumps({"cortado": True, "hmax_lote_cm": [0, 12], "pct_lote_gt5cm": [0.0, 100.0], "pct_lote_gt20cm": [0.0, 0.0]}))
    np.savez_compressed(rogd / "ens" / "P100_24h__demB_frames.npz", h_cm=h_cm, t_h=np.arange(2), lluvia_acum_mm=np.array([0.0, 100.0]))
    (p.out / "rog_ensamble.json").write_text(json.dumps({"dems": ["demB"], "ids": ["P100_24h"], "primario": "demA"}))
    (p.out / "clima.json").write_text(json.dumps({"disponible": True}))
    return p


def test_run_cortado_y_ensamble(tmp_path, monkeypatch):
    """websim.run(): pasa 'cortado' de <id>_meta.json a index.json y arma la lista de DEM del ensamble."""
    p = _proyecto_sintetico(tmp_path, monkeypatch)
    websim.run(p)

    idx = json.loads((p.web / "sim" / "index.json").read_text())
    esc = idx["escenarios"]["P100_24h"]
    assert esc["cortado"] is True
    assert esc["ensamble"] == ["demA", "demB"]
    assert (p.web / "sim" / "P100_24h.bin.gz").exists() and (p.web / "sim" / "P100_24h_cert.bin.gz").exists()


def test_run_lote_desde_meta(tmp_path, monkeypatch):
    """websim.run(): copia las series nativas del lote (hmax/pct5/pct20) desde <id>_meta.json a index.json."""
    p = _proyecto_sintetico(tmp_path, monkeypatch)
    websim.run(p)

    idx = json.loads((p.web / "sim" / "index.json").read_text())
    esc = idx["escenarios"]["P100_24h"]
    assert esc["lote"] == {"hmax_cm": [0, 12], "pct5": [0.0, 100.0], "pct20": [0.0, 0.0]}


def test_run_sin_lote_en_meta_lo_omite(tmp_path, monkeypatch):
    """websim.run(): si el meta no tiene las series del lote (datos viejos), 'lote' se omite en index.json."""
    p = _proyecto_sintetico(tmp_path, monkeypatch)
    (p.data_proc / "rog" / "P100_24h_meta.json").write_text(json.dumps({"cortado": True}))
    websim.run(p)

    idx = json.loads((p.web / "sim" / "index.json").read_text())
    assert "lote" not in idx["escenarios"]["P100_24h"]


def _estricto(txt):
    def no(c): raise ValueError(f"constante no JSON: {c}")
    return json.loads(txt, parse_constant=no)


def test_index_json_sin_nan_desnudo(tmp_path, monkeypatch):
    p = _proyecto_sintetico(tmp_path, monkeypatch)
    (p.out / "clima.json").write_text(json.dumps({"disponible": True, "gumbel": {"chirps": {"72": {"mu": float("nan"), "beta": float("inf")}}}}))
    websim.run(p)
    idx = _estricto((p.web / "sim" / "index.json").read_text())
    assert idx["clima"]["gumbel"]["chirps"]["72"] == {"mu": None, "beta": None}


def test_webdata_veredicto_faltante_avisa(tmp_path):
    p = Project(name="x", cfg={}, dir=tmp_path); B = webdata.Builder(p)
    (p.web / "veredicto.json").write_text("{}")             # uno viejo: se borra
    assert webdata._copiar_veredicto(p.out, p.web, B) == {}
    assert not (p.web / "veredicto.json").exists()
    assert any("falta out/veredicto.json" in w and "--fase informe" in w for w in B.warnings)
    (p.out / "veredicto.json").write_text(json.dumps({"etiqueta": "Riesgo bajo"}))
    B2 = webdata.Builder(p)
    assert webdata._copiar_veredicto(p.out, p.web, B2) == {"etiqueta": "Riesgo bajo"} and not B2.warnings
    assert (p.web / "veredicto.json").exists()


def test_webdata_limpia_capas_viejas_de_simulacion(tmp_path):
    p = Project(name="x", cfg={}, dir=tmp_path); B = webdata.Builder(p)
    for n in ["img/rog_h_P060_2h.png", "img/rog_d_P060_2h.png", "img/dem.png", "geo/rog_v_P060_2h.geojson", "geo/lote.geojson",
              "figures/40_rog_P060_2h.png", "figures/10_terrain_dem.png"]:
        (p.web / n).write_text("x")
    (p.out / "10_terrain_dem.png").write_text("x")
    webdata._limpiar_viejos(p.web, p.out)
    quedan = sorted(str(q.relative_to(p.web)) for q in p.web.rglob("*") if q.is_file())
    assert quedan == ["figures/10_terrain_dem.png", "geo/lote.geojson", "img/dem.png"]
