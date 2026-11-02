# Current style decision: analogues and bounded parameter review

Research date: November 2, 2026. Cached prices through 2026-10-30; current signal 2026-10-31. 31 fixed configurations, three cost levels, plus a historical annual-selection diagnostic. Production is unchanged.

## Findings and decision

The expanded tests do not provide a strong basis for overriding today's QQQ selection or rewriting entry rules around this trade. True incumbent retention, dropping six-month momentum, skipping no month, and rejecting new entries after a 5% loss all reduced full-period CAGR and Sharpe. Some more severe 7.5% rules showed tiny retrospective improvements; they would still select QQQ today and do not establish a robust new rule.

The separate sizing result is promising: 50% style / 50% sector allocation produced CAGR 13.73% versus 13.73%, Sharpe 0.992 versus 0.920, annualized volatility 11.94% versus 13.04%, and daily max drawdown -20.56% versus -22.21%. It also improved Sharpe in both the 2001-2018 and 2019+ comparisons. It still selects QQQ, but reduces the style allocation. This is a candidate for separate risk-budget review and forward paper tracking, not a demonstrated advantage from replacing QQQ with IWD for November.

Keep the current signal rules for the existing paper test. Do not automatically promote a retrospective winner or alter pending orders from this research. Similarity examples do not settle the next return; sizing and confidence in the forecast are separate decisions.

## Closest historical examples

There is no unique historical repeat. Similarity is computed without using subsequent returns. Market distance uses selected ETF monthly return and 21-day annualized volatility, SPY monthly return, and SPY volatility. Combined distance adds the selected ETF's skipped momentum score, six-month component dominance, unskipped twelve-month excess return over cash, and its already-known next-month rank. Each feature is divided by its standard deviation across preceding selected-style observations; distance is equal-weight root-mean-square standardized difference. These feature weights are subjective, not a validated forecast.

Candidates must have lost more than 5% in the signal month and have an observed following calendar month. Cohorts distinguish all styles, QQQ only, new entries, and new QQQ entries. The current QQQ month has no following-month outcome and is excluded.

| Metric | Cohort | Closest signal month | ETF | New entry? | ETF prior month | ETF following month (gross) | Full book following month (net) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| market | all_bad | 2005-03 | EEM | False | -7.91% | -1.25% | -0.52% |
| market | QQQ_bad | 2012-10 | QQQ | False | -5.28% | +1.31% | +0.34% |
| market | new_bad | 2004-04 | IWM | True | -5.52% | +2.15% | +1.28% |
| market | new_QQQ_bad | 2021-09 | QQQ | True | -5.68% | +7.86% | +8.13% |
| combined | all_bad | 2004-07 | IWM | True | -6.77% | -1.51% | +0.13% |
| combined | QQQ_bad | 2023-09 | QQQ | False | -5.08% | -2.07% | -2.07% |
| combined | new_bad | 2004-07 | IWM | True | -6.77% | -1.51% | +0.13% |
| combined | new_QQQ_bad | 2021-09 | QQQ | True | -5.68% | +7.86% | +8.13% |

All neighbors, feature values, distances, and fixed k=1/3/5/10 summaries are saved in the CSV artifacts. A nearest case is an example, not an estimate that the same outcome will recur.

## Parameter comparisons

The bounded family includes true top-two incumbent retention; equal-weight top-two selection; skipping zero rather than one month; single-horizon and leave-one-horizon-out momentum; six-month score weights of 1/6 and 1/2; new-entry loss filters at -3%, -5%, and -7.5%; defensive exits after -5% or -7.5%; early use of the next leader after those three losses; the known-next-rank veto; 15/20/25% candidate-volatility overrides; conditional incumbent retention; unconditional early use of the next leader; style allocation weights of 35%, 50%, and 80%; and restoring the existing 15% or 20% volatility throttle. Full definitions are in the saved configuration JSON and research source.

New-entry loss vetoes retain an eligible current-top-two incumbent that passes today's cash hurdle, or use the existing defensive choice. Defensive-loss rules move the selected style holding to that defensive choice after a qualifying monthly loss. Early-leader rules require the alternate leader to pass today's hurdle. Top-two equal weighting chooses only current top-two ETFs that pass; if only one passes it receives the whole style allocation. No model uses future cash hurdles or future prices to choose a position.

Sector selections are recalculated for every style path and sleeve weight. Portfolio costs, drift, defensive/cash returns, and execution at the next trading day's close use the production simulator.

### Full period, net 10 bps per traded leg

