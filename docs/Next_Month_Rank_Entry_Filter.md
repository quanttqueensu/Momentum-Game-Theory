# Known next-month rank: new-entry filter backtest

Research date: 2026-11-02. Cached ETF prices through 2026-10-30; last complete signal month 2026-10-31.

## Finding

The primary filter reduced style-holding changes from 92 to 76, but reduced net full-period CAGR from 13.73% to 13.50% and Sharpe from 0.920 to 0.904. There were only 13 rejected historical entries with executions in the cached sample. The filter helped modestly in the later period; the full-period paired interval spans zero. These results do not support adding the filter to production on performance grounds.

The inherited simulator's first reported monthly return is labelled 2001-09-30, and the last is labelled 2026-10-31. The latest label represents the completed October 30 trading close. The initial partial simulation month is omitted, matching production.

## Rule fixed before examining results

Keep the production 65% style / 35% sector strategy and its current leader-first style selection, cash hurdles, defensive choice, regime rules, and disabled throttle. Only a new style entry is screened. Reject the qualifying first-ranked candidate if its already-known next-month momentum rank is worse than 2. An existing holding is not screened merely because it is forecast to exit. Missing forecast ranks do not trigger rejection.

Primary fallback: retain the previous style ETF only if it still ranks in the current top two and passes the current 6m OR 12m cash hurdle; otherwise use the production IEF-or-cash defensive choice. Secondary fallback sensitivity: a rejected entry goes directly to that defensive choice. Neither version chooses a different new lower-ranked ETF.

The forecast is calculated from unshifted 3/6/12-month returns through the completed formation month. This equals the following month's ranking because the production ranking skips one month. No following-month ETF returns, cash hurdles, or realized holding durations are used by the filter. A next rank of 2 is allowed even though the leader-first selector may replace it next month.

Sector correlations and the congestion game are recalculated separately for each style path, including the changed 65% style exposure. Returns use the production daily simulator, next-trading-day closing execution, and cost per gross dollar traded, with buy and sell legs both charged. The primary cost is 10 bps; 0 and 25 bps are sensitivity checks, not optimized settings.

## Net results at 10 bps per traded leg

| Period | Strategy | CAGR | Sharpe | Daily max DD | Rejected entries | Style changes | Return months |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2001-2018 | Current strategy | 13.02% | 0.924 | -20.27% | 0 | 65 | 208 |
| 2001-2018 | Reject entry; retain eligible incumbent | 12.61% | 0.895 | -20.27% | 9 | 54 | 208 |
| 2001-2018 | Reject entry; use defensive holding | 12.24% | 0.876 | -20.27% | 10 | 61 | 208 |
| 2019-latest | Current strategy | 15.33% | 0.909 | -22.21% | 0 | 27 | 94 |
| 2019-latest | Reject entry; retain eligible incumbent | 15.49% | 0.921 | -22.26% | 4 | 22 | 94 |
| 2019-latest | Reject entry; use defensive holding | 15.69% | 0.939 | -20.54% | 4 | 26 | 94 |
| Full | Current strategy | 13.73% | 0.920 | -22.21% | 0 | 92 | 302 |
| Full | Reject entry; retain eligible incumbent | 13.50% | 0.904 | -22.26% | 13 | 76 | 302 |
| Full | Reject entry; use defensive holding | 13.30% | 0.897 | -20.54% | 14 | 87 | 302 |

Rejection and style-change counts cover formation dates within each labelled period that have executions in the cached sample; they include defensive transitions and, for style changes, the initial allocation. The latest October 2026 signal has no November 2 execution or holding return in this data and is excluded from those counts. Sharpe is excess of the repository's T-bill series; drawdown uses daily NAV with the preceding period-end NAV included as the starting value.

## Cost sensitivity, full period

