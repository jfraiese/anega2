"""Informe automático (out/README.md): números clave, veredicto por reglas (rules.yml) y chequeos de campo.

Lee las tablas producidas por terrain/water/sar/rog. Las fases ausentes se marcan como pendientes.
`run()` también escribe out/veredicto.json (indicadores, veredicto, verdict_md, field_md, etiqueta,
frase_nivel), que webdata.py copia a web/veredicto.json y usa para stats.verdict_md/field_md.
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .project import Project

RULES = yaml.safe_load((Path(__file__).parent / "rules.yml").read_text())
NIVELES = RULES["niveles"]


def f(v, d=2):
    """Número con coma decimal (castellano); '—' si falta."""
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    s = f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s.rstrip("0").rstrip(",") if d > 0 else s


def _num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def eventos_analizados(R: dict) -> list[str]:
    s = R.get("sar")
    if s is None or "evento" not in s:
        return []
    return list(dict.fromkeys(str(e).split("_")[0] for e in s["evento"] if e != "referencia_seca"))


# ------------------------------------------------------------------ carga de resultados
def load_results(p: Project) -> dict:
    o = p.out
    R: dict = {"primary": None, "terrain": None, "key": {}, "deps": None, "jrc": None, "jrc_extra": "", "sar": None, "rog": None, "rog_params": {}, "clima": None}
    if (o / "terrain_primary.json").exists():
        R["primary"] = json.load(open(o / "terrain_primary.json"))
    if (o / "terrain_stats.csv").exists():
        t = pd.read_csv(o / "terrain_stats.csv")
        R["terrain"] = t
        pc = [c for c in t.columns if "(primario)" in c]
        if pc:
            R["key"] = dict(zip(t["variable"], t[pc[0]]))
            R["primary_col"] = pc[0]
    if (o / "terrain_depresiones_aoi.csv").exists():
        R["deps"] = pd.read_csv(o / "terrain_depresiones_aoi.csv")
    if (o / "jrc_stats.csv").exists():
        R["jrc"] = pd.read_csv(o / "jrc_stats.csv")
        md = o / "jrc_stats.md"
        if md.exists():
            for line in md.read_text().splitlines():
                if line.startswith("Distancia del lote"):
                    R["jrc_extra"] = line.strip()
    if (o / "sar_stats.csv").exists():
        R["sar"] = pd.read_csv(o / "sar_stats.csv")
    if (o / "rog_stats.csv").exists():
        R["rog"] = pd.read_csv(o / "rog_stats.csv")
    if (o / "rog_params.json").exists():
        R["rog_params"] = json.load(open(o / "rog_params.json"))
    R["clima"] = json.load(open(o / "clima.json")) if (o / "clima.json").exists() else None
    return R


def indicators(R: dict, p: Project) -> dict:
    """Valores que evalúan las reglas (None si la fase falta)."""
    k = R["key"]
    ind = {
        "depresion_prof_max_m": _num(k.get("sink_depth_max_lote_m")),
        "cuenca_aportante_ha": _num(k.get("cuenca_celda_mas_baja_ha")),
        "hand_min_m": _num(k.get("hand_min_lote")),
        "hmax_lote_100mm_cm": None, "pct_lote_gt5cm_100mm": None, "pct_aoi_gt20cm_150mm": None,
        "jrc_occ_lote_pct": None, "sar_agua_lote_pct_max": None, "sar_agua_aoi_pct_max": None,
    }
    if R["jrc"] is not None and len(R["jrc"]):
        row = R["jrc"].iloc[0]
        ind["jrc_occ_lote_pct"] = _num(row.get("occ>0 %"))
    if R["sar"] is not None and len(R["sar"]):
        s = R["sar"]
        ev = s[s["evento"] != "referencia_seca"] if "evento" in s else s
        ind["sar_agua_lote_pct_max"] = _num(ev["pct_agua_lote"].max()) if "pct_agua_lote" in ev and len(ev) else None
        col = "pct_agua_500m" if "pct_agua_500m" in ev else ("pct_agua_aoi" if "pct_agua_aoi" in ev else None)
        ind["sar_agua_aoi_pct_max"] = _num(ev[col].max()) if col and len(ev) else None
    if R["rog"] is not None and len(R["rog"]):
        r = R["rog"]
        def row_for(P, sat=False):
            m = (r["P_mm"] == P) & (r["dur_h"] == 24) & (r["escenario"].str.endswith("_sat") == sat)
            return r[m].iloc[0] if m.any() else None
        r100 = row_for(100); r150 = row_for(150)
        if r100 is not None:
            ind["hmax_lote_100mm_cm"] = _num(r100["hmax_lote_m"]) * 100 if _num(r100["hmax_lote_m"]) is not None else None
            ind["pct_lote_gt5cm_100mm"] = _num(r100["pct_lote_gt5cm"])
        if r150 is not None:
            col = "pct_500m_gt20cm" if "pct_500m_gt20cm" in r else ("pct_aoi_gt20cm" if "pct_aoi_gt20cm" in r else None)
            ind["pct_aoi_gt20cm_150mm"] = _num(r150[col]) if col else None
    return ind


def evaluate(ind: dict) -> dict:
    """{'lluvia_local': (nivel, razones), 'desborde': (...), 'global': nivel}."""
    out = {}
    for comp in ("lluvia_local", "desborde"):
        lvl = 0; razones = []; faltan = []
        for name, rule in RULES[comp].items():
            v = ind.get(name)
            if v is None:
                faltan.append(rule["descr"]); continue
            hit = None
            for niv, thr in rule["umbrales"].items():
                ok = v >= thr if rule.get("dir", "ge") == "ge" else v < thr
                if ok and NIVELES.index(niv) > (NIVELES.index(hit) if hit else -1):
                    hit = niv
            if hit:
                razones.append((hit, rule["descr"], v))
                lvl = max(lvl, NIVELES.index(hit))
        out[comp] = dict(nivel=NIVELES[lvl], razones=razones, faltan=faltan)
    out["global"] = NIVELES[max(NIVELES.index(out["lluvia_local"]["nivel"]), NIVELES.index(out["desborde"]["nivel"]))]
    return out


# ------------------------------------------------------------------ texto
def _tabla_terreno(R, p) -> str:
    k = R["key"]
    if not k:
        return "_Fase de terreno pendiente._\n"
    aoi = f"{p.aoi_m:.0f} m"
    rows = [
        ("Cota (m snm)", f"{f(k.get('z_min_lote'))} – {f(k.get('z_max_lote'))} (media {f(k.get('z_mean_lote'))})", f"{f(k.get('z_min_aoi'))} – {f(k.get('z_max_aoi'))}"),
        ("HAND: altura sobre el drenaje más cercano (m)", f"**{f(k.get('hand_min_lote'))} – {f(k.get('hand_max_lote'))}** (media {f(k.get('hand_mean_lote'))})",
         f"media {f(k.get('hand_mean_aoi'))} · {f(k.get('pct_aoi_hand_le1'), 0)} % ≤ 1 m · {f(k.get('pct_aoi_hand_le2'), 0)} % ≤ 2 m"),
        ("Pendiente media", f"{f(k.get('slope_mean_lote_pct'))} %", f"{f(k.get('slope_mean_aoi_pct'))} %"),
        ("Dirección de escurrimiento (D8 dominante / salida del camino de flujo)", f"{k.get('d8_dominante_lote', '—')} / {k.get('direccion_salida_flowpath', '—')}", "—"),
        ("Distancia al drenaje ≥ 0,5 km²", f"**{f(k.get('dist_euclid_red_05km2_m'), 0)} m** en línea recta · {f(k.get('dist_flujo_red_05km2_m'), 0)} m por camino de flujo", "—"),
        ("Cota del cauce más cercano / salto vertical desde el punto más bajo del lote", f"{f(k.get('z_cauce_mas_cercano'))} m / {f(k.get('salto_lote_min_vs_cauce_m'))} m (línea recta) · {f(k.get('hand_min_lote'))} m por camino de flujo", "—"),
        ("Depresión cerrada en el lote", "**Sí**, prof. máx " + f(k.get('sink_depth_max_lote_m')) + " m" if str(k.get("lote_intersecta_depresion")) == "True" else "**No**",
         _deps_text(R)),
        ("Cuenca aportante", f"**{f(k.get('cuenca_celda_mas_baja_ha'))} ha** (celda más baja) · {f(k.get('cuenca_todo_el_lote_ha'))} ha (todo el lote)", "—"),
    ]
    s = f"| Variable (DEM primario, píxeles de 30 m; el lote toca {k.get('n_celdas_lote', '?')}) | Lote | Buffer {aoi} |\n|---|---|---|\n"
    s += "\n".join(f"| {a} | {b} | {c} |" for a, b, c in rows) + "\n"
    return s


def _deps_text(R) -> str:
    d = R["deps"]
    if d is None or len(d) == 0:
        return "ninguna"
    big = d.iloc[0]
    return f"{len(d)} depresiones; la mayor {f(big['area_m2']/1e4, 1)} ha / {f(big['vol_m3'], 0)} m³, prof. máx {f(d['prof_max_m'].max())} m" + (" (todas ≤ 10 cm: dentro del ruido del DEM)" if d["prof_max_m"].max() <= 0.10 else "")


def _dem_text(R) -> str:
    if R["terrain"] is None:
        return ""
    t = R["terrain"]; pc = R.get("primary_col", "")
    labels = dict(zip(t["variable"], t[pc])) if pc else {}
    others = [c for c in t.columns if c not in ("variable", pc)]
    crit = (R["primary"] or {}).get("criterio", "")
    s = f"DEM primario: **{labels.get('dem_label', pc)}** (criterio: {crit}). "
    if others:
        s += "Otros DEM evaluados (control de sensibilidad): " + ", ".join(str(t.loc[t['variable'] == 'dem_label', c].iloc[0]) for c in others) + ". "
    hm = _num(labels.get("hand_min_lote")); sl = _num(labels.get("slope_mean_lote_pct"))
    for c in others:
        h2 = _num(t.loc[t["variable"] == "hand_min_lote", c].iloc[0]); s2 = _num(t.loc[t["variable"] == "slope_mean_lote_pct", c].iloc[0])
        if hm is not None and h2 is not None and (h2 - hm > 2.5 or (s2 or 0) > 3 * max(sl or 0.3, 0.3)):
            s += (f"Con {t.loc[t['variable'] == 'dem_label', c].iloc[0]} el lote aparece mucho más alto (HAND {f(h2)} m, pendiente {f(s2)} %): "
                  "es la firma de copas de árboles o construcciones en un modelo de superficie, no del terreno. ")
    return s


def _tabla_jrc(R, p) -> str:
    j = R["jrc"]
    if j is None:
        return "_Fase JRC pendiente._\n"
    s = "| Zona | píxeles | agua alguna vez (occ > 0) | occ > 10 % | occ > 50 % | occ máx |\n|---|---|---|---|---|---|\n"
    for _, r in j.iterrows():
        s += f"| {r['zona']} | {int(r['n_pix'])} | {f(r['occ>0 %'])} % | {f(r['occ>10 %'])} % | {f(r['occ>50 %'])} % | {r['occ max']} |\n"
    if R["jrc_extra"]:
        s += "\n" + R["jrc_extra"] + "\n"
    return s


def _tabla_sar(R, p) -> str:
    s_ = R["sar"]
    if s_ is None:
        return "_Fase Sentinel-1 pendiente._\n"
    aoi = f"{p.aoi_m:.0f} m"
    col500 = "pct_agua_500m" if "pct_agua_500m" in s_ else "pct_agua_aoi"
    colc = "pct_500m_caida_3dB" if "pct_500m_caida_3dB" in s_ else "pct_aoi_caida_3dB"
    s = f"| Evento | Escena (días respecto del evento) | Agua en lote / {aoi} / {p.hidro_m/1000:.0f} km | Entorno con caída > 3 dB vs. referencia seca |\n|---|---|---|---|\n"
    for _, r in s_.iterrows():
        if r.get("escena") == "SIN PASADA A TIEMPO":
            s += f"| {str(r['evento']).replace('_', ' ')} | **sin pasada a tiempo** (no se puede saber) | — | — |\n"; continue
        if r.get("escena") == "SIN COBERTURA" or pd.isna(r.get("fecha")):
            s += f"| {str(r['evento']).replace('_', ' ')} | **sin cobertura Sentinel-1** | — | — |\n"; continue
        dd = _num(r.get("dias_desde_evento"))
        esc = f"{r['fecha']}" + (f" ({'+' if dd > 0 else ''}{int(dd)})" if dd is not None else "")
        cai = f(r.get(colc), 1) if r['evento'] != 'referencia_seca' else '—'
        s += (f"| {str(r['evento']).replace('_', ' ')} | {esc} | {f(r['pct_agua_lote'], 1)} / {f(r[col500], 1)} / {f(r['pct_agua_10km'] if 'pct_agua_10km' in r else r.get('pct_agua_hidro'), 2)} % "
              f"| {cai}{' %' if cai != '—' else ''} |\n")
    return s


def _tabla_rog(R, p) -> str:
    r = R["rog"]
    if r is None:
        return "_Fase de simulación pendiente._\n", ""
    aoi = f"{p.aoi_m:.0f} m"
    c5 = "pct_500m_gt5cm" if "pct_500m_gt5cm" in r else "pct_aoi_gt5cm"; c20 = "pct_500m_gt20cm" if "pct_500m_gt20cm" in r else "pct_aoi_gt20cm"
    hm5 = "hmax_500m_m" if "hmax_500m_m" in r else "hmax_aoi_m"
    s = f"| Escenario | Infiltra (mm) | Lote: h máx (cm) | Lote: h media (cm) | Lote: % > 5 cm | Lote: % > 20 cm | Lote: horas > 5 cm | {aoi}: % > 5 cm | {aoi}: % > 20 cm | {aoi}: h máx (cm) |\n|---|---|---|---|---|---|---|---|---|---|\n"
    effect = "| Lluvia | Efecto en el lote | Efecto en el entorno |\n|---|---|---|\n"
    for _, x in r.iterrows():
        lab = f"{int(x['P_mm'])} mm / {x['dur_h']:g} h" + (f" · suelo saturado (Ks {f(x['Ks_mm_h'], 0)})" if str(x["escenario"]).endswith("_sat") else "")
        s += (f"| {lab} | {f(x['infil_media_mm'], 0)} | {f(x['hmax_lote_m']*100, 0)} | {f(x['hmedia_lote_m']*100, 0)} | {f(x['pct_lote_gt5cm'], 0)} | {f(x['pct_lote_gt20cm'], 0)} | "
              f"{f(x['dur_max_lote_h'], 1)} | {f(x[c5], 0)} | {f(x[c20], 0)} | {f(x[hm5]*100, 0)} |\n")
        h = x["hmax_lote_m"] * 100
        el = ("nada" if h < 2 else f"lámina de {f(h, 0)} cm en el {f(x['pct_lote_gt5cm'], 0)} % del lote durante {f(x['dur_max_lote_h'], 1)} h"
              + ("" if x["pct_lote_gt20cm"] == 0 else f"; {f(x['pct_lote_gt20cm'], 0)} % con más de 20 cm"))
        ee = ("nada" if x[c5] < 1 else f"{f(x[c5], 0)} % con > 5 cm" + ("" if x[c20] < 0.5 else f", {f(x[c20], 0)} % con > 20 cm"))
        effect += f"| {lab} | {el} | {ee} |\n"
    return s, effect


def _veredicto(ev: dict, ind: dict, R: dict, p: Project) -> str:
    k = R["key"]; aoi = f"{p.aoi_m:.0f} m"
    def razones(comp):
        rs = ev[comp]["razones"]
        if not rs:
            return "ninguna regla disparada"
        return "; ".join(f"{d} = {f(v)} → {n}" for n, d, v in rs)
    L = ev["lluvia_local"]["nivel"]; D = ev["desborde"]["nivel"]; G = ev["global"]
    s = f"**Riesgo {G} de anegamiento para el lote** (heurística a 30 m, ver reglas al final), con esta composición:\n\n"
    # lluvia local
    s += f"- **Anegamiento por lluvia local (agua que cae sobre el lote o le llega de arriba): {L}.** "
    if k:
        dep = str(k.get("lote_intersecta_depresion")) == "True"
        s += ("El lote " + ("**tiene una depresión cerrada** de " + f(k.get('sink_depth_max_lote_m')) + " m de profundidad máxima" if dep else "no tiene depresión cerrada") +
              f", su cuenca aportante es de {f(k.get('cuenca_celda_mas_baja_ha'))} ha (celda más baja) a {f(k.get('cuenca_todo_el_lote_ha'))} ha (todo el lote) y "
              f"escurre hacia {k.get('direccion_salida_flowpath', '—')} con pendiente media {f(k.get('slope_mean_lote_pct'))} %. ")
    if ind["hmax_lote_100mm_cm"] is not None:
        s += (f"En la simulación, con 100 mm en 24 h la lámina máxima en el lote es de {f(ind['hmax_lote_100mm_cm'], 0)} cm "
              f"({f(ind['pct_lote_gt5cm_100mm'], 0)} % del lote con más de 5 cm). ")
    s += f"Reglas: {razones('lluvia_local')}.\n"
    # desborde
    s += f"- **Desborde del drenaje (el agua sube desde el arroyo o el bajo): {D}.** "
    if k:
        s += (f"El drenaje ≥ 0,5 km² más cercano está a **{f(k.get('dist_euclid_red_05km2_m'), 0)} m** y el punto más bajo del lote queda "
              f"**{f(k.get('hand_min_lote'))} m por encima del cauce por camino de flujo (HAND {f(k.get('hand_min_lote'))}–{f(k.get('hand_max_lote'))} m)**; "
              f"el {f(k.get('pct_aoi_hand_le1'), 0)} % del entorno de {aoi} está a menos de 1 m sobre el drenaje y el {f(k.get('pct_aoi_hand_le2'), 0)} % a menos de 2 m. ")
    if ind["jrc_occ_lote_pct"] is not None:
        s += ("Landsat 1984-2021 " + ("**registró agua sobre el lote** en el " + f(ind['jrc_occ_lote_pct'], 1) + " % de sus píxeles. " if ind["jrc_occ_lote_pct"] > 0 else "nunca registró agua sobre el lote. "))
    if ind["sar_agua_lote_pct_max"] is not None:
        s += ("Sentinel-1 " + (f"**detectó agua en hasta el {f(ind['sar_agua_lote_pct_max'], 0)} % del lote** en algún evento. " if ind["sar_agua_lote_pct_max"] > 0
                                else f"no detectó agua abierta sobre el lote en ninguna escena (máximo en el entorno: {f(ind['sar_agua_aoi_pct_max'], 1)} %). "))
    if ind["pct_aoi_gt20cm_150mm"] is not None:
        s += f"Con 150 mm en 24 h simulados, el {f(ind['pct_aoi_gt20cm_150mm'], 0)} % del entorno supera los 20 cm. "
    s += f"Reglas: {razones('desborde')}.\n"
    falt = ev["lluvia_local"]["faltan"] + ev["desborde"]["faltan"]
    if falt:
        s += "- **Indicadores sin datos** (fase pendiente): " + "; ".join(falt) + ".\n"
    cl = R.get("clima") or {}
    if cl.get("disponible") and cl["gumbel"].get("era5") and "24" in cl["gumbel"]["era5"]:
        from .clima import gumbel_T
        t_e = gumbel_T(cl["gumbel"]["era5"]["24"], 100)
        g_c = (cl["gumbel"].get("chirps") or {}).get("24")
        s += (f"- **Frecuencia**: 100 mm en 24 h ocurre en promedio cada {f(t_e, 0)} años según ERA5"
              + (f" (cada {f(gumbel_T(g_c, 100), 0)} según CHIRPS)" if g_c else "") + ".\n")
    s += ("- **Limitación principal**: la topografía disponible es de 30 m de píxel, con ruido vertical de décimas de metro y sin "
          "microrrelieve (zanjas, terraplenes, alcantarillas). A escala de lote la diferencia entre anegarse o no está en "
          "decenas de centímetros que el DEM no resuelve. **El veredicto es un diagnóstico regional que hay que confirmar en campo.**\n")
    return s


def _campo(ev: dict, R: dict, p: Project) -> str:
    k = R["key"]
    hand = f(k.get("hand_min_lote")) if k else "—"; dist = f(k.get("dist_euclid_red_05km2_m"), 0) if k else "—"
    return f"""1. **Nivelar el lote contra el drenaje**: con nivel óptico o GPS RTK, medir la cota del punto más bajo del lote y la del
   fondo y la barranca del cauce más cercano ({dist} m). El DEM dice ≈ {hand} m de desnivel por camino de flujo; si en campo es
   claramente menor, el riesgo de desborde sube un nivel; si es mayor, baja.
