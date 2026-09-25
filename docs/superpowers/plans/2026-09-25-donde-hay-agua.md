# «¿Dónde hay agua?» Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar lluvia histórica real (fase `clima`), simulación con cuadros horarios y ensamble de DEM, certeza por píxel, y una vista «Resumen» del visor en lenguaje llano, más paleta HAND sin azul y `veredicto.json` como contrato con el visor.

**Architecture:** Pipeline por fases de `anega2` (cada fase lee/escribe archivos en `projects/<n>/{data,out,web}`). Se agrega `anega2/clima.py` (fase nueva), se extiende `anega2/rog.py` (grilla, cuadros, paralelo, ensamble), se crea `anega2/websim.py` (cuadros → EPSG:3857 + certeza → `web/sim/`), y el visor estático se separa en `lib.js` (puro, testeado con node) + `sim.js` + `resumen.js` + `tecnico.js` + `app.js`.

**Tech Stack:** Python 3.12 (numpy, pandas, scipy, rasterio, landlab, requests, pytest), conda env `giles-flood`; JS plano sin build (Leaflet 1.9.4, Chart.js 4.4.1 desde cdnjs), `node --test` (node ≥ 18).

**Spec:** `docs/superpowers/specs/2026-09-25-donde-hay-agua-design.md`

## Global Constraints

- Entorno: conda env **`giles-flood`** (el `environment.yml` dice `anega2`; en esta máquina el env se llama `giles-flood`). Todos los comandos Python: `conda run --no-capture-output -n giles-flood <cmd>` (abreviado abajo como `$PY`), p. ej. `$PY python -m pytest tests -q`.
- Idioma: código, mensajes, docs y UI en **castellano** (rioplatense, como el resto del repo). Números en la UI con coma decimal (`toLocaleString('es-AR')`).
- Estilo: igual al código existente (líneas largas, funciones compactas, `from __future__ import annotations`, docstring de módulo que lista salidas).
- Visor **estático, sólo local**, sin build ni dependencias nuevas de JS. Librerías sólo desde cdnjs.
- Azul reservado **sólo para agua** en el visor.
- Grilla: `P_mm: [25..250 cada 25]`, `dur_h: [3, 24, 72]`, `suelo: [normal, saturado]`, `drenaje_h: 24`, ids `P<mmm>_<dur>h[_sat]` (P con 3 dígitos: `P025_3h`, `P100_24h_sat`).
- Cuadros: cm uint8 0-255 (satura en 2,55 m), una por hora entera desde t=0 hasta `dur_h + drenaje_h` inclusive.
- Certeza: umbrales 5 y 20 cm, ventana 3×3, promedio sobre DEM; niveles probable ≥ 70, posible 30-70, poco probable 5-30, < 5 no se dibuja; opacidades 0,95 / 0,55 / 0,2.
- Paleta HAND: `< 0,5 m #b71c1c`, `0,5-1 #f4511e`, `1-2 #ffb300`, `2-5 #fff3c4`, `> 5` transparente.
- Lluvia histórica: ERA5 horaria vía Open-Meteo `models=era5` desde 1940-01-01 (ERA5-Land descartado: devuelve nulos); CHIRPS v2.0 diaria p05 COG desde 1981-01-01; sin CHIRPS al sur de 50°S.
- Sentinel-1: escena «pre» = última en los 12 días previos; «post» = primera en 0-3 días posteriores; si no hay post → fila «sin pasada a tiempo» con porcentajes vacíos.
- No tocar `anega2/ficha.py` hasta la Task 11 (tiene cambios sin commitear del autor; ver Task 0).

## Review Focus

- **Lote fuera de la cobertura de CHIRPS (sur de 50°S) o sin red**: la fase `clima` debe terminar con ERA5 solo (o `disponible: false`) sin excepción, y `sar` con `eventos: auto` debe saltearse con aviso en vez de romper `anega2 run`. Test en Task 3 (`test_run_sin_fuentes`) y Task 4 (`test_resolve_events_auto_sin_clima`).
- **Proyecto viejo con `lluvia.escenarios` / `saturado`** (formato previo, p. ej. un lote privado del autor): debe seguir corriendo igual y avisar. Test en Task 5 (`test_scenario_specs_formato_viejo`).
- **Deslizador en los extremos y valores exactos de la grilla** (25 mm, 250 mm, 100 mm): la interpolación no debe salir de rango ni dividir por cero (`w` = 0 con un solo vecino). Test en Task 12 (`pickNeighbors extremos`).
- **Lote que nunca junta agua** (todas las láminas < 5 cm) y **lluvia mayor que cualquier registro**: la frase debe decir «El lote no junta agua» y «Más de lo que llovió…», no «0 % del lote» ni «cada Infinity años». Tests en Task 12 (`frase sin agua`, `frase fuera de registro`).
- **Escenario sin ensamble / DEM alternativo faltante** (fuera de Argentina no hay IGN): la certeza debe calcularse con los DEM disponibles y declararlo; nunca fallar por shape distinto. Test en Task 8 (`test_certeza_un_solo_dem` y `test_certeza_realinea_shapes`).

---

### Task 0: Empaquetado, pytest y commit previo del autor

**Files:**
- Create: `pyproject.toml`
- Create: `tests/__init__.py` (vacío), `tests/conftest.py`
- Modify: `environment.yml` (agregar `pytest`)

**Interfaces:**
- Produces: `anega2` instalable en modo editable (`pip install -e .`) con el script `anega2 = anega2.cli:main`; fixture `tmp_project` en `tests/conftest.py`.

Contexto: `environment.yml` hace `pip install -e .` pero **no existe** `pyproject.toml` ni `setup.py`; por eso `anega2` no es importable fuera de la raíz del repo y el comando `anega2` del README no existe.

- [ ] **Step 1: Pedir al autor que commitee sus cambios pendientes**

`git status --short` muestra `M anega2/ficha.py`, `M README.md`, `M README.en.md`, `M projects/ejemplo-bajo-giles/out/ficha_ejemplo-bajo-giles.pdf` (trabajo del autor, no de este plan). Preguntar al autor si los commitea él antes de empezar. No seguir con la Task 11 hasta que `anega2/ficha.py` esté limpio en `git status`.

- [ ] **Step 2: Crear `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "anega2"
dynamic = ["version"]
description = "Análisis de riesgo de anegamiento por lluvia para un polígono KML (Argentina)"
requires-python = ">=3.11"
license = {text = "MIT"}

[project.scripts]
anega2 = "anega2.cli:main"

[tool.setuptools]
packages = ["anega2"]

[tool.setuptools.package-data]
anega2 = ["*.yml"]

[tool.setuptools.dynamic]
version = {attr = "anega2.__version__"}

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Agregar pytest a `environment.yml`**

En la lista `dependencies`, después de `- scikit-image`, agregar `  - pytest`.

- [ ] **Step 4: Instalar**

Run: `conda install -y -n giles-flood -c conda-forge pytest && $PY pip install -e .`
Expected: `Successfully installed anega2-0.1.0`

- [ ] **Step 5: Crear `tests/conftest.py`**

```python
"""Fixtures comunes: proyecto temporal mínimo (sin red ni datos pesados)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import anega2.project as project_mod

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def tmp_project(tmp_path, monkeypatch):
    """Proyecto 'ejemplo' en un PROJECTS_DIR temporal, con el lote.kml del ejemplo público."""
    monkeypatch.setattr(project_mod, "PROJECTS_DIR", tmp_path)
    d = tmp_path / "ejemplo"; d.mkdir()
    shutil.copy(REPO / "projects/ejemplo-bajo-giles/lote.kml", d / "lote.kml")
    (d / "project.yml").write_text("nombre: ejemplo\ntitulo: Ejemplo\nkml: lote.kml\n")
    return project_mod.Project.load("ejemplo", yes=True)
```

Crear `tests/__init__.py` vacío.

- [ ] **Step 6: Verificar**

Run: `$PY python -m pytest -q` (desde la raíz) y `$PY anega2 --help`
Expected: `no tests ran` (código 5) y la ayuda de la CLI con `init, run, serve, list, doctor`.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml environment.yml tests/__init__.py tests/conftest.py
git commit -m "Empaquetado (pyproject) y pytest: anega2 instalable en modo editable"
```

---

### Task 1: `clima` — cálculos puros (máximos, desagrupado, Gumbel, retorno)

**Files:**
- Create: `anega2/clima.py` (sólo funciones puras en esta task)
- Test: `tests/test_clima_calc.py`

**Interfaces:**
- Produces (en `anega2/clima.py`):
  - `rolling_max_anual(s: pd.Series, horas: int, min_dias: int = 300) -> pd.DataFrame` — `s` índice DatetimeIndex regular (horario o diario, hora local), valores mm; devuelve columnas `anio, mm, fecha` (fecha = fin de la ventana del máximo), descarta años con < `min_dias` días con dato.
  - `gumbel_fit(x: np.ndarray) -> dict` — `{"mu": float, "beta": float, "n": int}` por momentos.
  - `gumbel_mm(fit: dict, T: float) -> float` — lluvia de período de retorno T.
  - `gumbel_T(fit: dict, mm: float) -> float` — período de retorno de `mm` (∞ si la prob. de excedencia es 0).
  - `gumbel_ic(x: np.ndarray, Ts: list[float], n_boot: int = 1000, seed: int = 0, nivel: float = 0.9) -> dict[float, tuple[float, float]]`
  - `desagrupar(s72: pd.Series, n: int, separacion_d: int, desde: str | None = None) -> list[pd.Timestamp]` — picos de la serie de sumas móviles de 72 h, separados ≥ `separacion_d` días, ordenados de mayor a menor.
  - Constante `TS = [2, 5, 10, 25, 50, 100]`.

- [ ] **Step 1: Escribir los tests**

```python
"""Cálculos puros de la fase clima (sin red)."""
import numpy as np
import pandas as pd
import pytest

from anega2 import clima


def _serie_horaria(anios=(2000, 2001, 2002), picos=None):
    idx = pd.date_range(f"{anios[0]}-01-01", f"{anios[-1]}-12-31 23:00", freq="h")
    s = pd.Series(0.0, index=idx)
    for t, mm in (picos or {}).items():
        s[pd.Timestamp(t)] = mm
    return s


def test_rolling_max_anual_24h_suma_ventana_y_fecha_fin():
    s = _serie_horaria(picos={"2000-03-10 10:00": 30, "2000-03-10 20:00": 20, "2001-07-01 00:00": 5, "2002-02-02 02:00": 80})
    df = clima.rolling_max_anual(s, 24)
    assert list(df.anio) == [2000, 2001, 2002]
    assert df.loc[df.anio == 2000, "mm"].item() == pytest.approx(50)
    assert df.loc[df.anio == 2002, "mm"].item() == pytest.approx(80)
    # la fecha es el fin de la primera ventana que alcanza el máximo
    assert df.loc[df.anio == 2000, "fecha"].item() == pd.Timestamp("2000-03-10 20:00")


def test_rolling_max_anual_descarta_anios_incompletos():
    s = _serie_horaria(picos={"2001-05-05 05:00": 10})
    s["2001-01-01":"2001-12-01"] = np.nan          # 2001 queda con 30 días
    df = clima.rolling_max_anual(s, 24)
    assert 2001 not in set(df.anio)


def test_rolling_max_anual_diaria_72h():
    idx = pd.date_range("2000-01-01", "2000-12-31", freq="D")
    s = pd.Series(0.0, index=idx); s["2000-04-01"] = 10; s["2000-04-02"] = 20; s["2000-04-03"] = 30
    df = clima.rolling_max_anual(s, 72)
    assert df.mm.item() == pytest.approx(60)


def test_gumbel_ida_y_vuelta():
    rng = np.random.default_rng(1)
    x = rng.gumbel(80, 25, 60)
    fit = clima.gumbel_fit(x)
    assert fit["n"] == 60
    for T in clima.TS:
        assert clima.gumbel_T(fit, clima.gumbel_mm(fit, T)) == pytest.approx(T, rel=1e-6)
    assert clima.gumbel_mm(fit, 100) > clima.gumbel_mm(fit, 10) > clima.gumbel_mm(fit, 2)


def test_gumbel_T_fuera_de_rango():
    fit = {"mu": 80.0, "beta": 20.0, "n": 50}
    assert clima.gumbel_T(fit, 10_000) == float("inf")
    assert clima.gumbel_T(fit, 0) == pytest.approx(1.0, abs=1e-6)


def test_gumbel_ic_reproducible_y_contiene_estimacion():
    rng = np.random.default_rng(2); x = rng.gumbel(80, 25, 50)
    a = clima.gumbel_ic(x, [10, 100], n_boot=200, seed=0)
    b = clima.gumbel_ic(x, [10, 100], n_boot=200, seed=0)
    assert a == b
    fit = clima.gumbel_fit(x)
    lo, hi = a[10]
    assert lo < clima.gumbel_mm(fit, 10) < hi


def test_desagrupar_separa_y_ordena():
    idx = pd.date_range("2010-01-01", "2010-12-31", freq="h")
    s72 = pd.Series(0.0, index=idx)
    s72["2010-03-01"] = 100; s72["2010-03-03"] = 90   # mismo evento (2 días)
    s72["2010-06-01"] = 80; s72["2010-09-01"] = 120
    picos = clima.desagrupar(s72, n=5, separacion_d=7)
    assert picos == [pd.Timestamp("2010-09-01"), pd.Timestamp("2010-03-01"), pd.Timestamp("2010-06-01")]


def test_desagrupar_desde():
    idx = pd.date_range("2010-01-01", "2016-12-31", freq="D")
    s72 = pd.Series(0.0, index=idx); s72["2012-01-01"] = 200; s72["2015-01-01"] = 50
    assert clima.desagrupar(s72, n=3, separacion_d=7, desde="2014-10-03") == [pd.Timestamp("2015-01-01")]
```

- [ ] **Step 2: Correr y ver que fallen**

Run: `$PY python -m pytest tests/test_clima_calc.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'anega2.clima'` (o `AttributeError`).

- [ ] **Step 3: Implementar**

`anega2/clima.py` (la parte de fuentes y `run` se agrega en Tasks 2-3; dejar el docstring completo desde ahora):

```python
"""Fase clima · lluvia histórica en el lote: máximos anuales, período de retorno y tormentas mayores.

Fuentes (punto = centroide del lote; sin cuentas):
  ERA5 horaria vía Open-Meteo (archive-api, models=era5, desde 1940; 0,25°). ERA5-Land no se usa: Open-Meteo
  devuelve precipitación nula para ese modelo.
  CHIRPS v2.0 diaria p05 (COG en data.chc.ucsb.edu, desde 1981; 0,05°; sólo entre 50°S y 50°N), un píxel por día.

Salidas: data/raw/clima/era5_<lat>_<lon>.csv (caché horaria), cache/chirps/<lat>_<lon>.csv (caché compartida);
         out/clima_serie_diaria.csv, clima_maximos_anuales.csv, clima_retorno.csv, clima_eventos.csv, clima_stats.md, clima.json
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

TS = [2, 5, 10, 25, 50, 100]
EULER = 0.5772156649


# ------------------------------------------------------------------ cálculos puros
def _paso_h(s: pd.Series) -> float:
    return (s.index[1] - s.index[0]) / pd.Timedelta(hours=1)


def rolling_max_anual(s: pd.Series, horas: int, min_dias: int = 300) -> pd.DataFrame:
    """Máximo anual de la suma móvil de `horas` (serie horaria o diaria, índice regular). fecha = fin de la ventana."""
    n = max(1, int(round(horas / _paso_h(s))))
    r = s.rolling(n, min_periods=n).sum()
    dias_ok = s.notna().groupby(s.index.year).sum() * _paso_h(s) / 24
    rows = []
    for anio, g in r.groupby(r.index.year):
        if dias_ok.get(anio, 0) < min_dias or g.notna().sum() == 0:
            continue
        rows.append(dict(anio=int(anio), mm=float(g.max()), fecha=g.idxmax()))
    return pd.DataFrame(rows, columns=["anio", "mm", "fecha"])


def gumbel_fit(x) -> dict:
    x = np.asarray(x, dtype=float); x = x[np.isfinite(x)]
    beta = float(np.std(x, ddof=1) * math.sqrt(6) / math.pi)
    return dict(mu=float(np.mean(x) - EULER * beta), beta=beta, n=int(len(x)))


def gumbel_mm(fit: dict, T: float) -> float:
    return float(fit["mu"] - fit["beta"] * math.log(-math.log(1 - 1 / T)))


def gumbel_T(fit: dict, mm: float) -> float:
    p_exc = 1 - math.exp(-math.exp(-(mm - fit["mu"]) / fit["beta"]))
    return float("inf") if p_exc <= 0 else float(1 / p_exc)