| Configuration | CAGR | Sharpe | Daily max DD |
| --- | --- | --- | --- |
| style_weight35 | 13.30% | 1.017 | -21.00% |
| style_weight50 | 13.73% | 0.992 | -20.56% |
| advance_after_loss7p5 | 13.76% | 0.924 | -20.87% |
| reject_new_loss7p5 | 13.75% | 0.922 | -22.26% |
| baseline | 13.73% | 0.920 | -22.21% |
| retain_next_incumbent_vol20 | 13.65% | 0.914 | -21.82% |
| reject_new_loss5 | 13.65% | 0.913 | -22.26% |
| restore_throttle15 | 12.90% | 0.912 | -20.92% |
| advance_vol25 | 13.47% | 0.910 | -20.87% |
| restore_throttle20 | 13.08% | 0.908 | -22.09% |
| advance_after_loss5 | 13.50% | 0.907 | -20.87% |
| defensive_after_loss7p5 | 13.30% | 0.906 | -20.65% |
| reject_known_next_outside2 | 13.50% | 0.904 | -22.26% |
| advance_vol20 | 13.46% | 0.904 | -20.58% |
| six_weight_1_2 | 13.39% | 0.895 | -22.21% |
| defensive_after_loss5 | 12.93% | 0.892 | -19.88% |
| six_weight_1_6 | 13.27% | 0.890 | -21.76% |
| true_top2_buffer | 13.15% | 0.883 | -21.82% |
| advance_vol15 | 13.20% | 0.883 | -20.62% |
| ranking_skip0 | 13.09% | 0.874 | -20.54% |
| rank_3_only | 12.74% | 0.871 | -21.69% |
| advance_always | 12.95% | 0.866 | -20.54% |
| advance_after_loss3 | 12.81% | 0.863 | -20.87% |
| top2_equal | 12.22% | 0.857 | -22.20% |
| rank_6_only | 12.89% | 0.856 | -21.14% |
| style_weight80 | 13.83% | 0.854 | -24.27% |
| rank_6_12_drop3 | 12.78% | 0.847 | -23.16% |
| rank_3_12_drop6 | 12.54% | 0.845 | -25.18% |
| reject_new_loss3 | 12.43% | 0.840 | -22.82% |
| rank_3_6_drop12 | 12.68% | 0.838 | -23.33% |
| rank_12_only | 12.10% | 0.811 | -26.38% |

The largest full-history Sharpe is not an automatic deployment choice. This search was motivated by today's uncomfortable QQQ trade and includes related families examined earlier in the session. Repeatedly testing historical data can select noise. [Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)

### Temporal stability

Highest full-history Sharpe: `style_weight35`. Highest 2001-2018 Sharpe: `style_weight35`. All later periods below are diagnostics, not clean holdouts: this research and existing rules already use knowledge of the history.

| Period | Configuration | CAGR | Sharpe | Daily max DD |
| --- | --- | --- | --- | --- |
| 2001-2018 | baseline | 13.02% | 0.924 | -20.27% |
| 2001-2018 | style_weight35 | 12.47% | 1.020 | -19.15% |
| 2001-2018 | style_weight50 | 12.91% | 0.990 | -18.98% |
| 2001-2018 | true_top2_buffer | 12.58% | 0.896 | -20.30% |
| 2001-2018 | rank_3_12_drop6 | 11.67% | 0.837 | -20.27% |
| 2001-2018 | reject_new_loss5 | 12.87% | 0.912 | -20.27% |
| 2001-2018 | annual_selection_60m | 12.49% | 0.909 | -21.31% |
| 2019-latest | baseline | 15.33% | 0.909 | -22.21% |
| 2019-latest | style_weight35 | 15.16% | 1.009 | -21.00% |
| 2019-latest | style_weight50 | 15.55% | 0.995 | -20.56% |
| 2019-latest | true_top2_buffer | 14.41% | 0.855 | -21.82% |
| 2019-latest | rank_3_12_drop6 | 14.48% | 0.858 | -25.18% |
| 2019-latest | reject_new_loss5 | 15.40% | 0.912 | -22.26% |
| 2019-latest | annual_selection_60m | 15.02% | 0.920 | -21.00% |
| 2010-latest | baseline | 12.35% | 0.853 | -22.21% |
| 2010-latest | style_weight35 | 11.91% | 0.925 | -21.00% |
| 2010-latest | style_weight50 | 12.39% | 0.919 | -20.56% |
| 2010-latest | true_top2_buffer | 11.54% | 0.798 | -21.82% |
| 2010-latest | rank_3_12_drop6 | 10.77% | 0.750 | -25.18% |
| 2010-latest | reject_new_loss5 | 12.25% | 0.844 | -22.26% |
| 2010-latest | annual_selection_60m | 11.67% | 0.841 | -21.31% |