2. **Alcantarillas y terraplenes**: rutas, caminos y vías entre el lote y el drenaje cortan la planicie. Ver diámetro y estado de
   las alcantarillas y si algún terraplén actúa como dique del lado del lote.
3. **Marcas de crecida y testimonio de vecinos**: preguntar por los eventos analizados ({', '.join(eventos_analizados(R)) or 'las lluvias grandes recientes'})
   y por la napa (si en años húmedos el agua "brota"). Buscar marcas en postes, alambrados y troncos.
4. **Napa y suelo**: en época húmeda, un pozo de 1-1,5 m para ver la profundidad de la napa; en la llanura pampeana el anegamiento
   por napa alta es tan frecuente como el desborde.
5. **Microrrelieve**: recorrer el lote y el entorno tras una lluvia fuerte para ver dónde se junta agua (el DEM no ve depresiones
   menores que un píxel ni zanjas).
6. **Cota de piso**: si se construye, elevar el piso al menos 0,5 m sobre el terreno natural (y por encima de la cota de crecida
   que surja del punto 1) cubre casi todo el rango de incertidumbre de este análisis.
"""


FRASES_NIVEL = {"BAJO": "No se esperan problemas de agua con lluvias normales ni grandes.",
                "MEDIO-BAJO": "Con lluvias muy grandes puede juntar algo de agua.",
                "MEDIO": "Con lluvias grandes, parte del lote se anega por unas horas.",
                "ALTO": "Se anega con frecuencia o está en la zona que ocupa el agua del arroyo."}


def etiqueta(nivel: str) -> tuple[str, str]:
    return f"Riesgo {nivel.lower()}", FRASES_NIVEL.get(nivel, "")


def _reglas_md() -> str:
    s = "| Componente | Indicador | Umbrales |\n|---|---|---|\n"
    for comp in ("lluvia_local", "desborde"):
        for name, rule in RULES[comp].items():
            op = "≥" if rule.get("dir", "ge") == "ge" else "<"
            s += f"| {comp.replace('_', ' ')} | {rule['descr']} | " + ", ".join(f"{op} {v} → {n}" for n, v in rule["umbrales"].items()) + " |\n"
    return s


def build(p: Project) -> tuple[str, dict]:
    R = load_results(p); ind = indicators(R, p); ev = evaluate(ind)
    lon, lat = p.lot_centroid_wgs84()
    aoi = f"{p.aoi_m:.0f} m"
    rp = R["rog_params"]; prim = (R["primary"] or {}).get("primary", "—")
    rog_tab, rog_eff = _tabla_rog(R, p)
    ev_ids = eventos_analizados(R) or ["ninguno"]
    veredicto_md = _veredicto(ev, ind, R, p)
    campo_md = _campo(ev, R, p)
    md = f"""# Riesgo de anegamiento — {p.titulo} · interpretación