| Cost per leg (bps) | Strategy | CAGR | Sharpe |
| --- | --- | --- | --- |
| 0 | Current strategy | 14.51% | 0.972 |
| 0 | Reject entry; retain eligible incumbent | 14.19% | 0.950 |
| 0 | Reject entry; use defensive holding | 14.06% | 0.948 |
| 10 | Current strategy | 13.73% | 0.920 |
| 10 | Reject entry; retain eligible incumbent | 13.50% | 0.904 |
| 10 | Reject entry; use defensive holding | 13.30% | 0.897 |
| 25 | Current strategy | 12.57% | 0.841 |
| 25 | Reject entry; retain eligible incumbent | 12.48% | 0.835 |
| 25 | Reject entry; use defensive holding | 12.18% | 0.820 |

## Paired uncertainty check

Circular 12-month moving-block bootstrap, 10,000 resamples, seed 20261102. Intervals describe the annualized arithmetic mean of paired monthly return differences at 10 bps, not a CAGR difference or a probability that a strategy is superior.

| Variant minus baseline | Period | Annualized mean difference | 95% block interval |
| --- | --- | --- | --- |
| Reject entry; retain eligible incumbent | 2001-2018 | -0.36% | [-0.97%, +0.15%] |
| Reject entry; retain eligible incumbent | 2019-latest | +0.14% | [-0.02%, +0.34%] |
| Reject entry; retain eligible incumbent | Full | -0.20% | [-0.64%, +0.14%] |
| Reject entry; use defensive holding | 2001-2018 | -0.72% | [-2.06%, +0.22%] |
| Reject entry; use defensive holding | 2019-latest | +0.30% | [-0.49%, +1.46%] |
| Reject entry; use defensive holding | Full | -0.40% | [-1.38%, +0.36%] |

## Latest formation: decision only

| Strategy | Its own incumbent | Candidate | Known next rank | Rejected? | Selected |
| --- | --- | --- | --- | --- | --- |
| Current strategy | IWD | QQQ | 3 | False | QQQ |
| Reject entry; retain eligible incumbent | IWD | QQQ | 3 | True | IWD |
| Reject entry; use defensive holding | IWD | QQQ | 3 | True | CASH |

Each counterfactual maintains its own incumbent history. Its latest holding is not necessarily what would result from adopting a new rule today while retaining the production account's current positions.

## Verification and limits

- The unfiltered research selector exactly matches the production style weights at every formation, and its net return path matches the end-to-end production strategy.
- Forecasts exactly match the next ranking across the historical sample. Truncating all inputs at December 2018 and March 2020 leaves all earlier decisions unchanged. Hypothetical +30% and -30% next-month returns leave the forecast known today unchanged.
- 2001-2018 is the repository's original development period. 2019+ is a later-period diagnostic, not a clean holdout: existing rules were examined against it, and this new question arose after observing the current QQQ signal. These are exploratory results, not fresh out-of-sample validation.
- Inputs are the same cached adjusted-price and FRED histories for all variants, not a point-in-time vintage database. Historical revisions and original publication delays are not reconstructed.
- The inherited simulator charges turnover across its position dictionary, including CASH changes, and its monthly-return series omits its initial partial month. These conventions are shared by all variants; the reported sample begins in 2001, after warm-up.
- This study does not change production strategy parameters, submit orders, or automatically promote the research filter.

## Reproduce

```bash
PYTHONDONTWRITEBYTECODE=1 python3 strategy/next_rank_entry_test.py
```

Input fingerprints:

- `strategy/data/prices.parquet`: `e55ba19dbfe6c7b197fd83241e3731f2ab0cd908e41f4b15e1c2c7c548d1d48b`
- `strategy/data/tbill_dgs3mo.parquet`: `a27b2dc9290a06759914d207153c236a7f33c89f926181cd87314f04a39f7a34`
- `strategy/strategy_lib.py`: `179179861d1376953909187d53ac465e88ec1044e63a6e9ccdd2e74df0b415a2`