Annual-selection diagnostic: from the December 2009 formation, choose one configuration each December using its preceding 60 monthly net returns' Sharpe. Each simulated expert maintains its own state; actual selected full-book targets are re-simulated, including the cost of switching between experts. Selection for 2010 onward uses data only through the preceding December. Before 2010 it follows baseline. This remains a retrospective diagnostic of an already-selected candidate family.

## Uncertainty and the number of tests

Paired circular 12-month block bootstrap, 10,000 draws, seed 20261102. Marginal intervals and a common-width simultaneous 95% band for all fixed variants' annualized arithmetic mean return differences versus baseline are saved. The simultaneous band uses the 95th percentile of the largest absolute centered bootstrap error across the fixed family. This addresses this bounded family, not every earlier research choice or data revision, and is not a formal estimate of backtest-overfitting probability. It is also not a confidence interval for CAGR or Sharpe.

| Variant minus baseline | Annualized mean difference | Marginal 95% interval | Family 95% band |
| --- | --- | --- | --- |
| style_weight35 | -0.60% | [-1.77%, +0.62%] | [-2.72%, +1.52%] |
| style_weight50 | -0.14% | [-0.80%, +0.54%] | [-2.26%, +1.98%] |
| true_top2_buffer | -0.53% | [-1.78%, +0.62%] | [-2.65%, +1.59%] |
| rank_3_12_drop6 | -1.08% | [-2.14%, -0.04%] | [-3.20%, +1.04%] |
| reject_new_loss5 | -0.07% | [-0.26%, +0.05%] | [-2.19%, +2.05%] |

Return-difference intervals do not test the lower-volatility or higher-Sharpe hypothesis. That comparison is assessed separately using the same paired blocks below. Sharpe differences are in Sharpe units, with a separate simultaneous band across the same fixed configuration family.

| Variant minus baseline | Sharpe difference | Marginal 95% interval | Family 95% band |
| --- | --- | --- | --- |
| style_weight35 | +0.097 | [+0.007, +0.191] | [-0.066, +0.260] |
| style_weight50 | +0.073 | [+0.027, +0.120] | [-0.090, +0.235] |
| true_top2_buffer | -0.037 | [-0.125, +0.051] | [-0.199, +0.126] |
| rank_3_12_drop6 | -0.075 | [-0.150, -0.005] | [-0.238, +0.087] |
| reject_new_loss5 | -0.007 | [-0.025, +0.004] | [-0.169, +0.156] |

## Verification and limits

- Baseline weights and returns exactly match production. Every configuration's earlier weights survive removing data after December 2018 and March 2020.
- Permuting subsequent outcomes leaves the similarity rankings unchanged; no future outcomes enter neighbor distances.
- Cached adjusted prices and FRED data are not original historical vintages. Original publication delays and revisions are not reconstructed.
- Costs are checked at 0, 10, and 25 bps per leg. The inherited simulator charges CASH changes too and omits its initial partial month; all variants share those conventions. The common monthly sample starts in September 2001 and ends in October 2026.
- No return from November 2026 is present. The research cannot determine whether QQQ or IWD will be the better November holding.
- No strategy parameter, broker setting, position, or order was changed.

## Reproduce

```bash
PYTHONDONTWRITEBYTECODE=1 python3 strategy/model_decision_review.py
```

Input and code fingerprints:

- `strategy/data/prices.parquet`: `18f116cc599dd135429ea1fdd1f12597c323d8334d7f492c8b1acc08735cbf47`
- `strategy/data/tbill_dgs3mo.parquet`: `a27b2dc9290a06759914d207153c236a7f33c89f926181cd87314f04a39f7a34`
- `strategy/strategy_lib.py`: `179179861d1376953909187d53ac465e88ec1044e63a6e9ccdd2e74df0b415a2`
- `strategy/model_decision_review.py`: `50df5f141712175bfea8c2da4049649591b7f7d13928405c3e6213248e09cbb6`
- `strategy/volatility_leader_test.py`: `5d0db354da7f83f8ff6e367a9603a3e15a973c324d055c7dbc1c9ebf6b8268c6`
- `strategy/next_rank_entry_test.py`: `2c86c2aa890041368f9701708100e50680b0c7faa8624770a03cf0d943c0d887`
