# Volatility and the already-known next-month leader

Research date: November 2, 2026. Cached prices through 2026-10-30. Last complete signal month: 2026-10-31.

## Findings

At 10 bps per traded leg, advancing to the next leader during candidate volatility above 20% reduced full-period CAGR from 13.73% to 13.46%, while reducing the worst daily drawdown from -22.21% to -20.58%. Its full-period Sharpe was lower, and the paired return-difference interval spans zero.

The later-period result was better: CAGR 16.27% versus 15.33%, across 8 executed overrides. Its paired interval also spans zero. This later period is not a clean holdout.

The narrower rule of retaining an eligible incumbent when it is also the next leader had only 3 completed historical overrides and a full-period CAGR of 13.65%. It would retain IWD for the current signal, but the small sample provides little evidence for that specific override. The current signal has no realized holding-period outcome in the cached data.

These are risk/return tradeoffs rather than evidence of a reliably more profitable current trade. No tested alternative improved full-period CAGR and Sharpe over baseline, and no production rule was changed.

## Market context at the rebalance

| ETF | October return | Last daily return | 21-day annualized realized vol | Historical month-end vol percentile |
| --- | --- | --- | --- | --- |
| SPY | -0.91% | -1.77% | 11.66% | 37.7% |
| QQQ | -6.66% | -3.47% | 22.61% | 65.2% |
| IWD | +4.32% | -0.81% | 7.25% | 7.0% |

Volatility is the sample standard deviation of the latest 21 daily adjusted-close returns multiplied by sqrt(252). The percentile compares with earlier month-end observations available in the same cached history. QQQ is substantially more volatile than IWD, while SPY's measured volatility is below the study's 20% broad-market threshold.

Cboe's official page reports a previous VIX close of 19.42 for October 30. That is option-implied broad-market volatility, a different measure from the realized ETF volatilities above. No November 2 intraday observation is used to choose historical month-end regimes. [Cboe VIX](https://www.cboe.com/tradable-products/vix/)

## Rules specified before examining returns

Primary rule: if the currently first-ranked style ETF passes today's 6m OR 12m cash hurdle, its 21-day annualized volatility exceeds 20%, the known next-month momentum leader differs, and that next leader also passes today's hurdle, allocate the style sleeve to the next leader now. Otherwise follow the production leader-first selector. The alternative leader can be below today's top two. This condition is evaluated at each monthly formation, including for an existing holding; it is not restricted to new entries.

Targeted incumbent variant: under the same 20% candidate-volatility condition, retain the incumbent only if it is the known next leader, is still in today's top two, and passes today's cash hurdle. Otherwise follow production. This directly tests retaining IWD in a QQQ-to-IWD situation without advancing to arbitrary new ETFs.

Sensitivity checks: candidate-volatility thresholds of 15% and 25%; SPY rather than candidate volatility above 20%; and unconditional use of a differing next leader that passes today's hurdle. These are displayed together rather than selecting the best threshold. A threshold named 20% is a round research convention, not an independently validated definition of a high-volatility regime.

The next ranking uses only returns through the completed formation month because the production ranking skips one month. Future returns and future cash hurdles are never used to select positions. Knowing next month's leader does not guarantee it will pass next month's cash hurdle or be held then.

All variants retain the 65/35 portfolio split, cash hurdles, defensive selection, regime rules, disabled throttle, next-trading-day closing execution, and daily buy-and-hold accounting. The sector congestion game is recalculated for each counterfactual style path. Each version maintains its own incumbent history.

## Net backtest at 10 bps per traded leg