def gumbel_ic(x, Ts, n_boot: int = 1000, seed: int = 0, nivel: float = 0.9) -> dict:
    x = np.asarray(x, dtype=float); x = x[np.isfinite(x)]
    rng = np.random.default_rng(seed)
    sims = np.array([[gumbel_mm(gumbel_fit(rng.choice(x, len(x), replace=True)), T) for T in Ts] for _ in range(n_boot)])
    a = (1 - nivel) / 2
    return {T: (float(np.quantile(sims[:, i], a)), float(np.quantile(sims[:, i], 1 - a))) for i, T in enumerate(Ts)}


def desagrupar(s72: pd.Series, n: int, separacion_d: int, desde: str | None = None) -> list:
    """Picos de la serie de sumas de 72 h separados al menos `separacion_d` días, de mayor a menor."""
    s = s72.dropna()
    if desde:
        s = s[s.index >= pd.Timestamp(desde)]
    s = s[s > 0].sort_values(ascending=False, kind="stable")     # empates: gana el primero en el tiempo
    sep = pd.Timedelta(days=separacion_d); picos = []
    for t in s.index:
        if all(abs(t - q) >= sep for q in picos):
            picos.append(t)
            if len(picos) == n:
                break
    return picos
```

- [ ] **Step 4: Correr y ver que pasen**

Run: `$PY python -m pytest tests/test_clima_calc.py -q`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add anega2/clima.py tests/test_clima_calc.py
git commit -m "clima: máximos anuales, desagrupado de tormentas y Gumbel con intervalo bootstrap"
```

---

### Task 2: `clima` — fuentes ERA5 (Open-Meteo) y CHIRPS con caché incremental

**Files:**
- Modify: `anega2/clima.py` (agregar sección de fuentes)
- Test: `tests/test_clima_fuentes.py`, fixture `tests/fixtures/openmeteo_era5.json`

**Interfaces:**
- Consumes: nada de tasks previas.
- Produces:
  - `OPENMETEO = "https://archive-api.open-meteo.com/v1/archive"`, `CHIRPS_URL = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/cogs/p05/{y}/chirps-v2.0.{y}.{m:02d}.{d:02d}.cog"`, `TZ = "America/Argentina/Buenos_Aires"`.
  - `parse_openmeteo(j: dict) -> pd.Series` — serie horaria (índice naive en hora local), mm, NaN donde viene `null`.
  - `era5_horaria(lat, lon, cache_csv: Path, hasta: date, get=requests.get) -> pd.Series` — lee la caché, pide sólo lo faltante por bloques de 10 años, reescribe la caché; ante error de red devuelve lo cacheado (puede ser vacío) y avisa.
  - `chirps_pixel(lat, lon) -> tuple[float, float]` — centro del píxel CHIRPS (0,05°) que contiene el punto.
  - `chirps_diaria(lat, lon, cache_csv: Path, hasta: date, hilos: int, leer=_leer_chirps_dia) -> pd.Series` — serie diaria; días que fallan (404/timeout) quedan NaN y **no** se cachean; devuelve serie vacía si `lat < -50 or lat > 50`.
  - `_leer_chirps_dia(fecha: date, lon: float, lat: float) -> float | None` (red, vía `/vsicurl`).

- [ ] **Step 1: Crear el fixture**

`tests/fixtures/openmeteo_era5.json` (respuesta recortada real de Open-Meteo para -34.40, -59.42):

```json
{"latitude": -34.4, "longitude": -59.4, "timezone": "America/Argentina/Buenos_Aires", "utc_offset_seconds": -10800,
 "hourly_units": {"time": "iso8601", "precipitation": "mm"},
 "hourly": {"time": ["2015-08-09T00:00", "2015-08-09T01:00", "2015-08-09T02:00", "2015-08-09T03:00"],
            "precipitation": [1.5, 12.0, null, 0.0]}}
```

- [ ] **Step 2: Escribir los tests**

```python
"""Fuentes de lluvia de la fase clima, sin red (respuestas simuladas)."""
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from anega2 import clima

FIX = Path(__file__).parent / "fixtures"


class _Resp:
    def __init__(self, j, status=200): self._j = j; self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f"HTTP {self.status_code}")
    def json(self): return self._j


def test_parse_openmeteo_hora_local_y_nulos():
    s = clima.parse_openmeteo(json.loads((FIX / "openmeteo_era5.json").read_text()))
    assert s.index[0] == pd.Timestamp("2015-08-09 00:00")
    assert s.iloc[1] == 12.0 and np.isnan(s.iloc[2])


def test_era5_pide_solo_lo_faltante(tmp_path):
    cache = tmp_path / "era5.csv"
    pd.Series([1.0, 2.0], index=pd.to_datetime(["2020-01-01 00:00", "2020-01-01 01:00"]), name="mm").rename_axis("t").to_csv(cache)
    pedidos = []
    def get(url, params, timeout):
        pedidos.append((params["start_date"], params["end_date"]))
        t = pd.date_range(params["start_date"], f"{params['end_date']} 23:00", freq="h")
        return _Resp({"hourly": {"time": [x.strftime("%Y-%m-%dT%H:%M") for x in t], "precipitation": [0.0] * len(t)}})
    s = clima.era5_horaria(-34.4, -59.42, cache, hasta=date(2020, 1, 3), get=get)
    assert pedidos == [("2020-01-01", "2020-01-03")]          # re-pide desde el último día cacheado
    assert s.index.max() == pd.Timestamp("2020-01-03 23:00")
    assert pd.read_csv(cache, index_col=0, parse_dates=True).shape[0] == len(s)


def test_era5_sin_red_devuelve_cache(tmp_path, capsys):
    cache = tmp_path / "era5.csv"
    def get(url, params, timeout): raise ConnectionError("sin red")
    s = clima.era5_horaria(-34.4, -59.42, cache, hasta=date(1941, 1, 1), get=get)
    assert len(s) == 0
    assert "sin red" in capsys.readouterr().out


def test_chirps_pixel_centro():
    assert clima.chirps_pixel(-34.4038, -59.4205) == pytest.approx((-34.425, -59.425))


def test_chirps_diaria_cachea_y_no_guarda_fallas(tmp_path):
    cache = tmp_path / "c.csv"
    llamadas = []
    def leer(f, lon, lat):
        llamadas.append(f)
        return None if f == date(2000, 1, 2) else 3.0
    s = clima.chirps_diaria(-34.4, -59.4, cache, hasta=date(2000, 1, 3), hilos=2, leer=leer, desde=date(2000, 1, 1))
    assert s.loc["2000-01-01"] == 3.0 and np.isnan(s.loc["2000-01-02"])
    llamadas.clear()
    clima.chirps_diaria(-34.4, -59.4, cache, hasta=date(2000, 1, 3), hilos=2, leer=leer, desde=date(2000, 1, 1))
    assert llamadas == [date(2000, 1, 2)]                     # sólo reintenta el día que falló


def test_chirps_fuera_de_cobertura(tmp_path):
    s = clima.chirps_diaria(-54.8, -68.3, tmp_path / "c.csv", hasta=date(2000, 1, 3), hilos=1, leer=lambda *a: 1.0)
    assert len(s) == 0
```

- [ ] **Step 3: Correr y ver que fallen**

Run: `$PY python -m pytest tests/test_clima_fuentes.py -q`
Expected: FAIL — `AttributeError: module 'anega2.clima' has no attribute 'parse_openmeteo'`

- [ ] **Step 4: Implementar** (agregar a `anega2/clima.py` debajo de los cálculos; imports nuevos arriba: `from concurrent.futures import ThreadPoolExecutor`, `from datetime import date, timedelta`, `from pathlib import Path`, `import requests`)

```python
# ------------------------------------------------------------------ fuentes
OPENMETEO = "https://archive-api.open-meteo.com/v1/archive"
CHIRPS_URL = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/cogs/p05/{y}/chirps-v2.0.{y}.{m:02d}.{d:02d}.cog"
TZ = "America/Argentina/Buenos_Aires"
ERA5_DESDE = date(1940, 1, 1)
CHIRPS_DESDE = date(1981, 1, 1)


def parse_openmeteo(j: dict) -> pd.Series:
    h = j["hourly"]
    return pd.Series([np.nan if v is None else float(v) for v in h["precipitation"]],
                     index=pd.to_datetime(h["time"]), name="mm", dtype=float).rename_axis("t")


def _read_cache(path: Path) -> pd.Series:
    if not path.exists():
        return pd.Series(dtype=float, name="mm")
    return pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0].rename("mm")


def era5_horaria(lat, lon, cache_csv: Path, hasta: date, get=requests.get) -> pd.Series:
    s = _read_cache(cache_csv)
    ini = s.index.max().date() if len(s) else ERA5_DESDE
    partes = [s[s.index < pd.Timestamp(ini)]] if len(s) else []
    d0 = ini
    try:
        while d0 <= hasta:
            d1 = min(hasta, date(d0.year + 10, 1, 1) - timedelta(days=1))
            r = get(OPENMETEO, params=dict(latitude=lat, longitude=lon, start_date=d0.isoformat(), end_date=d1.isoformat(),
                                           hourly="precipitation", models="era5", timezone=TZ), timeout=120)
            r.raise_for_status(); partes.append(parse_openmeteo(r.json()))
            print(f"  ERA5 {d0} → {d1}")
            d0 = d1 + timedelta(days=1)
    except Exception as e:  # noqa: BLE001
        print(f"  [aviso] ERA5 (Open-Meteo) no respondió: {e}; se usa lo que haya en caché")
    if not partes:
        return s
    out = pd.concat(partes); out = out[~out.index.duplicated(keep="last")].sort_index()
    cache_csv.parent.mkdir(parents=True, exist_ok=True); out.rename_axis("t").to_csv(cache_csv)
    return out


def chirps_pixel(lat: float, lon: float) -> tuple[float, float]:
    f = lambda v: math.floor(v / 0.05) * 0.05 + 0.025  # noqa: E731
    return round(f(lat), 3), round(f(lon), 3)


def _leer_chirps_dia(fecha: date, lon: float, lat: float) -> float | None:
    import rasterio
    url = CHIRPS_URL.format(y=fecha.year, m=fecha.month, d=fecha.day)
    try:
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT="30"):
            with rasterio.open(f"/vsicurl/{url}") as s:
                v = float(next(s.sample([(lon, lat)]))[0])
        return None if v < -9000 else v
    except Exception:  # noqa: BLE001
        return None


def chirps_diaria(lat, lon, cache_csv: Path, hasta: date, hilos: int, leer=_leer_chirps_dia, desde: date = CHIRPS_DESDE) -> pd.Series:
    if lat < -50 or lat > 50:
        print("  CHIRPS no cubre latitudes fuera de ±50°: se usa sólo ERA5")
        return pd.Series(dtype=float, name="mm")
    s = _read_cache(cache_csv).dropna()
    faltan = [d.date() for d in pd.date_range(desde, hasta, freq="D") if pd.Timestamp(d) not in s.index]
    if faltan:
        print(f"  CHIRPS: {len(faltan)} días por leer ({hilos} hilos)…")
        with ThreadPoolExecutor(hilos) as ex:
            vals = list(ex.map(lambda d: leer(d, lon, lat), faltan))
        nuevos = pd.Series({pd.Timestamp(d): v for d, v in zip(faltan, vals) if v is not None}, dtype=float, name="mm")
        s = pd.concat([s, nuevos]).sort_index()
        cache_csv.parent.mkdir(parents=True, exist_ok=True); s.rename_axis("t").to_csv(cache_csv)
    return s.reindex(pd.date_range(desde, hasta, freq="D")).rename("mm")
```

- [ ] **Step 5: Correr y ver que pasen**

Run: `$PY python -m pytest tests/test_clima_fuentes.py -q`
Expected: `6 passed`

- [ ] **Step 6: Commit**

```bash
git add anega2/clima.py tests/test_clima_fuentes.py tests/fixtures/openmeteo_era5.json
git commit -m "clima: ERA5 (Open-Meteo) y CHIRPS por píxel con caché incremental"
```

---

### Task 3: `clima` — fase completa, salidas y CLI

**Files:**
- Modify: `anega2/clima.py` (agregar `build`, `run`, `resolve_events`)
- Modify: `anega2/cli.py:16-27` (FASES), `anega2/cli.py:86-93` (cmd_list)
- Modify: `anega2/defaults.yml` (bloque `clima`)
- Test: `tests/test_clima_run.py`

**Interfaces:**
- Consumes: Task 1 (`rolling_max_anual`, `gumbel_*`, `desagrupar`, `TS`), Task 2 (`era5_horaria`, `chirps_diaria`, `chirps_pixel`).
- Produces:
  - `build(era5: pd.Series, chirps: pd.Series, cfg: dict) -> dict` — puro; devuelve el dict de `clima.json` (estructura abajo).
  - `run(p: Project) -> dict` — escribe las salidas; nunca levanta excepción por red.
  - `resolve_events(p: Project) -> list[dict]` — eventos para Sentinel-1: si `p.cfg["sar"]["eventos"] == "auto"`, los de `out/clima.json` (`eventos.sentinel`), cada uno `{"id": "AAAA-MM-DD_era5", "fecha": "AAAA-MM-DD", "descr": "Tormenta de N mm en 72 h (ERA5)"}`; si no existe `clima.json` o `disponible` es false, devuelve `[]` y avisa; si es una lista, la devuelve tal cual.

Estructura de `clima.json` (contrato con `report.py`, `websim.py` y el visor):

```json
{"disponible": true, "punto": {"lat": -34.40, "lon": -59.42},
 "fuentes": {"era5": {"desde": "1940-01-01", "hasta": "2026-09-19", "anios": 86},
             "chirps": {"desde": "1981-01-01", "hasta": "2026-08-31", "anios": 45, "pixel": [-34.425, -59.425]}},
 "gumbel": {"era5": {"3": {"mu": 40.1, "beta": 12.3, "n": 86}, "24": {...}, "72": {...}}, "chirps": {"24": {...}, "72": {...}}},
 "retorno": [{"fuente": "era5", "dur_h": 24, "T": 10, "mm": 118.2, "lo": 105.0, "hi": 132.4}],
 "maximos": {"era5": {"24": [[1940, 61.2, "1940-05-03"]]}, "chirps": {"24": [[1981, 70.0, "1981-02-11"]]}},
 "eventos": {"historicos": [{"id": "2015-08-10_era5", "fecha": "2015-08-10", "era5_24": 61.1, "era5_72": 104.2, "chirps_24": 18.6, "chirps_72": 40.0}],
             "sentinel": [ ... misma forma, sólo fechas ≥ 2014-10-03 ... ]}}
```

(Si una fuente no tiene datos, su clave en `fuentes`, `gumbel` y `maximos` es `null`; si ninguna tiene, `{"disponible": false}`.)

- [ ] **Step 1: Agregar el bloque de config a `anega2/defaults.yml`** (después de `dem:`)

```yaml
clima:
  fuentes: [era5, chirps]      # lluvia histórica en el centroide del lote
  hilos_chirps: 16             # lecturas CHIRPS en paralelo (la primera vez ≈ 25 min para 1981-hoy)
  eventos_n: 10                # tormentas mayores a listar
  separacion_d: 7              # días mínimos entre tormentas distintas
```

- [ ] **Step 2: Escribir los tests**

```python
"""Fase clima de punta a punta con series sintéticas (sin red)."""
import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from anega2 import clima

CFG = dict(fuentes=["era5", "chirps"], hilos_chirps=2, eventos_n=3, separacion_d=7)


def _era5(anios=range(1990, 2021), seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{anios[0]}-01-01", f"{anios[-1]}-12-31 23:00", freq="h")
    s = pd.Series(0.0, index=idx)
    for a in anios:
        t = pd.Timestamp(f"{a}-{rng.integers(1, 13):02d}-10 12:00")
        s[t] = rng.gumbel(60, 20)
    s[pd.Timestamp("2016-04-05 12:00")] = 300.0     # la mayor, post-2014
    return s


def test_build_estructura_y_retorno():
    j = clima.build(_era5(), pd.Series(dtype=float), CFG)
    assert j["disponible"] and j["fuentes"]["chirps"] is None
    assert set(j["gumbel"]["era5"]) == {"3", "24", "72"}
    r10 = next(r for r in j["retorno"] if r["fuente"] == "era5" and r["dur_h"] == 24 and r["T"] == 10)
    assert r10["lo"] < r10["mm"] < r10["hi"]
    assert j["eventos"]["historicos"][0]["fecha"] == "2016-04-05"
    assert all(e["fecha"] >= "2014-10-03" for e in j["eventos"]["sentinel"])
    assert j["eventos"]["sentinel"][0]["id"] == "2016-04-05_era5"


def test_build_sin_fuentes():
    assert clima.build(pd.Series(dtype=float), pd.Series(dtype=float), CFG) == {"disponible": False}


def test_run_sin_fuentes(tmp_project, monkeypatch):
    monkeypatch.setattr(clima, "era5_horaria", lambda *a, **k: pd.Series(dtype=float))
    monkeypatch.setattr(clima, "chirps_diaria", lambda *a, **k: pd.Series(dtype=float))
    out = clima.run(tmp_project)
    assert out == {"disponible": False}
    assert json.loads((tmp_project.out / "clima.json").read_text()) == {"disponible": False}


def test_run_escribe_salidas(tmp_project, monkeypatch):
    monkeypatch.setattr(clima, "era5_horaria", lambda *a, **k: _era5())
    monkeypatch.setattr(clima, "chirps_diaria", lambda *a, **k: _era5().resample("D").sum())
    clima.run(tmp_project)
    for f in ["clima_serie_diaria.csv", "clima_maximos_anuales.csv", "clima_retorno.csv", "clima_eventos.csv", "clima_stats.md", "clima.json"]:
        assert (tmp_project.out / f).exists(), f


def test_resolve_events_manual_y_auto(tmp_project):
    tmp_project.cfg["sar"]["eventos"] = [{"id": "x", "fecha": "2020-01-01"}]
    assert clima.resolve_events(tmp_project) == [{"id": "x", "fecha": "2020-01-01"}]
    tmp_project.cfg["sar"]["eventos"] = "auto"
    (tmp_project.out / "clima.json").write_text(json.dumps(clima.build(_era5(), pd.Series(dtype=float), CFG)))
    ev = clima.resolve_events(tmp_project)
    assert ev[0] == {"id": "2016-04-05_era5", "fecha": "2016-04-05", "descr": "Tormenta de 300 mm en 72 h (ERA5)"}
```

