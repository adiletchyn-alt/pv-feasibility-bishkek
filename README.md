# Feasibility Study: Rooftop Solar PV for a Business Centre in Bishkek (Huawei FusionSolar, 3 options)

Learning project: a feasibility study of a rooftop PV plant on an 8-storey business centre in Bishkek, Kyrgyzstan. The model uses the tariffs and regulations of the Kyrgyz Republic and Huawei equipment. Benchmark: the Orion-2 business centre (178 Panfilov St), which installed 50 kW of PV and a ~200 kWh battery in January 2026.

**Full study (19 pages, PDF):** [docs/Feasibility_Study_Rooftop_PV_Bishkek_EN.pdf](docs/Feasibility_Study_Rooftop_PV_Bishkek_EN.pdf) — regulation, Huawei market, string design, financial model, incentives, risks.

A Russian version of this README is in [README_ru.md](README_ru.md).

## Results (base case, 14% discount rate, 25 years)

| | V1. Grid-tied 61 kWp | V2. Hybrid 61 kWp + 215 kWh | V3. Grid-tied 122 kWp with export |
|---|---|---|---|
| CAPEX | $40.1k | $124.0k | $79.7k |
| NPV | KGS −0.14M | KGS −8.56M | KGS −1.22M |
| IRR | 13.4% | −0.7% | 11.6% |
| Simple payback | 7.9 years | — | 8.9 years |
| Share of building load | 34% | 36% | 51% |

Conclusion: V1 is close to break-even and turns NPV-positive with financing cheaper than 14%, CAPEX 5–10% lower, or tariff growth above 8% per year. The battery (V2) pays off only if uninterrupted power earns about KGS 940k per year on top of energy savings.

## Incentives (Kyrgyz Republic, checked 06.11.2026)

| Incentive | Effect in the model |
|---|---|
| VAT-free import of RES equipment (Cabinet list of 04.10.2021, expanded by Resolution No. 272 of 22.04.2026) — [Economist.kg](https://economist.kg/enierghietika/2026/09/12/nds-truby-malye-ges-lgota/) | CAPEX −6–9% for a developer who cannot recover VAT (prices in the model already exclude VAT) |
| "Improving Air Quality" loans for business: up to KGS 5M at 10% — [Economist.kg](https://economist.kg/novosti/2026/06/04/clean-air-loans-kyrgyzstan/) | Discounting at 10%: NPV V1 +KGS 1.20M, V3 +KGS 1.06M, V2 −KGS 7.88M |
| Tax exemption up to 5 years for new RES producers — [Kaktus.media](https://kaktus.media/doc/521963_zelenaia_ekonomika._barery_i_stimyly_dlia_biznesa_v_kyrgyzstane.html) | Negligible (depreciation already offsets early-year tax); likely not applicable to self-consumption |

Run the scenario: `model.run({'discount': 0.10, 'tax_holiday': 5})`.

## How the model works

- `model.py` contains all logic and all assumptions (dictionaries `A` and `P`).
  - Hourly generation profile (8,760 hours) built from NASA POWER seasonal yield and scaled to 1,500 kWh/kWp.
  - Business-centre load profile: weekdays, Saturday, Sunday, seasonal factor.
  - Battery dispatch: charging from PV surplus, discharging to the load, 30% of capacity reserved for backup, 91.3% round-trip efficiency.
  - Finance in nominal KGS: tariff path, O&M, inverter and battery replacement, profit tax, depreciation.
  - Metrics: NPV, IRR, simple and discounted payback, ROI, PI, LCOE, levelised grid tariff.
  - Sensitivity: tariff, discount rate, CAPEX, yield, KGS exchange rate, surplus buy-back price.
- `pv_feasibility.ipynb` — summary table, charts and scenarios.
- `results.json` — output of the last run.
- `docs/` — the full feasibility study as PDF.

```bash
python model.py   # prints results and sensitivity, writes results.json
```

Requires Python 3.10+, numpy, pandas, matplotlib.

## Key inputs (re-checked on 06.11.2026)

- Commercial tariff from 01.05.2026: KGS 4.33/kWh excluding taxes — [Economist.kg](https://economist.kg/enierghietika/2026/03/28/skolko-budiet-stoit-eliektrichiestvo-v-kyrghyzstanie-s-1-maia-2026-ghoda-tarify/)
- Yield in Bishkek: PVGIS 1,681 and Global Solar Atlas 1,484 kWh/kWp — [Tazabek](https://www.tazabek.kg/news:2533130?from=rss) (search snippet, article paywalled); seasonal profile — [profileSOLAR / NASA POWER](https://profilesolar.com/locations/Kyrgyzstan/Bishkek/)
- 2026 amendments to the RES law: storage of at least 30% of capacity for RES operators — [Economist.kg](https://economist.kg/enierghietika/2026/04/07/podpisany-popravki-v-zakon-o-vie-nakopitieli-enierghii-stali-obiazatielnymi/)
- Draft rooftop PV regulation: surplus sales up to 15 kW without a licence — [QAZAQ GREEN](https://qazaqgreen.com/en/news/central-asia/3556/)
- National Bank policy rate: 12% — [Economist.kg](https://economist.kg/ekonomika/2026/10/27/nbkr-uchetnaya-stavka-27-10-2026/)
- Huawei: [SUN2000-50KTL-M3 datasheet](https://solar.huawei.com/-/media/Solar/attachment/pdf/eu/datasheet/SUN2000-50kTL-M3-Datasheet.pdf), [LUNA2000-215 datasheet (2S12, Chinese)](https://solar.huawei.com/admin/asset/v1/pro/view/cd370f83116e48f290a1d8c8bfabf3f6.pdf)

## Limitations

- Building consumption, roof area, equipment prices, taxes and the surplus buy-back price for legal entities are assumptions, flagged in the code.
- Generation uses averaged days without cloud cover: the peak is ~0.68 kW/kWp, so inverter clipping (DC/AC 1.22) is not visible and self-consumption may be slightly overstated.
- The battery in V2 delivers ~6,200 kWh per year (~29 full cycles): with 61 kWp of PV it is under-used (Huawei recommends ~115 kWp).
- PVGIS/GSA figures, the KGS 1.45 buy-back price and turnkey prices come from the search snippet of a paywalled Tazabek article.
- This is a learning model, not design documentation.