| Period | Rule | CAGR | Sharpe | Daily max DD | Overrides | Style changes |
| --- | --- | --- | --- | --- | --- | --- |
| 2001-2018 | Current strategy | 13.02% | 0.924 | -20.27% | 0 | 65 |
| 2001-2018 | Use next leader when candidate vol >20% | 12.21% | 0.873 | -19.63% | 15 | 59 |
| 2001-2018 | Keep incumbent if next leader; candidate vol >20% | 12.86% | 0.911 | -20.27% | 2 | 61 |
| 2001-2018 | Candidate-vol threshold 15% | 12.08% | 0.866 | -19.63% | 27 | 61 |
| 2001-2018 | Candidate-vol threshold 25% | 12.47% | 0.897 | -19.63% | 7 | 66 |
| 2001-2018 | SPY-vol threshold 20% | 12.65% | 0.894 | -20.27% | 2 | 65 |
| 2001-2018 | Always use qualifying next leader | 12.02% | 0.861 | -19.63% | 52 | 66 |
| 2019-latest | Current strategy | 15.33% | 0.909 | -22.21% | 0 | 27 |
| 2019-latest | Use next leader when candidate vol >20% | 16.27% | 0.966 | -20.58% | 8 | 24 |
| 2019-latest | Keep incumbent if next leader; candidate vol >20% | 15.40% | 0.915 | -21.82% | 1 | 25 |
| 2019-latest | Candidate-vol threshold 15% | 15.71% | 0.919 | -20.62% | 15 | 24 |
| 2019-latest | Candidate-vol threshold 25% | 15.71% | 0.934 | -20.87% | 4 | 26 |
| 2019-latest | SPY-vol threshold 20% | 15.43% | 0.916 | -22.21% | 1 | 27 |
| 2019-latest | Always use qualifying next leader | 15.06% | 0.875 | -20.54% | 24 | 27 |
| Full | Current strategy | 13.73% | 0.920 | -22.21% | 0 | 92 |
| Full | Use next leader when candidate vol >20% | 13.46% | 0.904 | -20.58% | 23 | 83 |
| Full | Keep incumbent if next leader; candidate vol >20% | 13.65% | 0.914 | -21.82% | 3 | 86 |
| Full | Candidate-vol threshold 15% | 13.20% | 0.883 | -20.62% | 42 | 85 |
| Full | Candidate-vol threshold 25% | 13.47% | 0.910 | -20.87% | 11 | 92 |
| Full | SPY-vol threshold 20% | 13.51% | 0.902 | -22.21% | 3 | 92 |
| Full | Always use qualifying next leader | 12.95% | 0.866 | -20.54% | 76 | 93 |

Override and change counts are formation-dated and require an execution within the cached data; the latest October signal has no November execution or outcome in this dataset. The inherited simulator omits its initial partial month; the reported monthly returns run from 2001-09-30 through 2026-10-31.

## Cost sensitivity: full period

| Rule | Cost per leg (bps) | CAGR | Sharpe |
| --- | --- | --- | --- |
| Current strategy | 0 | 14.51% | 0.972 |
| Current strategy | 10 | 13.73% | 0.920 |
| Current strategy | 25 | 12.57% | 0.841 |
| Use next leader when candidate vol >20% | 0 | 14.18% | 0.953 |
| Use next leader when candidate vol >20% | 10 | 13.46% | 0.904 |
| Use next leader when candidate vol >20% | 25 | 12.38% | 0.830 |
| Keep incumbent if next leader; candidate vol >20% | 0 | 14.39% | 0.963 |
| Keep incumbent if next leader; candidate vol >20% | 10 | 13.65% | 0.914 |
| Keep incumbent if next leader; candidate vol >20% | 25 | 12.54% | 0.839 |
| Candidate-vol threshold 15% | 0 | 13.93% | 0.934 |
| Candidate-vol threshold 15% | 10 | 13.20% | 0.883 |
| Candidate-vol threshold 15% | 25 | 12.10% | 0.808 |
| Candidate-vol threshold 25% | 0 | 14.25% | 0.962 |
| Candidate-vol threshold 25% | 10 | 13.47% | 0.910 |
| Candidate-vol threshold 25% | 25 | 12.32% | 0.830 |
| SPY-vol threshold 20% | 0 | 14.28% | 0.954 |
| SPY-vol threshold 20% | 10 | 13.51% | 0.902 |
| SPY-vol threshold 20% | 25 | 12.35% | 0.823 |
| Always use qualifying next leader | 0 | 13.74% | 0.920 |
| Always use qualifying next leader | 10 | 12.95% | 0.866 |
| Always use qualifying next leader | 25 | 11.79% | 0.784 |

## Uncertainty: paired return differences at 10 bps

12-month circular moving-block bootstrap, 10,000 resamples, fixed seed 20261102. Differences below are annualized arithmetic mean return differences, not CAGR differences. Intervals are descriptive and do not correct for testing several related strategy variants.