- [ ] **Step 3: Correr y ver que fallen**

Run: `$PY python -m pytest tests/test_clima_run.py -q`
Expected: FAIL — `AttributeError: ... has no attribute 'build'`

- [ ] **Step 4: Implementar** (al final de `anega2/clima.py`; imports: `import json`, `from .common import df_to_md`, `from .project import Project`)

```python
# ------------------------------------------------------------------ fase
DUR_ERA5 = [3, 24, 72]
DUR_CHIRPS = [24, 72]
S1_DESDE = "2014-10-03"


def _diaria(s: pd.Series) -> pd.Series:
    return s.resample("D").sum(min_count=1) if len(s) and _paso_h(s) < 24 else s


def _evento(t, era5, chirps) -> dict:
    t = pd.Timestamp(t); d = t.normalize()
    e24 = era5[t - pd.Timedelta(hours=71):t].rolling(24, min_periods=1).sum().max() if len(era5) else np.nan
    e72 = era5[t - pd.Timedelta(hours=71):t].sum() if len(era5) else np.nan
    c = chirps[d - pd.Timedelta(days=2):d] if len(chirps) else pd.Series(dtype=float)
    r = lambda v: None if v is None or not np.isfinite(v) else round(float(v), 1)  # noqa: E731
    return dict(id=f"{d.date()}_era5", fecha=str(d.date()), era5_24=r(e24), era5_72=r(e72),
                chirps_24=r(c.max()) if len(c) else None, chirps_72=r(c.sum(min_count=1)) if len(c) else None)


def build(era5: pd.Series, chirps: pd.Series, cfg: dict) -> dict:
    era5 = era5.dropna() if len(era5) else era5
    fuentes = {"era5": (era5, DUR_ERA5), "chirps": (chirps.dropna() if len(chirps) else chirps, DUR_CHIRPS)}
    if all(len(s) == 0 for s, _ in fuentes.values()):
        return {"disponible": False}
    out = dict(disponible=True, fuentes={}, gumbel={}, retorno=[], maximos={})
    for nom, (s, durs) in fuentes.items():
        if len(s) == 0:
            out["fuentes"][nom] = out["gumbel"][nom] = out["maximos"][nom] = None; continue
        s = s.asfreq("h" if nom == "era5" else "D")
        out["fuentes"][nom] = dict(desde=str(s.index.min().date()), hasta=str(s.index.max().date()), anios=int(s.index.year.nunique()))
        out["gumbel"][nom] = {}; out["maximos"][nom] = {}
        for dur in durs:
            am = rolling_max_anual(s, dur)
            if len(am) < 10:
                continue
            fit = gumbel_fit(am.mm.values); ic = gumbel_ic(am.mm.values, TS)
            out["gumbel"][nom][str(dur)] = fit
            out["maximos"][nom][str(dur)] = [[int(a), round(float(m), 1), str(pd.Timestamp(f).date())] for a, m, f in am.itertuples(index=False)]
            out["retorno"] += [dict(fuente=nom, dur_h=dur, T=T, mm=round(gumbel_mm(fit, T), 1), lo=round(ic[T][0], 1), hi=round(ic[T][1], 1)) for T in TS]
    base = era5.asfreq("h") if len(era5) else _diaria(chirps).asfreq("D")
    s72 = base.rolling(72 if len(era5) else 3, min_periods=1).sum()
    n, sep = int(cfg.get("eventos_n", 10)), int(cfg.get("separacion_d", 7))
    ev = lambda desde: [_evento(t, era5.asfreq("h") if len(era5) else era5, _diaria(chirps)) for t in desagrupar(s72, n, sep, desde)]  # noqa: E731
    out["eventos"] = dict(historicos=ev(None), sentinel=ev(S1_DESDE))
    return out


def run(p: Project) -> dict:
    cfg = p.cfg.get("clima", {}); fuentes = cfg.get("fuentes", ["era5", "chirps"])
    lon, lat = p.lot_centroid_wgs84(); hasta = date.today() - timedelta(days=6)
    era5 = era5_horaria(lat, lon, p.data_raw / "clima" / f"era5_{lat:.3f}_{lon:.3f}.csv", hasta) if "era5" in fuentes else pd.Series(dtype=float)
    chirps = pd.Series(dtype=float)
    if "chirps" in fuentes:
        clat, clon = chirps_pixel(lat, lon); cache = p.cache / "chirps" / f"{clat:.3f}_{clon:.3f}.csv"
        if cache.exists() or p.confirm(f"Leer CHIRPS diario 1981-hoy para el píxel {clat}, {clon} (≈ 16.000 lecturas, ~25 min la primera vez; queda en {cache})"):
            chirps = chirps_diaria(lat, lon, cache, date.today() - timedelta(days=45), int(cfg.get("hilos_chirps", 16)))
    j = build(era5, chirps, cfg)
    if j.get("disponible"):
        j["punto"] = dict(lat=round(lat, 5), lon=round(lon, 5))
        if j["fuentes"].get("chirps"):
            j["fuentes"]["chirps"]["pixel"] = list(chirps_pixel(lat, lon))
    o = p.out
    json.dump(j, open(o / "clima.json", "w"), ensure_ascii=False, indent=1)
    if not j.get("disponible"):
        print("CLIMA: sin datos de lluvia (sin red o fuentes caídas); el visor lo informa y sar con eventos: auto se saltea.")
        return j
    pd.DataFrame({"era5_mm": _diaria(era5) if len(era5) else pd.Series(dtype=float), "chirps_mm": chirps}).rename_axis("fecha").to_csv(o / "clima_serie_diaria.csv", float_format="%.1f")
    am = pd.DataFrame([dict(fuente=f, dur_h=int(d), anio=a, mm=m, fecha=fe) for f, g in j["maximos"].items() if g for d, rows in g.items() for a, m, fe in rows])
    am.to_csv(o / "clima_maximos_anuales.csv", index=False)
    rt = pd.DataFrame(j["retorno"]); rt.to_csv(o / "clima_retorno.csv", index=False)
    evs = pd.DataFrame([dict(tipo=k, **e) for k, lst in j["eventos"].items() for e in lst]); evs.to_csv(o / "clima_eventos.csv", index=False)
    (o / "clima_stats.md").write_text(
        "# Lluvia histórica en el lote\n\n"
        f"ERA5 (Open-Meteo, 0,25°): {j['fuentes'].get('era5') or 'sin datos'} · CHIRPS v2 (0,05°): {j['fuentes'].get('chirps') or 'sin datos'}.\n"
        "Período de retorno por Gumbel (momentos) sobre máximos anuales; intervalo 90 % por bootstrap. ERA5 subestima picos "
        "convectivos: comparar con CHIRPS.\n\n## Período de retorno (mm)\n\n" + df_to_md(rt) + "\n\n## Tormentas mayores\n\n" + df_to_md(evs) + "\n")
    r24 = {r["T"]: r["mm"] for r in j["retorno"] if r["fuente"] == "era5" and r["dur_h"] == 24}
    p.summary_line("CLIMA (lluvia histórica)", [
        f"ERA5 {j['fuentes'].get('era5')} · CHIRPS {j['fuentes'].get('chirps')}",
        "24 h (ERA5): " + " · ".join(f"T{T}={mm:.0f} mm" for T, mm in r24.items()),
        "Mayores: " + ", ".join(f"{e['fecha']} ({e['era5_72']} mm/72 h)" for e in j["eventos"]["historicos"][:5])])
    return j


def resolve_events(p: Project) -> list[dict]:
    ev = p.cfg.get("sar", {}).get("eventos", "auto")
    if ev != "auto":
        return list(ev or [])
    f = p.out / "clima.json"
    j = json.loads(f.read_text()) if f.exists() else {}
    if not j.get("disponible"):
        print("  [aviso] sar.eventos = auto pero no hay out/clima.json con datos (correr la fase clima)")
        return []
    return [dict(id=e["id"], fecha=e["fecha"], descr=f"Tormenta de {e['era5_72']:.0f} mm en 72 h (ERA5)") for e in j["eventos"]["sentinel"]]
```

- [ ] **Step 5: Registrar la fase en la CLI**

En `anega2/cli.py`, en `FASES`, insertar después de la línea de `"agua"`:
```python
    ("clima", "lluvia histórica en el lote (ERA5 + CHIRPS): máximos, período de retorno, tormentas", "clima"),
```
y en `cmd_list`, en el dict de archivos, agregar `"clima": "clima.json",`.

- [ ] **Step 6: Correr los tests**

Run: `$PY python -m pytest tests -q`
Expected: todos pasan (`19 passed`).

- [ ] **Step 7: Prueba real** (red)

Run: `$PY anega2 run ejemplo-bajo-giles --fase clima --si`
Expected: `RESUMEN CLIMA` con ERA5 1940-2026, CHIRPS 1981-2026 y el evento de agosto 2015 entre los mayores. Anotar en el commit el tiempo que tardó CHIRPS.

- [ ] **Step 8: Commit**

```bash
git add anega2/clima.py anega2/cli.py anega2/defaults.yml tests/test_clima_run.py
git commit -m "Fase clima: lluvia histórica ERA5 + CHIRPS, período de retorno y tormentas mayores"
```

---

### Task 4: `sar` con eventos automáticos y pasada a tiempo; `report` sin depender de la lista de eventos

**Files:**
- Modify: `anega2/sar.py` (función nueva `plan_escenas` + `run`)
- Modify: `anega2/report.py:283` (`_campo`), `anega2/report.py:309` (`build`), agregar línea de retorno
- Modify: `anega2/defaults.yml` (bloque `sar`)
- Modify: `projects/ejemplo-bajo-giles/project.yml` (sin cambios de eventos; verificar que siga teniendo la lista manual)
- Test: `tests/test_sar_plan.py`, `tests/test_report.py`

**Interfaces:**
- Consumes: `clima.resolve_events(p)` (Task 3).
- Produces:
  - `sar.plan_escenas(fechas_escenas: list[date], fecha_evento: date, pre_max_d: int, post_max_d: int) -> tuple[date | None, date | None]` — (pre, post).
  - Filas de `sar_stats.csv` con `nota = "sin pasada a tiempo"` y `escena = "SIN PASADA A TIEMPO"` cuando no hay post.
  - `report.eventos_analizados(R: dict) -> list[str]` — ids de eventos a partir de `sar_stats.csv` (sin `referencia_seca`).

- [ ] **Step 1: Cambiar defaults**

En `anega2/defaults.yml`, reemplazar el bloque `eventos:` de `sar` (las 5 líneas del norte bonaerense) por:
```yaml
  eventos: auto                # auto = tormentas mayores desde 2014 según la fase clima; o una lista [{id, fecha, descr}]
  pre_max_d: 12                # escena "antes": la última dentro de estos días previos
  post_max_d: 3                # escena "después": la primera dentro de estos días posteriores (si no hay: "sin pasada a tiempo")
```
Verificar que `projects/ejemplo-bajo-giles/project.yml` conserva su lista explícita de 5 eventos (sí la tiene: no tocar).

- [ ] **Step 2: Tests**

`tests/test_sar_plan.py`:
```python
from datetime import date

from anega2 import clima, sar


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
```

`tests/test_report.py`:
```python
import pandas as pd

from anega2 import report


def test_eventos_analizados_desde_sar_stats():
    R = {"sar": pd.DataFrame({"evento": ["referencia_seca", "2016-04-05_era5", "2016-04-05_era5", "2024-03-12_era5"]})}
    assert report.eventos_analizados(R) == ["2016-04-05", "2024-03-12"]


def test_eventos_analizados_sin_sar():
    assert report.eventos_analizados({"sar": None}) == []
```

- [ ] **Step 3: Correr y ver que fallen**

Run: `$PY python -m pytest tests/test_sar_plan.py tests/test_report.py -q`
Expected: FAIL — `AttributeError: module 'anega2.sar' has no attribute 'plan_escenas'`

- [ ] **Step 4: Implementar `plan_escenas` y usarlo en `sar.run`**

En `anega2/sar.py`, antes de `def run`:
```python
def plan_escenas(fechas, fecha_evento, pre_max_d: int, post_max_d: int):
    """(pre, post): la última fecha en [evento − pre_max_d, evento) y la primera en [evento, evento + post_max_d]."""
    pre = [d for d in fechas if 0 < (fecha_evento - d).days <= pre_max_d]
    post = [d for d in fechas if 0 <= (d - fecha_evento).days <= post_max_d]
    return (max(pre) if pre else None, min(post) if post else None)
```

En `sar.run`, reemplazar
```python
    events = {e["id"]: e for e in cfg.get("eventos", [])}
```
por
```python
    from .clima import resolve_events
    events = {e["id"]: e for e in resolve_events(p)}
    if not events:
        print("SAR: sin eventos para buscar; se omite la fase."); return {}
    pre_max, post_max = int(cfg.get("pre_max_d", 12)), int(cfg.get("post_max_d", 3))
```
y reemplazar el cuerpo del `for key, ev in events.items():` de la búsqueda (desde `d = pd.Timestamp(...)` hasta el `plan.append(...)` del loop interno) por:
```python
        d = pd.Timestamp(ev["fecha"])
        items = search(str((d - pd.Timedelta(days=pre_max)).date()), str((d + pd.Timedelta(days=post_max)).date()), bbox)
        by_date = {}
        for it in items:
            by_date.setdefault(it.datetime.date(), []).append(it)
        pre, post = plan_escenas(list(by_date), d.date(), pre_max, post_max)
        if pre is None and post is None and not by_date:
            plan.append((key, ev, None, None, None)); continue
        if pre is not None:
            plan.append((key, ev, _pick_frame(by_date[pre], lot84), pre, "pre"))
        if post is not None:
            plan.append((key, ev, _pick_frame(by_date[post], lot84), post, "post"))
        else:
            plan.append((key, ev, None, None, "sin_post"))
```
En el loop de eventos (`for key, ev, it, date, tag in plan:`), reemplazar el bloque `if it is None:` por:
```python
        if it is None:
            if tag == "sin_post":
                print(f"[{key}] sin pasada de Sentinel-1 dentro de los {post_max} días posteriores")
                rows.append(dict(evento=key, descr=ev.get("descr", ""), escena="SIN PASADA A TIEMPO", fecha=None, momento="post",
                                 nota=f"sin pasada en 0-{post_max} días: no se puede saber si hubo agua")); continue
            print(f"[{key}] sin escenas entre −{pre_max} y +{post_max} días de {ev['fecha']}")
            rows.append(dict(evento=key, descr=ev.get("descr", ""), escena="SIN COBERTURA", fecha=None)); continue
```
En `anega2/webdata.py:233`, cambiar `if not isinstance(r.get("escena"), str) or r["escena"] == "SIN COBERTURA":` por `if not isinstance(r.get("escena"), str) or r["escena"] in ("SIN COBERTURA", "SIN PASADA A TIEMPO"):` (si no, el visor busca un archivo de escena inexistente).
En la línea del resumen final (`if r.get("escena") == "SIN COBERTURA":`) cambiar la condición a `if r.get("escena") in ("SIN COBERTURA", "SIN PASADA A TIEMPO"):` y el texto a `f"{r['evento']}: {r['escena'].lower()}"`.

- [ ] **Step 5: `report.py`**