**Polígono**: {f(p.load_aoi()['lote'].area, 0)} m², centroide {lat:.6f}, {lon:.6f} (WGS84), CRS de trabajo {p.crs} ({p.crs_descr}).
Fecha del análisis: {date.today().isoformat()} · generado por anega2 (informe automático por reglas; ver sección 6).
Buffers: área de interés {aoi}, análisis hidrológico {p.hidro_m/1000:.0f} km.

---

## Veredicto

{veredicto_md}
---

## 1. Dónde está el lote en el relieve (terreno)

{_dem_text(R)}

{_tabla_terreno(R, p)}
**Cómo leerlo**: HAND es cuántos metros tendría que subir el agua desde el drenaje más cercano (por el camino que sigue el
agua) para llegar a cada punto; HAND bajo = bajo del valle. "Cuenca aportante" pequeña significa que el lote no recibe
escurrimiento de otros lados. Figuras `10_terrain_*.png`; tabla completa con todos los DEM en `terrain_stats.md`.

## 2. Historial de agua superficial

**Landsat 1984-2021 (JRC Global Surface Water v1.4, 30 m)**

{_tabla_jrc(R, p)}
Landsat no ve agua bajo árboles ni agua que dure menos de unos días entre pasadas. Figuras `20_jrc_*.png`.