| Rule minus baseline | Period | Annualized mean difference | 95% block interval |
| --- | --- | --- | --- |
| Use next leader when candidate vol >20% | 2001-2018 | -0.74% | [-1.67%, -0.04%] |
| Use next leader when candidate vol >20% | 2019-latest | +0.84% | [-0.45%, +2.22%] |
| Use next leader when candidate vol >20% | Full | -0.25% | [-1.06%, +0.48%] |
| Keep incumbent if next leader; candidate vol >20% | 2001-2018 | -0.14% | [-0.40%, +0.00%] |
| Keep incumbent if next leader; candidate vol >20% | 2019-latest | +0.06% | [-0.00%, +0.18%] |
| Keep incumbent if next leader; candidate vol >20% | Full | -0.08% | [-0.26%, +0.04%] |
| Candidate-vol threshold 15% | 2001-2018 | -0.86% | [-1.94%, +0.15%] |
| Candidate-vol threshold 15% | 2019-latest | +0.37% | [-1.46%, +2.12%] |
| Candidate-vol threshold 15% | Full | -0.48% | [-1.44%, +0.46%] |
| Candidate-vol threshold 25% | 2001-2018 | -0.51% | [-1.18%, +0.03%] |
| Candidate-vol threshold 25% | 2019-latest | +0.34% | [-0.77%, +1.47%] |
| Candidate-vol threshold 25% | Full | -0.25% | [-0.83%, +0.29%] |
| SPY-vol threshold 20% | 2001-2018 | -0.32% | [-0.82%, +0.00%] |
| SPY-vol threshold 20% | 2019-latest | +0.09% | [-0.12%, +0.36%] |
| SPY-vol threshold 20% | Full | -0.19% | [-0.55%, +0.06%] |
| Always use qualifying next leader | 2001-2018 | -0.91% | [-2.55%, +0.59%] |
| Always use qualifying next leader | 2019-latest | -0.19% | [-2.56%, +1.90%] |
| Always use qualifying next leader | Full | -0.69% | [-2.05%, +0.57%] |

## Matched volatile-month diagnostic

On primary-rule trigger months, compare the current and next leaders from the next trading day's close to the following rebalance close. Both ETFs are charged 10 bps on entry and 10 bps on exit. This is an ETF-only diagnostic; it excludes sector changes and the ability to avoid a trade by retaining an existing position. Those effects are included in the full strategy results above. Only fully observed holding periods are included.

| Formation period | Cases | Current leader mean | Next leader mean | Mean difference | Next leader wins |
| --- | --- | --- | --- | --- | --- |
| 2001-2018 | 15 | +1.05% | -0.34% | -1.38% | 33.3% |
| 2019-latest | 8 | -0.18% | +1.11% | +1.30% | 75.0% |
| Full | 23 | +0.62% | +0.17% | -0.45% | 47.8% |

These events can cluster in the same market episode; the number of events is not the number of independent observations.

## Latest signal: decisions without a realized outcome

| Rule | Its incumbent | Current leader | Known next leader | Candidate vol | Regime? | Override? | Selected |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Current strategy | IWD | QQQ | IWD | 22.61% | False | False | QQQ |
| Use next leader when candidate vol >20% | IWD | QQQ | IWD | 22.61% | True | True | IWD |
| Keep incumbent if next leader; candidate vol >20% | IWD | QQQ | IWD | 22.61% | True | True | IWD |
| Candidate-vol threshold 15% | IWD | QQQ | IWD | 22.61% | True | True | IWD |
| Candidate-vol threshold 25% | IWD | QQQ | IWD | 22.61% | False | False | QQQ |
| SPY-vol threshold 20% | IWD | QQQ | IWD | 22.61% | False | False | QQQ |
| Always use qualifying next leader | QQQ | QQQ | IWD | 22.61% | True | True | IWD |

## Verification and limits

- The baseline weights and net return path exactly match production. The disabled-trigger control also matches baseline.
- Forecasts equal the next ranking across the full history. Truncating all inputs at December 2018 and March 2020 leaves all earlier strategy decisions unchanged, including their volatility regimes.
- This is exploratory research motivated by the current QQQ signal. 2019+ is a later-period diagnostic, not a clean holdout. Choosing a threshold after examining these results would introduce further selection bias.
- Cached adjusted prices and FRED histories are not point-in-time vintage datasets. Original release delays and historical revisions are not reconstructed.
- The inherited simulator charges turnover across its position dictionary, including CASH changes. Its conventions are identical for all comparisons; no production accounting change was made.
- No strategy rule, broker configuration, or order was changed by this research script.

## Reproduce

```bash
PYTHONDONTWRITEBYTECODE=1 python3 strategy/volatility_leader_test.py
```

Input fingerprints:

- `strategy/data/prices.parquet`: `18f116cc599dd135429ea1fdd1f12597c323d8334d7f492c8b1acc08735cbf47`
- `strategy/data/tbill_dgs3mo.parquet`: `a27b2dc9290a06759914d207153c236a7f33c89f926181cd87314f04a39f7a34`
- `strategy/strategy_lib.py`: `179179861d1376953909187d53ac465e88ec1044e63a6e9ccdd2e74df0b415a2`
- `strategy/volatility_leader_test.py`: `5d0db354da7f83f8ff6e367a9603a3e15a973c324d055c7dbc1c9ebf6b8268c6`
- `strategy/next_rank_entry_test.py`: `2c86c2aa890041368f9701708100e50680b0c7faa8624770a03cf0d943c0d887`