Agregar después de `_num`:
```python
def eventos_analizados(R: dict) -> list[str]:
    s = R.get("sar")
    if s is None or "evento" not in s:
        return []
    return list(dict.fromkeys(str(e).split("_")[0] for e in s["evento"] if e != "referencia_seca"))
```
En `_campo`, reemplazar `{', '.join(e['id'].split('_')[0] for e in p.cfg['sar']['eventos'])}` por `{', '.join(eventos_analizados(R)) or 'las lluvias grandes recientes'}`.
En `build`, reemplazar `ev_ids = [e["id"] for e in p.cfg["sar"]["eventos"]]` por `ev_ids = eventos_analizados(R) or ["ninguno"]`.
En `_tabla_sar`, cambiar `if r.get("escena") == "SIN COBERTURA" or pd.isna(r.get("fecha")):` por:
```python
        if r.get("escena") == "SIN PASADA A TIEMPO":
            s += f"| {str(r['evento']).replace('_', ' ')} | **sin pasada a tiempo** (no se puede saber) | — | — |\n"; continue
        if r.get("escena") == "SIN COBERTURA" or pd.isna(r.get("fecha")):
```
En `load_results`, agregar `R["clima"] = json.load(open(o / "clima.json")) if (o / "clima.json").exists() else None` (y `"clima": None` en el dict inicial).
En `_veredicto`, al final antes de la «Limitación principal», agregar:
```python
    cl = R.get("clima") or {}
    if cl.get("disponible") and cl["gumbel"].get("era5") and "24" in cl["gumbel"]["era5"]:
        from .clima import gumbel_T
        t_e = gumbel_T(cl["gumbel"]["era5"]["24"], 100)
        g_c = (cl["gumbel"].get("chirps") or {}).get("24")
        s += (f"- **Frecuencia**: 100 mm en 24 h ocurre en promedio cada {f(t_e, 0)} años según ERA5"
              + (f" (cada {f(gumbel_T(g_c, 100), 0)} según CHIRPS)" if g_c else "") + ".\n")
```
En «## 4. Limitaciones», reemplazar la línea `- **Sin período de retorno**: los escenarios son "mm en 24 h".` por `- **Período de retorno aproximado**: Gumbel sobre máximos anuales de ERA5 (28 km, subestima tormentas convectivas) y CHIRPS (5 km); no hay IDF local.`

- [ ] **Step 6: Correr tests**

Run: `$PY python -m pytest tests -q`
Expected: todo pasa.

- [ ] **Step 7: Prueba real**

Run: `$PY anega2 run ejemplo-bajo-giles --fase sar informe --si`
Expected: en `sar_stats.md`, el evento 2024-03 (post a +15 d) aparece como «sin pasada a tiempo»; el informe se genera sin errores.

- [ ] **Step 8: Commit**

```bash
git add anega2/sar.py anega2/report.py anega2/webdata.py anega2/defaults.yml tests/test_sar_plan.py tests/test_report.py
git commit -m "sar: eventos automáticos desde clima y pasada dentro de 0-3 días; informe con período de retorno"
```

---

### Task 5: Grilla de escenarios y compatibilidad con el formato viejo

**Files:**
- Modify: `anega2/rog.py` (`build_scenarios`, nueva `scenario_specs`)
- Modify: `anega2/defaults.yml` (bloque `lluvia`), `projects/ejemplo-bajo-giles/project.yml` (bloque `lluvia`)
- Modify: `anega2/kml.py:105-107,137-138`, `anega2/webdata.py:259-260`
- Test: `tests/test_rog_grilla.py`

**Interfaces:**
- Produces:
  - `rog.scen_id(P: float, dur: float, sat: bool) -> str` — `P025_3h`, `P100_24h_sat`.
  - `rog.scenario_specs(cfg: dict) -> list[dict]` — `[{"id", "P_mm", "dur_h", "suelo": "normal"|"saturado"}]`, desde `grilla` o, si hay `escenarios`, desde el formato viejo (con aviso impreso una vez).
  - `rog.build_scenarios(cfg) -> dict` — misma salida que hoy (`{id: dict(P_mm, dur_h, dt_h, ratios, t_end_h, Ks_mm_h, label)}`), ahora construida sobre `scenario_specs`.
  - `rog.ficha_ids(cfg) -> list[str]` — `cfg["ficha"]` si existe, si no los ids de `scenario_specs` con `dur_h == 24`.

- [ ] **Step 1: Config**

En `anega2/defaults.yml`, reemplazar las líneas `escenarios:` … `saturado: [...]` del bloque `lluvia` por:
```yaml
  grilla:                      # 10 × 3 × 2 = 60 corridas (≈ 2-3 h en paralelo la primera vez)
    P_mm: [25, 50, 75, 100, 125, 150, 175, 200, 225, 250]
    dur_h: [3, 24, 72]
    suelo: [normal, saturado]
  ficha: [P050_24h, P100_24h, P150_24h, P200_24h, P100_24h_sat, P150_24h_sat]   # escenarios con PNG, ficha y KML
  procesos: auto               # corridas en paralelo: auto = núcleos − 2
  ensamble: {P_mm: [50, 100, 150, 200], dur_h: [24], suelo: [normal]}          # se repiten con los otros DEM (certeza)
```
y cambiar `drenaje_h: 6` por `drenaje_h: 24`.
En `projects/ejemplo-bajo-giles/project.yml`, borrar las claves `escenarios` y `saturado` del bloque `lluvia` y cambiar `drenaje_h: 6` por `drenaje_h: 24` (hereda `grilla`, `ficha`, `procesos`, `ensamble` de los defaults).

- [ ] **Step 2: Tests**

```python
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
```

- [ ] **Step 3: Correr y ver que fallen**

Run: `$PY python -m pytest tests/test_rog_grilla.py -q`
Expected: FAIL — `AttributeError: module 'anega2.rog' has no attribute 'scen_id'`

- [ ] **Step 4: Implementar** (reemplazar `build_scenarios` en `anega2/rog.py`)

```python
def scen_id(P: float, dur: float, sat: bool) -> str:
    return f"P{int(round(P)):03d}_{dur:g}h" + ("_sat" if sat else "")


def scenario_specs(cfg: dict) -> list[dict]:
    """Escenarios a correr: la grilla P × duración × suelo, o la lista del formato viejo (escenarios + saturado)."""
    if cfg.get("escenarios"):
        print("  [aviso] lluvia.escenarios / saturado es el formato viejo: se usa tal cual (ver lluvia.grilla en defaults.yml)")
        out = [dict(id=s["id"], P_mm=float(s["P_mm"]), dur_h=float(s["dur_h"]), suelo="normal") for s in cfg["escenarios"]]
        by = {s["id"]: s for s in out}
        out += [dict(by[i], id=f"{i}_sat", suelo="saturado") for i in cfg.get("saturado", []) or [] if i in by]
        return out
    g = cfg["grilla"]
    return [dict(id=scen_id(P, d, s == "saturado"), P_mm=float(P), dur_h=float(d), suelo=s)
            for P in g["P_mm"] for d in g["dur_h"] for s in g["suelo"]]


def build_scenarios(cfg: dict) -> dict:
    """Escenarios -> {id: dict(P_mm, dur_h, dt_h, ratios, t_end_h, Ks_mm_h, suelo, label)}."""
    dren = float(cfg.get("drenaje_h", 24)); out = {}
    for s in scenario_specs(cfg):
        dur, P, sat = s["dur_h"], s["P_mm"], s["suelo"] == "saturado"
        dt_h = 1.0 if dur >= 6 else 1 / 6
        shape_ = DD_SHAPE_LONG if dur > 3 else DD_SHAPE_SHORT
        ks = float(cfg["Ks_sat_mm_h"] if sat else cfg["Ks_mm_h"])
        out[s["id"]] = dict(P_mm=P, dur_h=dur, dt_h=dt_h, ratios={f * dur: r for f, r in shape_.items()}, t_end_h=dur + dren, Ks_mm_h=ks,
                            suelo=s["suelo"], label=f"{P:g} mm en {dur:g} h" + (f" · suelo saturado (Ks {ks:g} mm/h)" if sat else ""))
    return out


def ficha_ids(cfg: dict) -> list[str]:
    return list(cfg.get("ficha") or [s["id"] for s in scenario_specs(cfg) if s["dur_h"] == 24])
```

Nota: `dur > 3` elige `DD_SHAPE_SHORT` para 3 h (igual que hoy para 2 h). Verificar que `test_hietograma_suma_P` pase para 3 h; si `alternating_block` no suma exacto por el `np.interp` con `left=`, el test lo detecta y hay que corregir `alternating_block` (no el test).

- [ ] **Step 5: Consumidores**

`anega2/kml.py`: agregar `from .rog import ficha_ids, scenario_specs` y reemplazar la línea 106 por
```python
    esc = [i for i in ficha_ids(p.cfg.get("lluvia", {})) if i in ("P100_24h", "P150_24h")]
```
y la línea 137 por
```python
        cfg_e = next((x for x in scenario_specs(p.cfg.get("lluvia", {})) if x["id"] == e), None)
```
`anega2/report.py` (`indicators`, función interna `row_for`): cambiar `(r["dur_h"] >= 6)` por `(r["dur_h"] == 24)`, para que con la grilla (24 y 72 h) las reglas lean siempre el escenario de 24 h.
`anega2/webdata.py:260`: reemplazar `by_id = {s["id"]: s for s in cfg_ll.get("escenarios", [])}` por `by_id = {s["id"]: s for s in scenario_specs(cfg_ll)}` (import `from .rog import scenario_specs`), y en el loop de escenarios de la línea 262 agregar al principio `if name not in ficha_ids(cfg_ll): continue` (import `ficha_ids`), para que la vista técnica sólo muestre los escenarios de la ficha.

- [ ] **Step 6: Tests**

Run: `$PY python -m pytest tests -q`
Expected: todo pasa.

- [ ] **Step 7: Commit**

```bash
git add anega2/rog.py anega2/kml.py anega2/webdata.py anega2/report.py anega2/defaults.yml projects/ejemplo-bajo-giles/project.yml tests/test_rog_grilla.py
git commit -m "lluvia: grilla de 60 escenarios (P × duración × suelo), compatible con el formato viejo"
```

---

### Task 6: Cuadros horarios, estadísticas del lote por hora y corridas en paralelo

**Files:**
- Modify: `anega2/rog.py` (`run_scenario`, `run`, nuevas `encode_frame`, `lote_por_hora`, `_worker`)
- Test: `tests/test_rog_frames.py`

**Interfaces:**
- Consumes: `build_scenarios`, `ficha_ids` (Task 5).
- Produces:
  - `encode_frame(h_m: np.ndarray) -> np.ndarray` — uint8 cm, `clip(round((h − H_FILM)·100), 0, 255)`.
  - `lote_por_hora(frames: np.ndarray, lot: np.ndarray) -> dict` — `{"hmax_lote_cm": [int], "pct_lote_gt5cm": [float], "pct_lote_gt20cm": [float], "horas_con_agua_lote": int, "hora_pico_lote": int}` (frames `[t, rows, cols]` uint8 norte arriba; `lot` bool mismo shape).
  - `run_scenario(p, name, sc, z, tr, params, budget_s, lot, subdir="") -> dict` — firma nueva con `lot` (bool, norte arriba) y `subdir` (p. ej. `"ens"`); además de lo actual guarda `data/proc/rog/<subdir>/<name>_frames.npz` con `h_cm` (uint8 `[t, rows, cols]`, norte arriba), `t_h` (int), `lluvia_acum_mm` (float por hora) y agrega a `<name>_meta.json` las claves de `lote_por_hora`. La caché exige los tres archivos (tif, meta, frames).
  - `rog.run` corre los escenarios faltantes con `ProcessPoolExecutor(n)` (`procesos: auto` → `max(1, os.cpu_count() − 2)`), y genera PNG, GeoJSON/KML sólo para `ficha_ids`.

- [ ] **Step 1: Tests**

```python
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
```

- [ ] **Step 2: Correr y ver que fallen**

Run: `$PY python -m pytest tests/test_rog_frames.py -q`
Expected: FAIL — `AttributeError: ... 'encode_frame'`

- [ ] **Step 3: Implementar helpers** (en `anega2/rog.py`, después de las constantes)

```python
def encode_frame(h_m: np.ndarray) -> np.ndarray:
    return np.clip(np.round((h_m - H_FILM) * 100), 0, 255).astype(np.uint8)


def lote_por_hora(frames: np.ndarray, lot: np.ndarray) -> dict:
    v = frames[:, lot].astype(float)
    hmax = v.max(axis=1)
    return dict(hmax_lote_cm=[int(x) for x in hmax],
                pct_lote_gt5cm=[round(100 * float(x), 1) for x in (v > 5).mean(axis=1)],
                pct_lote_gt20cm=[round(100 * float(x), 1) for x in (v > 20).mean(axis=1)],
                horas_con_agua_lote=int((hmax > 5).sum()), hora_pico_lote=int(hmax.argmax()))
```

- [ ] **Step 4: Cambiar `run_scenario`**

Firma: `def run_scenario(p, name, sc, z, tr, params, budget_s, lot, subdir: str = "") -> dict:`
- `proc = p.data_proc / "rog" / subdir` (con `mkdir(parents=True, exist_ok=True)`), `frames_path = proc / f"{name}_frames.npz"`.
- Caché: exigir también `frames_path.exists()`.
- Antes del `while`: `frames = [encode_frame(np.flipud(h.reshape(rows, cols)))]; rain_acc = [0.0]; next_frame = 3600.0`.
- `dt` también se limita a no pasar la próxima hora: agregar `next_frame - t` a la lista del `min(...)` que calcula `dt`.
- Al final de cada paso (después de `t += dt`):
```python
        if t >= next_frame - 1e-6:
            frames.append(encode_frame(np.flipud(h.reshape(rows, cols)))); rain_acc.append(rain_tot * 1000); next_frame += 3600.0
```
- Después del loop:
```python
    fr = np.stack(frames)
    np.savez_compressed(frames_path, h_cm=fr, t_h=np.arange(len(fr)), lluvia_acum_mm=np.array(rain_acc))
    meta.update(lote_por_hora(fr, lot))
```
(el `meta.update` va antes del `json.dump(meta, ...)`). En la rama de caché, devolver también lo que haya en meta como hoy.

- [ ] **Step 5: Paralelo en `run`**

Arriba del módulo: `import os` y `from concurrent.futures import ProcessPoolExecutor`. Función de nivel de módulo:
```python
def _worker(args):
    p, name, sc, z, tr, params, budget_s, lot, subdir = args
    return name, run_scenario(p, name, sc, z, tr, params, budget_s, lot, subdir)
```
En `run`, después de `scen = build_scenarios(cfg)`:
```python
    nproc = cfg.get("procesos", "auto"); nproc = max(1, (os.cpu_count() or 4) - 2) if nproc == "auto" else int(nproc)
    lot_n = rasterize_geom(aoi["lote"], z.shape, tr, all_touched=True)
    jobs = [(p, name, sc, z, tr, params, budget_s, lot_n, "") for name, sc in scen.items()]
    print(f"{len(jobs)} escenarios · {nproc} en paralelo")
    with ProcessPoolExecutor(nproc) as ex:
        res = dict(ex.map(_worker, jobs))
```
y el loop `for name, sc in scen.items():` usa `r = res[name]` en lugar de llamar a `run_scenario`. Los `plot_map`, `features.shapes` y KML de manchas se ejecutan sólo si `name in ficha_ids(cfg)`. Las filas de `rog_stats.csv` se generan para todos (60 filas).

- [ ] **Step 6: Tests**

Run: `$PY python -m pytest tests -q`
Expected: todo pasa.

- [ ] **Step 7: Commit**

```bash
git add anega2/rog.py tests/test_rog_frames.py
git commit -m "lluvia: cuadros horarios (cm) y agua en el lote por hora; escenarios en paralelo"
```

---

### Task 7: Ensamble con los otros DEM

**Files:**
- Modify: `anega2/rog.py` (nueva `ensemble_jobs`, llamada en `run`)
- Test: `tests/test_rog_ensamble.py`

**Interfaces:**
- Consumes: `run_scenario(..., lot, subdir)`, `scenario_specs`, `scen_id` (Tasks 5-6).
- Produces:
  - `rog.ensemble_dems(p, primary) -> list[str]` — DEM con `data/proc/terrain/<dem>/dem_breach.tif`, sin el primario, en orden alfabético.
  - `rog.ensemble_ids(cfg) -> list[str]` — ids de `cfg["ensamble"]` (grilla chica, mismo esquema que `grilla`); `[]` si no hay `ensamble`.
  - Corridas guardadas como `data/proc/rog/ens/<id>__<dem>_{hmax_dom.tif,dur5cm_dom.tif,meta.json,frames.npz}`.
  - `out/rog_ensamble.json`: `{"dems": ["glo30", "ign30"], "ids": ["P050_24h", ...], "primario": "fabdem"}`.