**Sentinel-1 (radar, 10 m)**, máscara de agua por umbral (Otsu o {p.cfg['sar']['umbral_fijo_dB']} dB fijo, ver `sar_stats.md`):

{_tabla_sar(R, p)}
Limitaciones: el radar en banda C no ve el suelo bajo copas (agua bajo árboles aparece brillante, no oscura); superficies
lisas no-agua (suelo desnudo húmedo, pavimento) también aparecen oscuras; las escenas caen días antes o después del pico.
Figuras `30_sar_*.png`.

## 3. Simulación lluvia → lámina de agua (rain-on-grid)

Modelo 2D Landlab `OverlandFlow` sobre el DEM primario corregido ({prim}, 30 m), dominio de ±{p.buffers['lluvia_m']/1000:.0f} km con bordes
abiertos, Manning n = {rp.get('mannings_n', p.cfg['lluvia']['manning'])}, infiltración Green-Ampt con Ks = {rp.get('Ks_mm_h', p.cfg['lluvia']['Ks_mm_h'])} mm/h
(ψ = {rp.get('psi_m', p.cfg['lluvia']['psi_m'])} m, Δθ = {rp.get('dtheta', p.cfg['lluvia']['dtheta'])}) y sensibilidad con Ks = {p.cfg['lluvia']['Ks_sat_mm_h']} mm/h (suelo saturado / napa alta).
Hietograma de bloque alterno con relaciones P(d)/P(24 h) genéricas: **sin período de retorno** (no hay IDF local).

