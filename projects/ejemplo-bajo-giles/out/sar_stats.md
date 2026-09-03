# Sentinel-1 RTC · agua detectada por evento

Fuente: Planetary Computer `sentinel-1-rtc` (gamma0 VV, 10 m). Filtro Lee 7x7, umbral de Otsu sobre el histograma del buffer 10 km (si Otsu > −13 dB no hay bimodalidad agua/no-agua y se usa -18 dB fijo). 'nueva' = agua en la escena y no en la referencia seca. Columnas: `*_500m` = buffer AOI (500 m), `*_10km` = buffer hidrológico (10 km).

**Limitaciones**: el radar en banda C no ve el suelo bajo copas (agua bajo árboles aparece brillante por doble rebote, no oscura); superficies lisas no-agua (suelo desnudo húmedo, pavimento, cultivos rastreros) también aparecen oscuras; el viento rugosifica el agua. Píxeles de 10 m.

| evento | escena | fecha | momento | dias_desde_evento | umbral_dB | pct_agua_lote | pct_agua_500m | pct_nueva_lote | pct_nueva_500m | pct_agua_10km | dB_medio_lote | dB_dif_lote | pct_500m_caida_3dB | nota |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| referencia_seca | S1A_IW_GRDH_1SDV_20230225T091530_20230225T091555_047390_05B052_rtc | 2023-02-25 | nan | nan | -18.00 | 0.00 | 0.00 | nan | nan | 0.01 | -8.30 | nan | nan | Otsu=-9.7 dB no plausible para agua; se usa umbral fijo -18 dB |
| 2015-08_agosto2015 | S1A_IW_GRDH_1SSV_20150818T091444_20150818T091508_007315_00A0A9_rtc | 2015-08-18 | post | 8.00 | -18.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.06 | -11.26 | -2.97 | 7.22 | Otsu=-9.2 dB no plausible para agua; se usa umbral fijo -18 dB |
| 2016-04_abril2016 | SIN COBERTURA | nan | nan | nan | nan | nan | nan | nan | nan | nan | nan | nan | nan | nan |
| 2024-03_marzo2024 | S1A_IW_GRDH_1SDV_20240303T091535_20240303T091600_052815_066446_rtc | 2024-03-03 | pre | -9.00 | -18.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | -9.38 | -1.08 | 0.36 | Otsu=-8.9 dB no plausible para agua; se usa umbral fijo -18 dB |
| 2024-03_marzo2024 | S1A_IW_GRDH_1SDV_20240327T091535_20240327T091600_053165_0670F5_rtc | 2024-03-27 | post | 15.00 | -18.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.04 | -7.94 | 0.36 | 0.10 | Otsu=-8.0 dB no plausible para agua; se usa umbral fijo -18 dB |
| 2025-05_mayo2025 | S1A_IW_GRDH_1SDV_20250509T091529_20250509T091554_059115_rtc | 2025-05-09 | pre | -8.00 | -18.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | -9.78 | -1.49 | 1.34 | Otsu=-8.6 dB no plausible para agua; se usa umbral fijo -18 dB |
| 2025-05_mayo2025 | S1C_IW_GRDH_1SDV_20250515T091414_20250515T091439_002339_rtc | 2025-05-15 | pre | -2.00 | -18.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.06 | -11.96 | -3.67 | 16.16 | Otsu=-9.9 dB no plausible para agua; se usa umbral fijo -18 dB |
| 2025-05_mayo2025 | S1C_IW_GRDH_1SDV_20250527T091415_20250527T091440_002514_rtc | 2025-05-27 | post | 10.00 | -18.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | -9.23 | -0.94 | 1.33 | Otsu=-8.0 dB no plausible para agua; se usa umbral fijo -18 dB |
| 2026-06_junio2026 | S1D_IW_GRDH_1SDV_20260604T091439_20260604T091504_003084_00555E_rtc | 2026-06-04 | pre | -4.00 | -18.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | -10.49 | -2.20 | 15.51 | Otsu=-10.4 dB no plausible para agua; se usa umbral fijo -18 dB |
| 2026-06_junio2026 | S1A_IW_GRDH_1SDV_20260609T091501_20260609T091526_064890_082D55_rtc | 2026-06-09 | post | 1.00 | -18.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.03 | -5.57 | 2.73 | 0.21 | Otsu=-8.1 dB no plausible para agua; se usa umbral fijo -18 dB |
| 2026-06_junio2026 | S1D_IW_GRDH_1SDV_20260616T091440_20260616T091505_003259_005B26_rtc | 2026-06-16 | post | 8.00 | -18.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | -6.49 | 1.80 | 0.98 | Otsu=-9.2 dB no plausible para agua; se usa umbral fijo -18 dB |