- [ ] **Step 1: Tests**

```python
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
```

- [ ] **Step 2: Correr y ver que fallen**

Run: `$PY python -m pytest tests/test_rog_ensamble.py -q`
Expected: FAIL — `AttributeError: ... 'ensemble_ids'`

- [ ] **Step 3: Implementar**

```python
def ensemble_ids(cfg: dict) -> list[str]:
    e = cfg.get("ensamble")
    return [] if not e else [scen_id(P, d, s == "saturado") for P in e["P_mm"] for d in e["dur_h"] for s in e["suelo"]]


def ensemble_dems(p: Project, primary: str) -> list[str]:
    base = p.data_proc / "terrain"
    return sorted(q.name for q in base.iterdir() if q.is_dir() and q.name != primary and (q / "dem_breach.tif").exists()) if base.exists() else []
```
En `run`, después de armar `jobs` del primario y antes del `ProcessPoolExecutor`:
```python
    ens_ids = [i for i in ensemble_ids(cfg) if i in scen]; ens_dems = ensemble_dems(p, primary)
    for dem in ens_dems:
        z_d, tr_d = load_dem_window(p, dem, aoi)
        if z_d.shape != z.shape:
            print(f"  [aviso] {dem}: grilla {z_d.shape} ≠ {z.shape}; se omite del ensamble"); continue
        jobs += [(p, f"{i}__{dem}", scen[i], z_d, tr_d, params, budget_s, lot_n, "ens") for i in ens_ids]
    json.dump(dict(dems=ens_dems, ids=ens_ids, primario=primary), open(out / "rog_ensamble.json", "w"), indent=1)
```
y en el loop de estadísticas, iterar sólo sobre `scen` (los `__dem` no generan filas ni PNG): `res[name]` con `name in scen`.

- [ ] **Step 4: Tests**

Run: `$PY python -m pytest tests -q`
Expected: todo pasa.

- [ ] **Step 5: Corrida real completa** (larga: dejar en segundo plano y anotar el tiempo)

Run: `$PY anega2 run ejemplo-bajo-giles --fase lluvia --si 2>&1 | tee /tmp/lluvia.log`
Expected: 60 + 8 corridas; `rog_stats.csv` con 60 filas; `P100_24h` con `hmax_lote_m` entre 0,06 y 0,10 (hoy 0,08); `balance.error_pct` < 1 % en los meta. Anotar el tiempo total en el commit.

- [ ] **Step 6: Commit**

```bash
git add anega2/rog.py tests/test_rog_ensamble.py
git commit -m "lluvia: ensamble de escenarios clave con los otros DEM (para la certeza)"
```

---

### Task 8: `websim` — cuadros a EPSG:3857, certeza y `web/sim/`

**Files:**
- Create: `anega2/websim.py`
- Modify: `anega2/webdata.py` (llamar `websim.run(p)` al final de `run`)
- Test: `tests/test_websim.py`

**Interfaces:**
- Consumes: `data/proc/rog/<id>_frames.npz`, `data/proc/rog/ens/<id>__<dem>_frames.npz`, `<id>_meta.json`, `out/rog_ensamble.json`, `out/clima.json`, `rog.scenario_specs`, `clima.gumbel_T`.
- Produces:
  - `websim.grilla_3857(tr, crs, shape, lat) -> dict` — `{"transform": [a, b, c, d, e, f] (3857), "cols", "rows", "bounds_3857", "bounds_wgs84": [[s, w], [n, e]], "res_m": float}`; resolución en unidades 3857 = `res_proyecto / cos(lat)` (≈ celdas de 30 m en el terreno).
  - `websim.a_3857(frames: np.ndarray, tr, crs, g: dict) -> np.ndarray` — reproyección vecino más cercano de `[t, r, c]` uint8 a `[t, g.rows, g.cols]` uint8 (fuera = 0).
  - `websim.certeza(frames_por_dem: list[np.ndarray], umbral_cm: int) -> np.ndarray` — uint8 0-100 `[t, r, c]`: media sobre DEM de `uniform_filter((f > umbral).astype(float), size=(1, 3, 3), mode="constant")`; si los shapes difieren, usa el de `frames_por_dem[0]` y los demás se recortan/rellenan con 0 al mismo shape.
  - `websim.lote_idx(lote_geom, crs, g) -> list[int]` — índices lineales (fila·cols + col) de la grilla 3857 que tocan el lote.
  - Archivos: `web/sim/<id>.bin.gz` (gzip de `uint8[t][rows][cols]`), `web/sim/<id>_cert.bin.gz` (gzip de `uint8[2][t][rows][cols]`, umbral 5 y 20 cm), `web/sim/index.json`:

```json
{"grid": {"transform": [...], "cols": 380, "rows": 380, "bounds_wgs84": [[s, w], [n, e]], "res_m": 36.3},
 "lote_idx": [123456, ...], "umbrales_cm": [5, 20],
 "duraciones": [3, 24, 72], "P_mm": [25, 50, ...], "suelos": ["normal", "saturado"],
 "escenarios": {"P100_24h": {"P_mm": 100, "dur_h": 24, "suelo": "normal", "horas": 49, "lluvia_acum_mm": [...],
                              "ensamble": ["fabdem", "glo30", "ign30"], "url": "sim/P100_24h.bin.gz", "cert_url": "sim/P100_24h_cert.bin.gz"}},
 "clima": { ... copia de out/clima.json ... }}
```

- [ ] **Step 1: Tests**

```python
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
```

- [ ] **Step 2: Correr y ver que fallen**

Run: `$PY python -m pytest tests/test_websim.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'anega2.websim'`

- [ ] **Step 3: Implementar `anega2/websim.py`**

```python
"""Datos de la vista «Resumen» del visor: cuadros horarios reproyectados a EPSG:3857, certeza por píxel y
lote -> projects/<n>/web/sim/{<id>.bin.gz, <id>_cert.bin.gz, index.json}.

Cuadros: data/proc/rog/<id>_frames.npz (DEM primario) y data/proc/rog/ens/<id>__<dem>_frames.npz (ensamble).
Certeza (umbral u): media sobre los DEM disponibles de la fracción de la ventana 3×3 con lámina > u; uint8 0-100.
"""
from __future__ import annotations

import gzip
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio import features
from rasterio.warp import Resampling, reproject, transform_bounds
from scipy.ndimage import uniform_filter

from .common import CRS_WGS84
from .project import Project
from .rog import load_dem_window, scenario_specs

EPSG3857 = "EPSG:3857"
UMBRALES = [5, 20]


def grilla_3857(tr, crs, shape, lat: float) -> dict:
    rows, cols = shape
    b = transform_bounds(crs, EPSG3857, *rasterio.transform.array_bounds(rows, cols, tr))
    res = abs(tr.a) / math.cos(math.radians(lat))
    nc, nr = int(math.ceil((b[2] - b[0]) / res)), int(math.ceil((b[3] - b[1]) / res))
    t = Affine(res, 0, b[0], 0, -res, b[3])
    bb = (b[0], b[3] - nr * res, b[0] + nc * res, b[3])
    w, s, e, n = transform_bounds(EPSG3857, CRS_WGS84, *bb)
    return dict(transform=list(t)[:6], cols=nc, rows=nr, bounds_3857=list(bb), bounds_wgs84=[[s, w], [n, e]], res_m=res)


def a_3857(frames: np.ndarray, tr, crs, g: dict) -> np.ndarray:
    out = np.zeros((frames.shape[0], g["rows"], g["cols"]), np.uint8)
    for i in range(frames.shape[0]):
        reproject(frames[i], out[i], src_transform=tr, src_crs=crs, dst_transform=Affine(*g["transform"]), dst_crs=EPSG3857,
                  resampling=Resampling.nearest, src_nodata=None, dst_nodata=0)
    return out


def _ajustar(a: np.ndarray, shape) -> np.ndarray:
    out = np.zeros(shape, a.dtype); t, r, c = (min(x, y) for x, y in zip(a.shape, shape))
    out[:t, :r, :c] = a[:t, :r, :c]; return out


def certeza(frames_por_dem: list, umbral_cm: int) -> np.ndarray:
    shape = frames_por_dem[0].shape
    acc = np.zeros(shape, float)
    for f in frames_por_dem:
        acc += uniform_filter((_ajustar(f, shape) > umbral_cm).astype(float), size=(1, 3, 3), mode="constant")
    return np.round(100 * acc / len(frames_por_dem)).astype(np.uint8)


def lote_idx(lote_geom, crs, g: dict) -> list[int]:
    import geopandas as gpd
    geom = gpd.GeoSeries([lote_geom], crs=crs).to_crs(EPSG3857).iloc[0]
    m = features.rasterize([(geom, 1)], out_shape=(g["rows"], g["cols"]), transform=Affine(*g["transform"]), all_touched=True).astype(bool)
    return [int(i) for i in np.flatnonzero(m)]


def escribir_gz(path: Path, a: np.ndarray) -> None:
    path.write_bytes(gzip.compress(np.ascontiguousarray(a, np.uint8).tobytes(), compresslevel=6))


def run(p: Project) -> dict:
    rogd = p.data_proc / "rog"; out = p.web / "sim"; out.mkdir(parents=True, exist_ok=True)
    prim = json.load(open(p.out / "terrain_primary.json"))["primary"]
    aoi = p.load_aoi(); _, tr = load_dem_window(p, prim, aoi)
    lat = p.lot_centroid_wgs84()[1]
    specs = [s for s in scenario_specs(p.cfg["lluvia"]) if (rogd / f"{s['id']}_frames.npz").exists()]
    if not specs:
        print("  [aviso] no hay cuadros horarios (correr la fase lluvia): la vista Resumen no tendrá simulación"); return {}
    f0 = np.load(rogd / f"{specs[0]['id']}_frames.npz")["h_cm"]
    g = grilla_3857(tr, p.crs, f0.shape[1:], lat)
    ens = json.load(open(p.out / "rog_ensamble.json")) if (p.out / "rog_ensamble.json").exists() else {"dems": [], "ids": []}
    idx = dict(grid={k: g[k] for k in ("transform", "cols", "rows", "bounds_wgs84", "res_m")}, lote_idx=lote_idx(aoi["lote"], p.crs, g),
               umbrales_cm=UMBRALES, duraciones=sorted({s["dur_h"] for s in specs}), P_mm=sorted({s["P_mm"] for s in specs}),
               suelos=sorted({s["suelo"] for s in specs}), escenarios={})
    for s in specs:
        z = np.load(rogd / f"{s['id']}_frames.npz")
        fr = a_3857(z["h_cm"], tr, p.crs, g)
        por_dem = [fr]; dems = [prim]
        for dem in (ens["dems"] if s["id"] in ens["ids"] else []):
            q = rogd / "ens" / f"{s['id']}__{dem}_frames.npz"
            if q.exists():
                por_dem.append(a_3857(np.load(q)["h_cm"], tr, p.crs, g)); dems.append(dem)
        escribir_gz(out / f"{s['id']}.bin.gz", fr)
        escribir_gz(out / f"{s['id']}_cert.bin.gz", np.stack([certeza(por_dem, u) for u in UMBRALES]))
        idx["escenarios"][s["id"]] = dict(P_mm=s["P_mm"], dur_h=s["dur_h"], suelo=s["suelo"], horas=int(fr.shape[0]),
                                          lluvia_acum_mm=[round(float(v), 1) for v in z["lluvia_acum_mm"]], ensamble=dems,
                                          url=f"sim/{s['id']}.bin.gz", cert_url=f"sim/{s['id']}_cert.bin.gz")
    cl = p.out / "clima.json"
    idx["clima"] = json.load(open(cl)) if cl.exists() else {"disponible": False}
    json.dump(idx, open(out / "index.json", "w"), ensure_ascii=False)
    mb = sum(q.stat().st_size for q in out.glob("*")) / 1e6
    print(f"  vista Resumen: {len(specs)} escenarios, grilla {g['cols']}×{g['rows']} (3857, {g['res_m']:.1f} m), {mb:.0f} MB en {out}")
    return dict(escenarios=len(specs), mb=mb)
```

Al final de `webdata.run`, antes del `p.summary_line`, agregar:
```python
    from . import websim
    websim.run(p)
```

- [ ] **Step 4: Tests**

Run: `$PY python -m pytest tests -q`
Expected: todo pasa.

- [ ] **Step 5: Commit**

```bash
git add anega2/websim.py anega2/webdata.py tests/test_websim.py
git commit -m "web: cuadros horarios en 3857, certeza por vecindad y ensamble de DEM para la vista Resumen"
```

---

### Task 9: `veredicto.json` como contrato con el visor

**Files:**
- Modify: `anega2/report.py` (`build`, `run`)
- Modify: `anega2/webdata.py:329-345` (dejar de parsear el README)
- Test: `tests/test_report.py` (agregar)

**Interfaces:**
- Produces: `out/veredicto.json` (ya existe con `indicadores`, `veredicto`) suma `verdict_md` (texto de la sección Veredicto), `field_md` (qué chequear en campo), `etiqueta` (`"Riesgo bajo"`, `"Riesgo medio-bajo"`, `"Riesgo medio"`, `"Riesgo alto"`) y `frase_nivel` (una línea llana). `webdata` lo copia a `web/veredicto.json` y lo usa para `stats.verdict_md/field_md`.
  - `report.etiqueta(nivel: str) -> tuple[str, str]`.

- [ ] **Step 1: Test**

Agregar a `tests/test_report.py`:
```python
def test_etiqueta():
    assert report.etiqueta("MEDIO-BAJO") == ("Riesgo medio-bajo", "Con lluvias muy grandes puede juntar algo de agua.")
    assert report.etiqueta("ALTO")[0] == "Riesgo alto"
```

- [ ] **Step 2: Correr y ver que falle**

Run: `$PY python -m pytest tests/test_report.py -q`
Expected: FAIL — `AttributeError: ... 'etiqueta'`

- [ ] **Step 3: Implementar**

En `report.py`:
```python
FRASES_NIVEL = {"BAJO": "No se esperan problemas de agua con lluvias normales ni grandes.",
                "MEDIO-BAJO": "Con lluvias muy grandes puede juntar algo de agua.",
                "MEDIO": "Con lluvias grandes, parte del lote se anega por unas horas.",
                "ALTO": "Se anega con frecuencia o está en la zona que ocupa el agua del arroyo."}


def etiqueta(nivel: str) -> tuple[str, str]:
    return f"Riesgo {nivel.lower()}", FRASES_NIVEL.get(nivel, "")
```
En `build`, además de `md`, devolver en el dict: `verdict_md=_veredicto(ev, ind, R, p).strip()`, `field_md=_campo(ev, R, p).strip()`, `etiqueta=etiqueta(ev["global"])[0]`, `frase_nivel=etiqueta(ev["global"])[1]` (calcular `_veredicto` y `_campo` una vez y reutilizarlos en el f-string).

En `webdata.run`, reemplazar las líneas que leen `readme` y hacen `re.search(r"## Veredicto…")` / `re.search(r"## 5\. Qué chequear…")` por:
```python
    vj = json.load(open(out / "veredicto.json")) if (out / "veredicto.json").exists() else {}
    if vj:
        shutil.copy(out / "veredicto.json", web / "veredicto.json")
```
y en `stats` usar `verdict_md=vj.get("verdict_md", ""), field_md=vj.get("field_md", "")`.

- [ ] **Step 4: Tests + regenerar**

Run: `$PY python -m pytest tests -q && $PY anega2 run ejemplo-bajo-giles --fase informe web --si`
Expected: tests pasan; en el visor viejo la pestaña Veredicto muestra el mismo texto que antes.

- [ ] **Step 5: Commit**

```bash
git add anega2/report.py anega2/webdata.py tests/test_report.py
git commit -m "informe: veredicto.json con textos y etiqueta llana; el visor deja de parsear el README"
```

---

### Task 10: Paleta HAND sin azul y HAND con su error

**Files:**
- Create: `anega2/paletas.py`
- Modify: `anega2/terrain.py:340,377` (figuras), `anega2/webdata.py:216-218` (capa HAND), `anega2/defaults.yml` (`terreno.sigma_dem_m`)
- Test: `tests/test_paletas.py`

**Interfaces:**
- Produces (`anega2/paletas.py`):
  - `HAND_CLASES` — `[(0, 0.5, "#b71c1c", "menos de 0,5 m"), (0.5, 1, "#f4511e", "0,5 – 1 m"), (1, 2, "#ffb300", "1 – 2 m"), (2, 5, "#fff3c4", "2 – 5 m")]` (> 5 m sin color).
  - `hand_clase(a: np.ndarray) -> np.ndarray` — 0..3 por clase, NaN arriba de 5 m o nodata.
  - `hand_incertidumbre(hand_min: float, hand_min_por_dem: list[float], sigma_min: float) -> dict` — `{"sigma": σ, "p_lt05": %, "p_lt1": %}` con σ = máx(`sigma_min`, desvío muestral de `hand_min_por_dem`) y probabilidades normales.