{rog_tab}
**Escenario → efecto**

{rog_eff}
Advertencias: no incluye la crecida que viene de fuera del dominio; las celdas son de 30 × 30 m; celdas aisladas con láminas
> 1 m suelen ser pozos residuales del DEM; el balance de masa cierra por residuo. Figuras `40_rog_*.png`; tabla `rog_stats.md`.

## 4. Limitaciones

- **DEM de 30 m**: sin microrrelieve ni obras; los modelos de superficie (GLO-30, MDE-Ar) ven copas y techos; FABDEM los remueve
  estadísticamente. Datum vertical EGM2008 (FABDEM/GLO-30) o SRVN16 (IGN): irrelevante para alturas relativas.
- **Sin calibración**: no hay aforos ni marcas de crecida; Manning y Green-Ampt son valores de literatura.
- **Período de retorno aproximado**: Gumbel sobre máximos anuales de ERA5 (28 km, subestima tormentas convectivas) y CHIRPS (5 km); no hay IDF local.
- **Crecida del arroyo desde aguas arriba**: no simulada; el desborde se evalúa por HAND y por el registro satelital.
- **Satélite**: Landsat no ve bajo nubes ni árboles; Sentinel-1 no ve bajo copas y cae días después del pico.

## 5. Qué chequear en campo

