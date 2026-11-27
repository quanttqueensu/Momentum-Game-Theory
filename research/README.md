# Research

In-sample experiments run against the production strategy (`strategy/strategy_lib.py`).
None of them change production code. Every script imports `strategy_lib` and tests one variant.

New here? Start with [`reports/research_guide.md`](reports/research_guide.md): a plain-language guide to the strategy, the 7 ETFs and every experiment below.

## Layout

```
research/
├── scripts/    one script per experiment (run from the repo root)
├── data/       outside input data, saved once and read-only
│   └── french/ Kenneth French data library (downloaded 2026-11-25)
├── results/    charts (PNG) written by the scripts
├── tables/     CSV outputs, one folder per experiment
└── reports/    longer write-ups
```

Run any experiment from the repo root, e.g. `python research/scripts/factor_momentum_test.py`.

## Experiments

| Experiment | Question | Script | Charts | Tables / report |
|---|---|---|---|---|
| Damped returns | Does capping each monthly return at ±K·σ before scoring help the style sleeve? | `damped_returns_test.py` | `damped_returns_insample.png` | — |
| Soft-damp z-score | Does squeezing extreme 3/6/12m z-scores with `C·tanh(z/C)` help? | `soft_damp_zscore_test.py` | `soft_damp_zscore_insample.png` | — |
| High-score penalty | Does pulling back assets far above the pack improve results? | `high_score_penalty_test.py` | `high_score_penalty_insample.png` | — |
| Factor momentum | Does following each factor spread's own trend beat ranking the style ETFs? | `factor_momentum_test.py` | `factor_momentum_french.png`, `factor_momentum_insample.png` | `tables/factor_momentum/` |
| Score predictive power | Does the production score predict next month's returns? (measurement only) | `score_predictive_power.py` | — | `tables/score_predictive_power/` |
| Sleeve split | Where does the style sleeve's edge come from: the ranking or the T-bill hurdle? (measurement only) | `sleeve_split.py` | `sleeve_split_insample.png` | `tables/sleeve_split/` |
| EW-hurdle holdout | Does the equal-weight-passing sleeve hold up out of sample (2019-01 to 2026-10)? Result: not confirmed | `ew_hurdle_holdout.py` | `ew_hurdle_holdout.png` | `tables/ew_hurdle_holdout/` |
| Sector signal | Do residual or volatility-adjusted momentum scores beat production in the sector sleeve? | `sector_signal_research.py` | `sector_signal_insample.png` | `tables/sector_signal/`, `reports/sector_signal_research.md` |
| Breadth sizing | Does sizing the style pick by breadth (share of the 7 style ETFs passing the T-bill hurdle) beat production? In-sample 2002-2018: Sharpe 0.886 vs 0.763, max DD -15.5% vs -26.2%, but fails the bar (t 0.35, lower CAGR 2010-18). Holdout 2019-01 to 2026-10: not confirmed (Sharpe 0.745 vs 0.859, CAGR 12.0% vs 14.7%)  Follow-up 2026-11-26: across all 21 rebalance days it wins in-sample Sharpe on 21/21 (gain concentrated where production was unlucky, corr -0.89) but loses Sharpe and CAGR on 21/21 in 2019-26; on US history 1928-2018 it is no better than production diluted to the same exposure (t 0.78) and lags recoveries (1932, 1998) | `breadth_sizing_test.py` | `breadth_sizing_insample.png`, `breadth_sizing_holdout.png`, `breadth_sizing_offsets.png` | `tables/breadth_sizing/` |
| Switch band (T2) | Does switching the style ETF only when the new #1 beats the current holding by more than 0.5 (composite z units) cut trading without hurting results? In-sample 2002-2018: style switches -39%/yr, Sharpe 0.762 vs 0.763, CAGR 11.26% vs 11.17%, same max DD; PASS (implementation non-inferiority). Holdout 2019-01 to 2026-10: CONFIRMED (switches -46%, Sharpe 0.869 vs 0.859, CAGR 14.92% vs 14.69%). Long US history 1964-2018: CAGR +0.03 pp. Recommended | `switch_band_test.py` | `switch_band_insample.png`, `switch_band_holdout.png` | `tables/switch_band/` |