- `webdata`: capa `hand` categórica con `HAND_CLASES`, **no visible por defecto** (`visible=False`); `stats.hand_incert` con el dict de arriba.

- [ ] **Step 1: Config**

En `anega2/defaults.yml` agregar:
```yaml
terreno:
  sigma_dem_m: 1.0             # error vertical típico del DEM para el HAND del lote (se usa el mayor entre esto y la dispersión entre DEM)
```

- [ ] **Step 2: Tests**

```python
import numpy as np
import pytest

from anega2 import paletas


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
```

- [ ] **Step 3: Correr y ver que fallen**

Run: `$PY python -m pytest tests/test_paletas.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'anega2.paletas'`

- [ ] **Step 4: Implementar `anega2/paletas.py`**

```python
"""Paletas compartidas (figuras, ficha y visor). Azul reservado para agua."""
from __future__ import annotations

import math

import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap

HAND_CLASES = [(0.0, 0.5, "#b71c1c", "menos de 0,5 m"), (0.5, 1.0, "#f4511e", "0,5 – 1 m"),
               (1.0, 2.0, "#ffb300", "1 – 2 m"), (2.0, 5.0, "#fff3c4", "2 – 5 m")]
HAND_CMAP = ListedColormap([c for _, _, c, _ in HAND_CLASES])
HAND_NORM = BoundaryNorm([lo for lo, _, _, _ in HAND_CLASES] + [HAND_CLASES[-1][1]], HAND_CMAP.N)


def hand_clase(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=float); out = np.full(a.shape, np.nan)
    for i, (lo, hi, _, _) in enumerate(HAND_CLASES):
        out[(a >= lo) & (a < hi)] = i
    return out


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def hand_incertidumbre(hand_min: float, hand_min_por_dem: list, sigma_min: float) -> dict:
    v = [x for x in hand_min_por_dem if x is not None and np.isfinite(x)]
    sd = float(np.std(v, ddof=1)) if len(v) > 1 else 0.0
    s = max(float(sigma_min), sd)
    return dict(sigma=round(s, 2), p_lt05=round(100 * _phi((0.5 - hand_min) / s), 1), p_lt1=round(100 * _phi((1.0 - hand_min) / s), 1))
```

- [ ] **Step 5: Usar la paleta**

`anega2/common.py` (`plot_map`): agregar el parámetro `norm=None` al final de la firma y borrar la línea `    norm = None` del cuerpo (el `if discrete_labels:` sigue pisándolo cuando corresponde). `imshow` ya recibe `norm=norm`.

`anega2/terrain.py`: import `from .paletas import HAND_CMAP, HAND_NORM`. En el dict `layers` (línea ~340) la entrada `"hand"` pasa a `(f"hand_{k0}.tif", "HAND · altura sobre el drenaje más cercano (m) · sin color: > 5 m", HAND_CMAP, None, None)`; en el `plot_map` del loop agregar `norm=HAND_NORM if key == "hand" else None`. En la figura `10_terrain_hand_hidro.png` (línea ~377) reemplazar `cmap="RdYlBu", vmin=0, vmax=8` por `cmap=HAND_CMAP, norm=HAND_NORM`.

`anega2/webdata.py:217`: reemplazar la capa HAND por
```python
        B.raster("hand", "HAND · altura sobre el drenaje (m)", "Terreno", hand_src, transform_fn=hand_clase, visible=False,
                 categorical={i: (lab, col) for i, (_, _, col, lab) in enumerate(HAND_CLASES)},
                 description="Cuántos metros tendría que subir el agua desde el drenaje para llegar. Rojo = bajo; sin color = más de 5 m.")
```
(import `from .paletas import HAND_CLASES, hand_clase, hand_incertidumbre`). En `stats` agregar:
```python
        hand_incert=hand_incertidumbre(float(kv.get("hand_min_lote", "nan")),
                                       [float(v) for v in ts.loc[ts["variable"] == "hand_min_lote"].iloc[0, 1:]] if len(ts) and (ts["variable"] == "hand_min_lote").any() else [],
                                       float(p.cfg.get("terreno", {}).get("sigma_dem_m", 1.0))) if kv.get("hand_min_lote") is not None else None,
```
Asegurar que la capa visible por defecto en «Terreno» ya no sea HAND (ninguna raster visible por defecto en la vista técnica salvo la lámina del escenario elegido).

- [ ] **Step 6: Tests y regenerar**

Run: `$PY python -m pytest tests -q && $PY anega2 run ejemplo-bajo-giles --fase terreno web --si`
Expected: tests pasan; `out/10_terrain_hand.png` sin azul.

- [ ] **Step 7: Commit**

```bash
git add anega2/paletas.py anega2/terrain.py anega2/common.py anega2/webdata.py anega2/defaults.yml tests/test_paletas.py
git commit -m "HAND en clases cálidas (cortes de rules.yml, sin azul) y HAND del lote con su error"
```

---

### Task 11: Ficha — paleta HAND, banda de error y escenarios de la ficha

**Precondición:** `git status --short anega2/ficha.py` vacío (cambios del autor commiteados; ver Task 0). Si no, frenar y preguntar.

**Files:**
- Modify: `anega2/ficha.py:93` (`self.rog`), `:96` (`self.years`), `:329-341` (`_lam_hand`), `_lam_corredor` (perfil)

**Interfaces:**
- Consumes: `paletas.HAND_CLASES`, `paletas.hand_incertidumbre`, `rog.ficha_ids`, `report.eventos_analizados` (Tasks 4, 5, 10).

- [ ] **Step 1: Escenarios y eventos**

En `_Ctx.__init__`: después de leer `self.rog`, filtrar
```python
        if self.rog is not None:
            self.rog = self.rog[self.rog["escenario"].isin(ficha_ids(p.cfg["lluvia"]))].reset_index(drop=True)
```
y reemplazar la línea de `self.years` por
```python
        from .report import eventos_analizados
        sar_csv = p.out / "sar_stats.csv"
        self.years = sorted({e[:4] for e in eventos_analizados({"sar": pd.read_csv(sar_csv) if sar_csv.exists() else None})})
```
Guardar además `self.hinc = hand_incertidumbre(...)` con los mismos argumentos que en `webdata` (valores de `terrain_stats.csv`).

- [ ] **Step 2: Paleta en `_lam_hand`**

Reemplazar
```python
    hs = _classes(ax, hand, trh, [0, 0.5, 1, 2, 3], ["#b71c1c", "#e53935", "#fb8c00", "#fdd835"])
    for h_, lab in zip(hs, ["menos de 0,5 m (drenaje y su borde)", "0,5 – 1 m (muy bajo)", "1 – 2 m (bajo)", "2 – 3 m (medio)"]):
        h_.set_label(lab)
    hs.append(patches.Patch(fc="none", ec="#999", label="sin color: más de 3 m (alto)"))
```
por
```python
    hs = _classes(ax, hand, trh, [lo for lo, _, _, _ in HAND_CLASES] + [HAND_CLASES[-1][1]], [c for _, _, c, _ in HAND_CLASES])
    for h_, (_, _, _, lab) in zip(hs, HAND_CLASES):
        h_.set_label(lab)
    hs.append(patches.Patch(fc="none", ec="#999", label="sin color: más de 5 m (alto)"))
```
y en `cap` agregar al final: `f" Con el error típico del modelo de terreno (± {fnum(ctx.hinc['sigma'])} m), la probabilidad de que el lote esté a menos de 1 m del drenaje es de ~{fnum(ctx.hinc['p_lt1'], 0)} %."`

- [ ] **Step 3: Banda en el perfil**

En `_lam_corredor`, después de `axp.axhline(zmin_lote, …)`:
```python
    sg = ctx.hinc["sigma"]
    axp.axhspan(zmin_lote - sg, zmin_lote + sg, color=C_LOTE, alpha=0.07, zorder=1)
    axp.text(x[-1] - 5, zmin_lote + sg, f"± {fnum(sg)} m (error típico del DEM) ", ha="right", va="bottom", fontsize=7.2, color=C_LOTE)
```

- [ ] **Step 4: Regenerar y revisar**

Run: `$PY anega2 run ejemplo-bajo-giles --fase ficha --si`
Expected: PDF generado; abrir `out/ficha/04_altura_sobre_el_drenaje.png` y `05_drenaje_mas_cercano.png` con Read y verificar paleta cálida, leyenda «2 – 5 m», banda rosada en el perfil; la lámina de lluvias tiene 6 filas.

- [ ] **Step 5: Commit**

```bash
git add anega2/ficha.py
git commit -m "ficha: paleta HAND nueva, banda de error del DEM en el perfil y sólo los escenarios de la ficha"
```

---

### Task 12: `webapp/lib.js` — funciones puras con tests de node

**Files:**
- Create: `webapp/lib.js`, `webapp/test/lib.test.js`

**Interfaces:**
- Produces (objeto global `Lib` en el navegador; `module.exports` en node):
  - `pickNeighbors(Ps: number[], P: number) -> {lo: number, hi: number, w: number}` — `Ps` ordenado; `P` se acota a `[Ps[0], Ps.at(-1)]`; si coincide con un valor, `lo = hi = P`, `w = 0`.
  - `lerp(a: Uint8Array, b: Uint8Array, w: number) -> Uint8Array` — redondeo.
  - `loteSerie(frames: Uint8Array[], loteIdx: number[], u: number) -> {hmax: number[], pct: number[], horasConAgua: number, horaPico: number}`.
  - `nivelCerteza(c: number) -> 'probable'|'posible'|'poco'|null` (≥70, ≥30, ≥5, resto null).
  - `retornoAnios(mm: number, g: {mu, beta}) -> number` (Infinity si fuera de rango).
  - `durTexto(dur) -> 'un chaparrón de 3 h'|'un día de lluvia'|'un temporal de 3 días'`.
  - `frase(o) -> string`, con `o = {P, dur, hmaxCm, pct, horasConAgua, nivel, Tera5, Tchirps, maxHistorico, certezaSoloVecindad, soloUnModelo}`.
  - `fmt(v, d)` — número con coma decimal.

- [ ] **Step 1: Tests**

`webapp/test/lib.test.js`:
```js
const test = require('node:test');
const assert = require('node:assert');
const Lib = require('../lib.js');

test('pickNeighbors interior y exacto', () => {
  assert.deepStrictEqual(Lib.pickNeighbors([25, 50, 75], 60), { lo: 50, hi: 75, w: 0.4 });
  assert.deepStrictEqual(Lib.pickNeighbors([25, 50, 75], 50), { lo: 50, hi: 50, w: 0 });
});
test('pickNeighbors extremos', () => {
  assert.deepStrictEqual(Lib.pickNeighbors([25, 50], 10), { lo: 25, hi: 25, w: 0 });
  assert.deepStrictEqual(Lib.pickNeighbors([25, 50], 300), { lo: 50, hi: 50, w: 0 });
});
test('lerp redondea', () => {
  assert.deepStrictEqual(Array.from(Lib.lerp(new Uint8Array([0, 10]), new Uint8Array([10, 20]), 0.25)), [3, 13]);
});
test('loteSerie', () => {
  const f = [new Uint8Array([0, 0, 0]), new Uint8Array([8, 2, 99]), new Uint8Array([30, 6, 0])];
  const s = Lib.loteSerie(f, [0, 1], 5);
  assert.deepStrictEqual(s.hmax, [0, 8, 30]);
  assert.deepStrictEqual(s.pct, [0, 50, 100]);
  assert.strictEqual(s.horasConAgua, 2); assert.strictEqual(s.horaPico, 2);
});
test('nivelCerteza', () => {
  assert.deepStrictEqual([80, 70, 50, 10, 4].map(Lib.nivelCerteza), ['probable', 'probable', 'posible', 'poco', null]);
});
test('retornoAnios', () => {
  const g = { mu: 80, beta: 20 };
  assert.ok(Math.abs(Lib.retornoAnios(80 - 20 * Math.log(-Math.log(0.9)), g) - 10) < 1e-6);
  assert.strictEqual(Lib.retornoAnios(1e5, g), Infinity);
});
test('frase con agua', () => {
  const s = Lib.frase({ P: 120, dur: 24, hmaxCm: 15, pct: 33, horasConAgua: 6, nivel: 'probable', Tera5: 10.4, Tchirps: 12 });
  assert.strictEqual(s, 'Con 120 mm en un día de lluvia: hasta 15 cm en un tercio del lote (probable), con agua ~6 h. Una lluvia así pasa cada ~10 años.');
});
test('frase sin agua', () => {
  const s = Lib.frase({ P: 25, dur: 3, hmaxCm: 3, pct: 0, horasConAgua: 0, nivel: null, Tera5: 1.2 });
  assert.strictEqual(s, 'Con 25 mm en un chaparrón de 3 h: el lote no junta agua (menos de 5 cm). Una lluvia así pasa casi todos los años.');
});
test('frase fuera de registro y fuentes que difieren', () => {
  assert.match(Lib.frase({ P: 250, dur: 24, hmaxCm: 40, pct: 90, horasConAgua: 20, nivel: 'posible', Tera5: Infinity, maxHistorico: 180, desde: 1940 }),
    /Más de lo que llovió en cualquier día desde 1940\.$/);
  assert.match(Lib.frase({ P: 150, dur: 24, hmaxCm: 20, pct: 50, horasConAgua: 8, nivel: 'probable', Tera5: 10, Tchirps: 30 }),
    /pasa cada 10 a 30 años según la fuente\.$/);
});
test('frase con un solo modelo', () => {
  assert.match(Lib.frase({ P: 100, dur: 24, hmaxCm: 8, pct: 10, horasConAgua: 2, nivel: 'poco', soloUnModelo: true, Tera5: 5 }),
    /\(incierto: sólo 1 de 3 modelos de terreno\)/);
});
```

- [ ] **Step 2: Correr y ver que fallen**

Run: `node --test webapp/test/`
Expected: FAIL — `Cannot find module '../lib.js'`

- [ ] **Step 3: Implementar `webapp/lib.js`**

```js
/* anega2 · funciones puras del visor (interpolación, estadísticas del lote, certeza, frase). Sin DOM: testeadas con node --test. */
(function (root) {
  const fmt = (v, d = 0) => Number(v).toLocaleString('es-AR', { maximumFractionDigits: d, minimumFractionDigits: 0 });

  function pickNeighbors(Ps, P) {
    const p = Math.min(Math.max(P, Ps[0]), Ps[Ps.length - 1]);
    for (let i = 0; i < Ps.length; i++) {
      if (Ps[i] === p) return { lo: p, hi: p, w: 0 };
      if (Ps[i] > p) { const lo = Ps[i - 1], hi = Ps[i]; return { lo, hi, w: Math.round(((p - lo) / (hi - lo)) * 1e6) / 1e6 }; }
    }
    return { lo: p, hi: p, w: 0 };
  }

  function lerp(a, b, w) {
    const out = new Uint8Array(a.length);
    for (let i = 0; i < a.length; i++) out[i] = Math.round(a[i] + (b[i] - a[i]) * w);
    return out;
  }

  function loteSerie(frames, loteIdx, u) {
    const hmax = [], pct = [];
    for (const f of frames) {
      let m = 0, n = 0;
      for (const i of loteIdx) { const v = f[i]; if (v > m) m = v; if (v > u) n++; }
      hmax.push(m); pct.push(Math.round((1000 * n) / loteIdx.length) / 10);
    }
    const horasConAgua = hmax.filter(v => v > u).length;
    return { hmax, pct, horasConAgua, horaPico: hmax.indexOf(Math.max(...hmax)) };
  }

  const nivelCerteza = c => (c >= 70 ? 'probable' : c >= 30 ? 'posible' : c >= 5 ? 'poco' : null);

  function retornoAnios(mm, g) {
    const pExc = 1 - Math.exp(-Math.exp(-(mm - g.mu) / g.beta));
    return pExc <= 0 ? Infinity : 1 / pExc;
  }

  const durTexto = dur => (dur <= 3 ? 'un chaparrón de 3 h' : dur <= 24 ? 'un día de lluvia' : 'un temporal de 3 días');
  const NIVEL_TXT = { probable: 'probable', posible: 'posible', poco: 'poco probable' };

  function fraccion(pct) {
    if (pct >= 95) return 'todo el lote';
    if (pct >= 60) return 'la mayor parte del lote';
    if (pct >= 40) return 'la mitad del lote';
    if (pct >= 25) return 'un tercio del lote';
    if (pct >= 10) return 'una parte del lote';
    return 'una esquina del lote';
  }

  function frecuencia(o) {
    const unDia = o.dur <= 24 ? 'día' : 'temporal';
    if (!Number.isFinite(o.Tera5)) return o.maxHistorico != null ? `Más de lo que llovió en cualquier ${unDia} desde ${o.desde || 1940}.` : '';
    if (o.Tera5 < 1.5) return 'Una lluvia así pasa casi todos los años.';
    const a = Math.round(o.Tera5);
    if (o.Tchirps && Number.isFinite(o.Tchirps) && (o.Tchirps / o.Tera5 > 2 || o.Tera5 / o.Tchirps > 2)) {
      const [x, y] = [a, Math.round(o.Tchirps)].sort((m, n) => m - n);
      return `Una lluvia así pasa cada ${x} a ${y} años según la fuente.`;
    }
    return `Una lluvia así pasa cada ~${a} años.`;
  }

  function frase(o) {
    const cab = `Con ${fmt(o.P)} mm en ${durTexto(o.dur)}: `;
    let cuerpo;
    if (o.hmaxCm < 5) cuerpo = 'el lote no junta agua (menos de 5 cm).';
    else {
      const cert = o.soloUnModelo ? ' (incierto: sólo 1 de 3 modelos de terreno)' : o.nivel ? ` (${NIVEL_TXT[o.nivel]}${o.certezaSoloVecindad ? ', certeza sólo por vecindad' : ''})` : '';
      cuerpo = `hasta ${fmt(o.hmaxCm)} cm en ${fraccion(o.pct)}${cert}, con agua ~${fmt(o.horasConAgua)} h.`;
    }
    const fr = frecuencia(o);
    return cab + cuerpo + (fr ? ' ' + fr : '');
  }

  const Lib = { fmt, pickNeighbors, lerp, loteSerie, nivelCerteza, retornoAnios, durTexto, frase };
  if (typeof module !== 'undefined' && module.exports) module.exports = Lib; else root.Lib = Lib;
})(this);
```