{campo_md}
## 6. Reglas del veredicto

Niveles: {' < '.join(NIVELES)}. Cada componente toma el nivel más alto que dispare alguna regla; el global es el máximo de los dos.

{_reglas_md()}
Eventos Sentinel-1 configurados: {', '.join(ev_ids)}. Fuentes y licencias: `SOURCES.md` del repositorio.
"""
    et, frase = etiqueta(ev["global"])
    return md, dict(indicadores=ind, veredicto=ev, verdict_md=veredicto_md.strip(), field_md=campo_md.strip(),
                     etiqueta=et, frase_nivel=frase)


def run(p: Project) -> dict:
    md, info = build(p)
    (p.out / "README.md").write_text(md)
    json.dump(info, open(p.out / "veredicto.json", "w"), ensure_ascii=False, indent=1, default=str)
    ev = info["veredicto"]
    p.summary_line("INFORME", [
        f"Veredicto global: {ev['global']} · lluvia local {ev['lluvia_local']['nivel']} · desborde {ev['desborde']['nivel']}",
        "Reglas lluvia local: " + ("; ".join(f'{d}={f(v)}→{n}' for n, d, v in ev['lluvia_local']['razones']) or "ninguna"),
        "Reglas desborde: " + ("; ".join(f'{d}={f(v)}→{n}' for n, d, v in ev['desborde']['razones']) or "ninguna"),
        "Indicadores sin datos: " + (", ".join(ev['lluvia_local']['faltan'] + ev['desborde']['faltan']) or "ninguno"),
        f"Salida: {p.out / 'README.md'} · veredicto.json",
    ])
    return info
