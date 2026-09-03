# Rain-on-grid · lámina máxima por escenario

Landlab OverlandFlow (de Almeida et al. 2012) sobre fabdem (30 m, dominio ±5 km), Manning n = 0.05, Green-Ampt Ks = 10 mm/h (saturado: 2), ψ = 0.17 m, Δθ = 0.15. Hietograma de bloque alterno. Sin período de retorno (no hay IDF local). Columnas `*_aoi_*` = buffer de 500 m. `escurrido_pct` = 100 − infiltrado (sale por los bordes abiertos o queda almacenado; la salida por los bordes se estima como residuo).

| escenario | P_mm | dur_h | Ks_mm_h | hmax_lote_m | hmedia_lote_m | pct_lote_gt5cm | pct_lote_gt20cm | dur_max_lote_h | hmax_aoi_m | hmedia_aoi_m | pct_aoi_gt5cm | pct_aoi_gt20cm | infil_media_mm | escurrido_pct | almacenado_final_pct | t_sim_h | pasos | wall_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P050_24h | 50.00 | 24.00 | 10.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 41.02 | 17.97 | 0.00 | 30.00 | 1800 | 1.19 |
| P100_24h | 100.00 | 24.00 | 10.00 | 0.08 | 0.03 | 8.00 | 0.00 | 3.62 | 0.38 | 0.07 | 28.06 | 14.56 | 76.50 | 23.50 | 0.66 | 30.00 | 9074 | 6.23 |
| P150_24h | 150.00 | 24.00 | 10.00 | 0.43 | 0.17 | 64.00 | 36.00 | 7.30 | 0.78 | 0.20 | 53.13 | 33.90 | 101.06 | 32.63 | 2.23 | 30.00 | 10724 | 7.43 |
| P200_24h | 200.00 | 24.00 | 10.00 | 0.76 | 0.45 | 96.00 | 88.00 | 8.30 | 1.78 | 0.36 | 62.91 | 46.55 | 116.86 | 41.57 | 3.76 | 30.00 | 12716 | 9.24 |
| P060_2h | 60.00 | 2.00 | 10.00 | 0.06 | 0.03 | 4.00 | 0.00 | 2.82 | 0.35 | 0.06 | 27.31 | 11.69 | 52.69 | 12.18 | 5.40 | 8.00 | 3391 | 2.39 |
| P100_24h_sat | 100.00 | 24.00 | 2.00 | 0.48 | 0.20 | 76.00 | 48.00 | 9.59 | 0.84 | 0.22 | 54.30 | 35.60 | 47.72 | 52.28 | 8.19 | 30.00 | 11730 | 8.84 |
| P150_24h_sat | 150.00 | 24.00 | 2.00 | 1.67 | 0.90 | 100.00 | 100.00 | 11.24 | 2.47 | 0.68 | 67.16 | 54.09 | 57.76 | 61.49 | 9.29 | 30.00 | 14178 | 11.59 |