- [ ] **Step 4: Correr**

Run: `node --test webapp/test/`
Expected: `# pass 10`, `# fail 0`.

- [ ] **Step 5: Commit**

```bash
git add webapp/lib.js webapp/test/lib.test.js
git commit -m "visor: funciones puras de la vista Resumen (interpolación, certeza, frase) con tests de node"
```

---

### Task 13: Visor — separar la vista técnica y agregar la vista «Resumen»

**Files:**
- Modify: `webapp/index.html` (estructura de dos vistas, scripts nuevos)
- Rename: `webapp/app.js` → `webapp/tecnico.js` (con `git mv`), y crear un `webapp/app.js` nuevo de arranque
- Create: `webapp/sim.js`, `webapp/resumen.js`
- Modify: `webapp/style.css`

**Interfaces:**
- Consumes: `web/sim/index.json`, `web/sim/*.bin.gz` (Task 8), `web/veredicto.json` (Task 9), `web/stats.json` (`hand_incert`, Task 10), `Lib` (Task 12).
- Produces:
  - `Sim` (global, `sim.js`): `Sim.load(base) -> Promise<index>`, `Sim.frames(id) -> Promise<{h: Uint8Array[], c5: Uint8Array[], c20: Uint8Array[]}>` (caché en memoria), `Sim.mezcla(P, dur, suelo) -> Promise<{h, c5, c20, lo, hi, w}>`, `Sim.pintar(canvas, h, c, maxCm) -> void`, `Sim.celda(latlng) -> index | null`.
  - `Resumen.init(map, S)`, `Resumen.show()`, `Resumen.hide()`.
  - `Tecnico.init(map, S)`, `Tecnico.show()`, `Tecnico.hide()` — el código actual de `app.js` (paneles, capas, click) envuelto; `show/hide` agregan/quitan del mapa las capas que tenía prendidas.
  - `app.js`: `S` compartido (`S.base`, `S.manifest`, `S.stats`, `S.grid`, `S.figures`, `S.veredicto`), mapa único (`S.map`), carga del proyecto, selector de vista.

- [ ] **Step 1: `git mv webapp/app.js webapp/tecnico.js`** y en `tecnico.js`:
  - Quitar `loadProjects`, `init()` y el `init().catch(...)` final (pasan a `app.js`), y `initMap` (el mapa lo crea `app.js`; `tecnico.js` recibe `S.map`).
  - Envolver el resto en `const Tecnico = (() => { … return { init, show, hide }; })();`. El código interno sigue usando el `S` global (declarado con `const` en `app.js`, que se evalúa antes de que se llame a `init`). `async function init()` hace lo que hacía el viejo `init` desde `initTabs()` hasta los `onclick` (sin el `fetch` de datos ni `initMap`, que pasan a `app.js`), y
```js
  let prendidas = [];
  function hide() { prendidas = Object.values(S.layers).filter(o => o.on).map(o => o.def.id); prendidas.forEach(id => hide_(id, false)); S.map.off('click', onMapClick); $('#legend').innerHTML = ''; }
  function show() { prendidas.forEach(id => show_(id, false)); S.map.on('click', onMapClick); refresh(); }
```
  (renombrar las funciones internas `show`/`hide` de capas a `show_`/`hide_`).
  - En `renderVerdict`, la tarjeta de HAND usa `S.stats.hand_incert`: valor `${fmt(k.hand_min_lote)} – ${fmt(k.hand_max_lote)} m · ± ${fmt(hi.sigma)} m` y debajo `prob. de < 1 m: ${fmt(hi.p_lt1, 0)} %`.

- [ ] **Step 2: `webapp/index.html`** — dentro de `<main>`, el `<aside id="panel">` actual pasa a `id="panel-tecnico"` con `hidden`; agregar antes otro aside:

```html
  <aside id="panel-resumen">
    <section class="card-r" id="r-lluvia">
      <div class="label">1 · Con esta lluvia</div>
      <div id="r-riesgo" class="riesgo"></div>
      <p id="r-frase" class="frase">cargando…</p>
      <div class="pills" id="r-dur"></div>
      <div class="pills" id="r-suelo"></div>
      <label class="row">Lluvia <input id="r-mm" type="range" min="25" max="250" step="5" value="100"><b id="r-mm-v"></b></label>
      <div class="pills" id="r-umbral"></div>
      <div class="chart-wrap small"><canvas id="r-curva"></canvas></div>
    </section>
    <section class="card-r" id="r-historia">
      <div class="label">2 · ¿Pasó alguna vez?</div>
      <div class="chart-wrap small"><canvas id="r-maximos"></canvas></div>
      <p id="r-veces" class="muted"></p>
      <div id="r-eventos" class="list"></div>
      <div id="r-evento" class="evento"></div>
    </section>
    <a href="#" id="r-tecnico" class="card-r link">3 · Detalle técnico (HAND, capas, tablas) ›</a>
  </aside>
```
y debajo del mapa (dentro de `#map`'s contenedor) una barra de hora:
```html
<div id="r-hora" class="hora"><button id="r-play" title="Reproducir">▶</button><input id="r-t" type="range" min="0" max="48" step="1" value="0"><span id="r-t-v"></span></div>
```
En el header, reemplazar el control de opacidad por un selector de vista: `<div class="pills" id="vista"><button data-v="resumen" class="on">Resumen</button><button data-v="tecnico">Detalle técnico</button></div>` (el slider de opacidad se mueve adentro de `#panel-tecnico`, primera línea de la pestaña Capas).
Scripts al final, en este orden: leaflet, chart.js, proj4, `lib.js`, `sim.js`, `tecnico.js`, `resumen.js`, `app.js`.

- [ ] **Step 3: `webapp/sim.js`**

```js
/* anega2 · datos de simulación de la vista Resumen: descarga, descompresión, caché, interpolación y pintado. */
const Sim = (() => {
  let base = '', idx = null; const cache = new Map();
  async function gunzip(url) {
    const r = await fetch(base + url); if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    return new Uint8Array(await new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
  }
  async function load(b) { base = b; const r = await fetch(base + 'sim/index.json'); if (!r.ok) return null; idx = await r.json(); return idx; }
  const n = () => idx.grid.rows * idx.grid.cols;
  function partir(buf, k) { const out = []; for (let i = 0; i < k; i++) out.push(buf.subarray(i * n(), (i + 1) * n())); return out; }
  async function frames(id) {
    if (!cache.has(id)) cache.set(id, (async () => {
      const e = idx.escenarios[id]; const [h, c] = await Promise.all([gunzip(e.url), gunzip(e.cert_url)]);
      const cc = partir(c, 2 * e.horas);
      return { h: partir(h, e.horas), c5: cc.slice(0, e.horas), c20: cc.slice(e.horas) };
    })());
    return cache.get(id);
  }
  const idDe = (P, dur, suelo) => `P${String(P).padStart(3, '0')}_${dur}h${suelo === 'saturado' ? '_sat' : ''}`;
  async function mezcla(P, dur, suelo) {
    const { lo, hi, w } = Lib.pickNeighbors(idx.P_mm, P);
    const [a, b] = await Promise.all([frames(idDe(lo, dur, suelo)), frames(idDe(hi, dur, suelo))]);
    const mix = k => a[k].map((f, t) => (w === 0 ? f : Lib.lerp(f, b[k][t], w)));
    return { h: mix('h'), c5: mix('c5'), c20: mix('c20'), lo, hi, w, ensamble: idx.escenarios[idDe(lo, dur, suelo)].ensamble };
  }
  // azules por profundidad; alpha por nivel de certeza; < 2 cm transparente
  const STOPS = [[2, [198, 219, 239]], [5, [107, 174, 214]], [20, [33, 113, 181]], [50, [8, 69, 148]], [100, [8, 48, 107]]];
  function color(cm) { let c = STOPS[0][1]; for (const [v, col] of STOPS) if (cm >= v) c = col; return c; }
  const ALPHA = { probable: 242, posible: 140, poco: 51 };
  function pintar(canvas, h, cert) {
    const { cols, rows } = idx.grid; canvas.width = cols; canvas.height = rows;
    const ctx = canvas.getContext('2d'); const img = ctx.createImageData(cols, rows); const d = img.data;
    for (let i = 0; i < h.length; i++) {
      const v = h[i]; if (v < 2) continue; const nv = Lib.nivelCerteza(cert[i]); if (!nv) continue;
      const [r, g, b] = color(v); d[4 * i] = r; d[4 * i + 1] = g; d[4 * i + 2] = b; d[4 * i + 3] = ALPHA[nv];
    }
    ctx.putImageData(img, 0, 0);
  }
  function celda(latlng) {
    const p = L.CRS.EPSG3857.project(latlng); const [a, , c, , e, f] = idx.grid.transform;
    const col = Math.floor((p.x - c) / a), row = Math.floor((p.y - f) / e);
    return row < 0 || col < 0 || row >= idx.grid.rows || col >= idx.grid.cols ? null : row * idx.grid.cols + col;
  }
  return { load, frames, mezcla, pintar, celda, idDe, color, get idx() { return idx; } };
})();
```

- [ ] **Step 4: `webapp/resumen.js`**

Estado: `R = {P, dur: 24, suelo: 'normal', u: 5, t, mezcla, playing}`. Responsabilidades (una función cada una):
```js
const Resumen = (() => {
  let map, S, R = { dur: 24, suelo: 'normal', u: 5, t: 0, P: 100 }, overlay = null, canvas = document.createElement('canvas'), grilla = null, charts = {}, s1layer = null;
  const $ = s => document.querySelector(s);
  const DUR = [[3, 'Chaparrón 3 h'], [24, 'Día de lluvia'], [72, 'Temporal 3 días']];
  const SUELO = [['normal', 'Suelo normal'], ['saturado', 'Saturado']];
  const UMB = [[5, 'más de 5 cm'], [20, 'más de 20 cm']];

  function pills(el, opts, cur, fn) {
    el.innerHTML = ''; opts.forEach(([v, lab]) => { const b = document.createElement('button'); b.textContent = lab; b.className = v === cur ? 'on' : ''; b.onclick = () => fn(v); el.appendChild(b); });
  }
  const clima = () => Sim.idx.clima || { disponible: false };
  function gumbel(fuente) { const c = clima(); return c.disponible && c.gumbel[fuente] ? c.gumbel[fuente][String(R.dur)] : null; }
  function pInicial() {                                  // tormenta de ~10 años (ERA5, 24 h), redondeada a 5 mm y acotada
    const g = gumbel('era5'); if (!g) return 100;
    const mm = g.mu - g.beta * Math.log(-Math.log(0.9)); return Math.min(250, Math.max(25, Math.round(mm / 5) * 5));
  }
  async function actualizar(mantenerHora = true) {
    R.mezcla = await Sim.mezcla(R.P, R.dur, R.suelo);
    const H = R.mezcla.h.length; $('#r-t').max = H - 1;
    const serie = Lib.loteSerie(R.mezcla.h, Sim.idx.lote_idx, R.u);
    if (!mantenerHora || R.t >= H) R.t = serie.horaPico;
    $('#r-t').value = R.t; pintarHora(); frase(serie); curva(serie); maximos();
  }
  function pintarHora() {
    const t = R.t, cert = R.u === 5 ? R.mezcla.c5[t] : R.mezcla.c20[t];
    Sim.pintar(canvas, R.mezcla.h[t], cert);
    canvas.toBlob(b => { const url = URL.createObjectURL(b); if (!overlay) overlay = L.imageOverlay(url, Sim.idx.grid.bounds_wgs84, { pane: 'rasters' }).addTo(map); else { URL.revokeObjectURL(overlay._url); overlay.setUrl(url); } });
    const e = Sim.idx.escenarios[Sim.idDe(R.mezcla.lo, R.dur, R.suelo)];
    const acum = e.lluvia_acum_mm[Math.min(t, e.lluvia_acum_mm.length - 1)] * (R.P / R.mezcla.lo);
    $('#r-t-v').textContent = `hora ${t} · llovieron ${Lib.fmt(Math.min(acum, R.P))} mm`;
    if (charts.curva) charts.curva.draw();
  }
  function frase(serie) {
    const loteCert = Sim.idx.lote_idx.map(i => (R.u === 5 ? R.mezcla.c5 : R.mezcla.c20)[serie.horaPico][i]).filter((_, k) => R.mezcla.h[serie.horaPico][Sim.idx.lote_idx[k]] > R.u).sort((a, b) => a - b);
    const med = loteCert.length ? loteCert[Math.floor(loteCert.length / 2)] : 0;
    const ens = R.mezcla.ensamble || [];
    const ge = gumbel('era5'), gc = gumbel('chirps');
    const maxH = clima().disponible && clima().maximos.era5 && clima().maximos.era5[String(R.dur)] ? Math.max(...clima().maximos.era5[String(R.dur)].map(r => r[1])) : null;
    $('#r-frase').textContent = Lib.frase({ P: R.P, dur: R.dur, hmaxCm: serie.hmax[serie.horaPico], pct: serie.pct[serie.horaPico], horasConAgua: serie.horasConAgua,
      nivel: Lib.nivelCerteza(med), certezaSoloVecindad: ens.length < 2, soloUnModelo: ens.length >= 3 && med < 34,
      Tera5: ge ? Lib.retornoAnios(R.P, ge) : NaN, Tchirps: gc ? Lib.retornoAnios(R.P, gc) : null, maxHistorico: maxH, desde: clima().fuentes?.era5?.desde?.slice(0, 4) });
  }
  const horaActual = { id: 'horaActual', afterDraw(c) {
    const x = c.scales.x.getPixelForValue(R.t), { top, bottom } = c.chartArea, g = c.ctx;
    g.save(); g.strokeStyle = '#e65100'; g.lineWidth = 1.5; g.beginPath(); g.moveTo(x, top); g.lineTo(x, bottom); g.stroke(); g.restore(); } };
  function curva(serie) {
    const e = Sim.idx.escenarios[Sim.idDe(R.mezcla.lo, R.dur, R.suelo)], k = R.P / R.mezcla.lo;
    const lluvia = serie.hmax.map((_, i) => (i === 0 || i >= e.lluvia_acum_mm.length ? 0 : (e.lluvia_acum_mm[i] - e.lluvia_acum_mm[i - 1]) * k));
    if (charts.curva) charts.curva.destroy();
    charts.curva = new Chart($('#r-curva'), { data: { labels: serie.hmax.map((_, i) => i), datasets: [
      { type: 'bar', label: 'lluvia (mm por hora)', data: lluvia, backgroundColor: '#90caf9', yAxisID: 'y1' },
      { type: 'line', label: 'agua en el lote (cm)', data: serie.hmax, borderColor: '#0d47a1', pointRadius: 0, yAxisID: 'y' }] },
      options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { labels: { boxWidth: 10, font: { size: 10 } } } },
        scales: { x: { title: { display: true, text: 'hora' }, ticks: { maxTicksLimit: 8 } }, y: { beginAtZero: true, title: { display: true, text: 'cm' } },
                  y1: { position: 'right', beginAtZero: true, grid: { drawOnChartArea: false }, title: { display: true, text: 'mm/h' } } } },
      plugins: [horaActual] });
  }
  const DUR_LAB = { 3: '3 h', 24: '24 h', 72: '72 h' };
  function maximos() {
    const c = clima(), el = $('#r-veces');
    if (charts.max) { charts.max.destroy(); charts.max = null; }
    if (!c.disponible) { el.textContent = `Sin datos de lluvia histórica: corré anega2 run ${S.project} --fase clima.`; return; }
    const e5 = (c.maximos.era5 || {})[String(R.dur)] || [], ch = (c.maximos.chirps || {})[String(R.dur)] || [];
    if (!e5.length) { el.textContent = `ERA5 no tiene máximos de ${DUR_LAB[R.dur]}.`; return; }
    const anios = e5.map(r => r[0]), chMap = Object.fromEntries(ch.map(r => [r[0], r[1]])), sup = e5.filter(r => r[1] >= R.P);
    charts.max = new Chart($('#r-maximos'), { data: { labels: anios, datasets: [
      { type: 'bar', label: 'ERA5', data: e5.map(r => r[1]), backgroundColor: e5.map(r => (r[1] >= R.P ? '#e65100' : '#b0bec5')) },
      { type: 'line', label: 'CHIRPS', data: anios.map(a => chMap[a] ?? null), showLine: false, pointRadius: 2, borderColor: '#6d4c41', backgroundColor: '#6d4c41' },
      { type: 'line', label: `${R.P} mm`, data: anios.map(() => R.P), borderColor: '#1565c0', borderDash: [5, 4], pointRadius: 0 }] },
      options: { responsive: true, maintainAspectRatio: false, animation: false,
        plugins: { legend: { labels: { boxWidth: 10, font: { size: 10 } } }, title: { display: true, text: `Lluvia máxima en ${DUR_LAB[R.dur]} de cada año` } },
        scales: { x: { ticks: { maxTicksLimit: 8 } }, y: { beginAtZero: true, title: { display: true, text: 'mm' } } } } });
    el.textContent = sup.length
      ? `${R.P} mm en ${DUR_LAB[R.dur]} se superó ${sup.length} ${sup.length === 1 ? 'vez' : 'veces'} desde ${anios[0]} (ERA5): ${sup.slice(-4).map(r => r[0]).join(', ')}${sup.length > 4 ? '…' : ''}.`
      : `Desde ${anios[0]} nunca llovió ${R.P} mm en ${DUR_LAB[R.dur]} (ERA5).`;
  }
  function eventos() {
    const c = clima(), box = $('#r-eventos'); box.innerHTML = '';
    if (!c.disponible) return;
    c.eventos.historicos.forEach(ev => {
      const b = document.createElement('button'); b.className = 'ev'; b.textContent = `${ev.fecha} · ${Lib.fmt(ev.era5_72)} mm en 72 h`;
      b.onclick = () => detalleEvento(ev); box.appendChild(b);
    });
  }
  function radar(ev) {
    const t = S.stats.sar || { columns: [], rows: [] }, ix = k => t.columns.indexOf(k);
    const filas = t.rows.filter(r => r[ix('evento')] === ev.id);
    if (!filas.length) return ev.fecha < '2014-10-03' ? 'No había radar Sentinel-1 en esa fecha.' : 'Esa fecha no se analizó con radar.';
    if (filas.some(r => r[ix('escena')] === 'SIN PASADA A TIEMPO')) return 'El radar no pasó a tiempo: no se puede saber si hubo agua.';
    const post = filas.find(r => r[ix('momento')] === 'post'); if (!post) return 'No hay escena del radar después de la tormenta.';
    const d = post[ix('dias_desde_evento')], pct = post[ix('pct_agua_lote')];
    return pct > 0 ? `El radar pasó ${d} días después y vio agua en el ${Lib.fmt(pct)} % del lote.` : `El radar pasó ${d} días después y no vio agua en el lote.`;
  }
  async function detalleEvento(ev) {
    const P = Math.min(250, Math.max(25, Math.round(ev.era5_72 / 5) * 5));
    const m = await Sim.mezcla(P, 72, 'normal'), s = Lib.loteSerie(m.h, Sim.idx.lote_idx, 5), hp = s.horaPico;
    const modelo = s.hmax[hp] < 5 ? 'el modelo no pone agua en el lote' : `el modelo pone hasta ${s.hmax[hp]} cm en el ${Lib.fmt(s.pct[hp])} % del lote`;
    const box = $('#r-evento');
    box.innerHTML = `<b>${ev.fecha}</b>: ${Lib.fmt(ev.era5_72)} mm en 72 h según ERA5` + (ev.chirps_72 != null ? `, ${Lib.fmt(ev.chirps_72)} mm según CHIRPS` : '')
      + `. Con esa lluvia ${modelo}. ${radar(ev)}`;
    const sc = (S.manifest.scenes || []).find(x => x.evento === ev.id && x.momento === 'post');
    if (sc && sc.w_layer && S.layers[sc.w_layer]) {
      const b = document.createElement('button'); b.textContent = 'Ver en el mapa lo que vio el radar';
      b.onclick = () => { if (s1layer) map.removeLayer(s1layer); s1layer = S.layers[sc.w_layer].layer.addTo(map); };
      box.appendChild(b);
    }
  }
  function leyenda() {
    const sw = (css, lab) => `<div class="cls"><span class="swatch" style="background:${css}"></span>${lab}</div>`;
    $('#legend').innerHTML = '<div class="item"><b>Agua</b>'
      + [[2, '2 cm'], [5, '5 cm · cubre el pie'], [20, '20 cm · media pierna'], [50, '50 cm · rodilla']].map(([v, l]) => sw(`rgb(${Sim.color(v).join(',')})`, l)).join('')
      + sw('rgba(33,113,181,.95)', 'probable') + sw('rgba(33,113,181,.55)', 'posible') + sw('rgba(33,113,181,.2)', 'poco probable') + '</div>';
  }
  function click(e) {
    const i = Sim.celda(e.latlng); if (i == null || !R.mezcla) return;
    const col = R.mezcla.h.map(f => f[i]); const cert = (R.u === 5 ? R.mezcla.c5 : R.mezcla.c20)[R.t][i];
    const hrs = col.filter(v => v > R.u).length; const nv = Lib.nivelCerteza(cert);
    L.popup().setLatLng(e.latlng).setContent(col[R.t] < 2 && Math.max(...col) < 2 ? 'Acá no se junta agua con esta lluvia.' :
      `Acá: <b>${col[R.t]} cm</b> a la hora ${R.t} · máximo ${Math.max(...col)} cm · con agua ${hrs} h${nv ? ` · certeza: ${nv === 'poco' ? 'poco probable' : nv}` : ''}`).openOn(map);
  }
  function grillaPixeles() {                           // a zoom ≥ 17: celdas de ~30 m en ±300 m del lote
    const g = Sim.idx.grid, [a, , c, , e, f] = g.transform, i0 = Sim.idx.lote_idx[0];
    const r0 = Math.floor(i0 / g.cols), c0 = i0 % g.cols, k = Math.ceil(300 / g.res_m);
    const un = (x, y) => L.CRS.EPSG3857.unproject(L.point(x, y)), lines = [];
    for (let j = c0 - k; j <= c0 + k + 1; j++) lines.push([un(c + j * a, f + (r0 - k) * e), un(c + j * a, f + (r0 + k + 1) * e)]);
    for (let i = r0 - k; i <= r0 + k + 1; i++) lines.push([un(c + (c0 - k) * a, f + i * e), un(c + (c0 + k + 1) * a, f + i * e)]);
    grilla = L.polyline(lines, { color: '#fff', weight: 0.6, opacity: 0.45, interactive: false });
    const upd = () => { if (map.getZoom() >= 17 && !$('#panel-resumen').hidden) grilla.addTo(map); else map.removeLayer(grilla); };
    map.on('zoomend', upd); upd();
  }
  let timer = null;
  function play() { if (timer) { clearInterval(timer); timer = null; $('#r-play').textContent = '▶'; return; }
    $('#r-play').textContent = '❚❚'; timer = setInterval(() => { R.t = (R.t + 1) % R.mezcla.h.length; $('#r-t').value = R.t; pintarHora(); }, 250); }
  async function init(m, s) {
    map = m; S = s; const idx = await Sim.load(S.base); if (!idx) return false;
    R.P = pInicial(); $('#r-mm').value = R.P; $('#r-mm-v').textContent = `${R.P} mm`;
    const v = S.veredicto || {}; $('#r-riesgo').textContent = v.etiqueta ? `${v.etiqueta} · ${v.frase_nivel}` : '';
    const redraw = () => { pills($('#r-dur'), DUR, R.dur, x => { R.dur = x; redraw(); actualizar(false); }); pills($('#r-suelo'), SUELO, R.suelo, x => { R.suelo = x; redraw(); actualizar(); }); pills($('#r-umbral'), UMB, R.u, x => { R.u = x; redraw(); actualizar(); }); };
    redraw();
    $('#r-mm').oninput = e => { R.P = +e.target.value; $('#r-mm-v').textContent = `${R.P} mm`; actualizar(); };
    $('#r-t').oninput = e => { R.t = +e.target.value; pintarHora(); };
    $('#r-play').onclick = play; eventos(); grillaPixeles();
    await actualizar(false); return true;
  }
  function show() { $('#panel-resumen').hidden = false; $('#r-hora').hidden = false; if (overlay) overlay.addTo(map); map.on('click', click); leyenda(); map.fire('zoomend'); }
  function hide() { $('#panel-resumen').hidden = true; $('#r-hora').hidden = true; if (overlay) map.removeLayer(overlay); if (s1layer) map.removeLayer(s1layer);
    if (grilla) map.removeLayer(grilla); map.off('click', click); if (timer) play(); }
  return { init, show, hide };
})();
```
Además, `maximos()` se vuelve a llamar al cambiar el tipo de tormenta y el deslizador de lluvia (ya incluido en `actualizar`).

- [ ] **Step 5: `webapp/app.js` nuevo**

```js
/* anega2 · arranque del visor: proyecto, mapa único y cambio de vista (Resumen / Detalle técnico). */
const S = { map: null, manifest: null, stats: null, grid: null, figures: [], layers: {}, opacity: 0.8, scene: null, scenario: null, charts: {}, project: null, base: '', projects: [], veredicto: null };
const PROJECTS_INDEX = '../projects/index.json';
// loadProjects() e initMap(center): se MUEVEN tal cual desde tecnico.js (Step 1), con un solo cambio:
// initMap ya no hace S.map.on('click', onMapClick) (cada vista registra su click en show()).
function vista(v) {
  document.querySelectorAll('#vista button').forEach(b => b.classList.toggle('on', b.dataset.v === v));
  document.getElementById('panel-tecnico').hidden = v !== 'tecnico';
  if (v === 'tecnico') { Resumen.hide(); Tecnico.show(); } else { Tecnico.hide(); Resumen.show(); }
}
async function init() {
  await loadProjects();
  const get = u => fetch(S.base + u).then(r => (r.ok ? r.json() : null));
  [S.manifest, S.stats, S.grid, S.figures, S.veredicto] = await Promise.all(['layers.json', 'stats.json', 'grid.json', 'figures.json', 'veredicto.json'].map(get));
  if (!S.manifest) throw new Error('layers.json: falta (corré anega2 run <proyecto> --fase web)');
  initMap(S.manifest.center);
  await Tecnico.init(S.map, S);
  const hayResumen = await Resumen.init(S.map, S);
  document.querySelectorAll('#vista button').forEach(b => (b.onclick = () => vista(b.dataset.v)));
  document.getElementById('r-tecnico').onclick = e => { e.preventDefault(); vista('tecnico'); };
  if (!hayResumen) { document.querySelector('#vista [data-v="resumen"]').disabled = true; document.querySelector('#vista [data-v="resumen"]').title = 'falta correr la fase lluvia y web'; }
  vista(hayResumen ? 'resumen' : 'tecnico');
  S.map.fitBounds(S.layers.lote.layer.getBounds().pad(4));
}
init().catch(e => { console.error(e); document.getElementById('subtitle').textContent = 'Error cargando datos: ' + e.message; });
```

- [ ] **Step 6: `webapp/style.css`** — estilos de `.card-r`, `.pills button(.on)`, `.frase` (17px, 600), `.riesgo` (chip con color por nivel: BAJO verde, MEDIO-BAJO ámbar, MEDIO naranja, ALTO rojo), `.hora` (barra fija abajo del mapa), `.chart-wrap.small` (altura 150px). Mantener la paleta y tipografía actuales; `#panel-resumen` con el mismo ancho que el panel técnico.

- [ ] **Step 7: Generar datos y probar en Chrome**

Run: `$PY anega2 run ejemplo-bajo-giles --fase web --si && $PY anega2 serve --no-abrir &`
Luego, con las herramientas de Chrome (skill `claude-in-chrome`): abrir `http://localhost:8000/webapp/?project=ejemplo-bajo-giles` y verificar, con capturas:
  1. Abre en Resumen, con la frase, el nivel de riesgo y el agua en el mapa (sin HAND).
  2. Mover el deslizador de lluvia a 25, 137 y 250 cambia el mapa y la frase; tipo de tormenta y suelo también.
  3. ▶ anima; el deslizador de hora muestra «hora N · llovieron X mm».
  4. Umbral 20 cm reduce la mancha.
  5. Click en el lote → popup «Acá: …».
  6. Tarjeta 2: gráfico de máximos, texto «se superó N veces», click en un evento muestra fecha, mm y radar.
  7. Zoom 17 → grilla de píxeles.
  8. «Detalle técnico» → pestañas viejas funcionando, HAND en clases cálidas, tarjeta HAND con «± 1 m».
  9. `read_console_messages` sin errores.

- [ ] **Step 8: Commit**

```bash
git add webapp/
git commit -m "visor: vista Resumen «¿Dónde hay agua?» (lluvia, hora, certeza, historia) y vista técnica separada"
```

---

### Task 14: Corrida completa del ejemplo, README y limpieza

**Files:**
- Modify: `README.md`, `README.en.md`, `SOURCES.md`, `.gitignore`, `docs/visor.jpg`
- Regenerate: `projects/ejemplo-bajo-giles/{out,web}/`

- [ ] **Step 1: Corrida de punta a punta**

Run: `$PY anega2 run ejemplo-bajo-giles --si 2>&1 | tee /tmp/ejemplo.log`
Expected: todas las fases OK. Verificar:
  - `out/rog_stats.csv`: 60 filas; `P100_24h` `hmax_lote_m` entre 0,06 y 0,10 (antes 0,08).
  - Todos los `data/proc/rog/*_meta.json` con `|balance.error_pct| < 1`.
  - `out/clima.json` con `disponible: true`.
  - `web/sim/` y su tamaño (anotarlo).

- [ ] **Step 2: `.gitignore`**

El ejemplo versiona `web/`; `web/sim/` puede pesar 50-200 MB. Agregar `projects/ejemplo-*/web/sim/` a `.gitignore` y documentar en el README que se regenera con `anega2 run ejemplo-bajo-giles --fase lluvia web`.

- [ ] **Step 3: README (es y en)**

- Fases: agregar `clima` entre `agua` y `sar`.
- «Qué produce»: `clima_*.csv/md`, `clima.json`, `veredicto.json`, `web/sim/`.
- «Cómo decide»: punto 3 (Histórico) menciona ERA5 + CHIRPS y eventos automáticos; punto 4 (Lluvia) la grilla de 60 escenarios, cuadros horarios y ensamble de DEM; nuevo punto «Certeza».
- Tiempos: CHIRPS ~25 min la primera vez; lluvia: el tiempo medido en la Task 7.
- Visor: vista Resumen (qué muestra) y Detalle técnico.
- Limitaciones: quitar «escenarios sin recurrencia»; agregar «período de retorno aproximado (ERA5 28 km subestima tormentas convectivas; CHIRPS 5 km)».
- Instalación: `pip install -e .` ahora funciona (pyproject); tests: `python -m pytest` y `node --test webapp/test/`.
- Nueva captura `docs/visor.jpg` de la vista Resumen (desde Chrome).

- [ ] **Step 4: `SOURCES.md`**

Agregar ERA5 (Copernicus Climate Change Service, vía Open-Meteo, CC BY 4.0, atribución «Contains modified Copernicus Climate Change Service information») y CHIRPS v2.0 (Climate Hazards Center UCSB, dominio público; cita Funk et al. 2015).

- [ ] **Step 5: Tests completos**

Run: `$PY python -m pytest -q && node --test webapp/test/`
Expected: todo pasa.

- [ ] **Step 6: Commit**

```bash
git add README.md README.en.md SOURCES.md .gitignore docs/visor.jpg projects/ejemplo-bajo-giles
git commit -m "Ejemplo regenerado con clima, grilla horaria y vista Resumen; README y fuentes actualizados"
```
