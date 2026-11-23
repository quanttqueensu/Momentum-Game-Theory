# Sector Momentum Signal Research

**Status:** in-sample testing complete (2026-11-23). Holdout not run. Production unchanged.

## 1. Summary

This research tested whether a different momentum score could improve the 35% sector
sleeve of the Two-Engine Book. Neither idea seems to beat the production signal beyond noise.

- **Residual momentum (S1)** came closest. With the crowding penalty on, the 36-month
  version added +0.028 Sharpe over the common sample and +0.041 over its longest
  available history. Both are at or inside the 0.03 to 0.05 range treated as noise.
  -  With the crowding penalty off, the S1 36-month gain mostly disappeared: -0.009 over
  the common sample and +0.015 over its longest history.
- **Volatility-adjusted momentum (S2, S3, S4)** showed no reliable improvement.

## 2. What was tested

Only the sector sleeve's momentum score changed. The 65% style sleeve, crowding game
(including the 300-iteration budget), regime filter, top-4/top-6 rules, equal weights,
trading costs, and simulator are unchanged. `strategy_lib.py` was not edited.

Each horizon (3, 6, and 12 months) skips the most recent month. Each is z-scored across
sectors, then the three z-scores are averaged.

| Variant | Plain-language meaning | Measure used at each horizon |
|---|---|---|
| **S0** | Production baseline | Compounded return |
| **S1** | Sector performance after removing the market's influence | Sum of (sector return - beta x SPY return) |
| **S2** | Rewards steadier gains | Return / volatility over the same horizon |
| **S3** | Like S2, with one risk measure | Return / 12-month volatility |
| **S4** | Residual momentum, adjusted for steadiness | Residual sum / residual volatility over the same horizon |

S1 estimates beta with a no-intercept regression over the trailing 36 months (headline),
with 12 and 60 months as robustness checks. S4 uses the 36-month beta.

Every variant ran with `lam = 8` (production crowding penalty) and `lam = 0` (no
penalty), to separate the signal's effect from the penalty's.

## 3. Method and controls

**Baseline check.** The unmodified production strategy produced:

| Check | Expected | Result |
|---|---|---|
| In-sample Sharpe, 2001 to 2018 | about 0.924 | 0.9238 |
| Full-period Sharpe, through Oct 2026 | about 0.92 | 0.9200 |
| Turnover | about 6.9x/yr | 6.90x/yr |
| S0 research copy vs production | exact match | exact match |

Including the unfinished month of November 2026 lowers full-period Sharpe to 0.899, so
the full-period check uses the last completed month.

**Holdout protection.** Variants only received data through 2018-12-31, so they could
not produce 2019+ results.

**Look-ahead checks.** Removing all later data left every signal unchanged on six test
dates. A separate regression also reproduced the S1 36-month score on a test date.

**Warm-up.** Sector ETFs launched in 2000, so longer lookbacks become available later.
Until a variant has a valid score for all 11 sectors, the sleeve uses the production
score, and those months are excluded from that variant's evaluation.

**Significance.** Each variant is compared with the baseline using the same `lam` and
the same months. The 95% interval comes from a paired circular block bootstrap with
12-month blocks and 10,000 resamples.

## 4. Results (in-sample only)

### Common sample: August 2005 to December 2018 (161 months)

This is the like-for-like comparison. Delta is the Sharpe difference from S0.

**`lam = 8`**

| Variant | Sharpe | Delta | 95% interval | Return | Vol | Max DD | Turnover | Avg sectors | Months differing | Read |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---|
| S0 | 0.852 | | | 12.3% | 13.3% | -18.5% | 6.73x | 4.74 | 0.0% | Baseline |
| S1 12m | 0.859 | +0.007 | -0.028 to +0.039 | 12.3% | 13.2% | -18.4% | 6.79x | 4.81 | 62.7% | Noise |
| S1 36m | 0.880 | +0.028 | +0.001 to +0.055 | 12.6% | 13.1% | -18.5% | 6.68x | 4.73 | 56.5% | Noise |
| S1 60m | 0.893 | +0.041 | +0.015 to +0.067 | 12.7% | 13.1% | -18.2% | 6.70x | 4.79 | 56.5% | Borderline noise |
| S2 | 0.830 | -0.022 | -0.065 to +0.016 | 11.9% | 13.2% | -19.0% | 6.98x | 4.62 | 65.8% | Noise |
| S3 | 0.863 | +0.011 | -0.013 to +0.033 | 12.4% | 13.2% | -18.4% | 6.88x | 4.70 | 67.7% | Noise |
| S4 | 0.843 | -0.009 | -0.043 to +0.022 | 12.1% | 13.2% | -18.8% | 6.65x | 4.75 | 64.6% | Noise |

**`lam = 0`**

| Variant | Sharpe | Delta | 95% interval | Return | Vol | Max DD | Turnover | Avg sectors | Months differing | Read |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---|
| S0 | 0.843 | | | 12.4% | 13.6% | -19.0% | 6.85x | 4.77 | 0.0% | Baseline |
| S1 12m | 0.825 | -0.018 | -0.065 to +0.031 | 12.0% | 13.4% | -19.0% | 7.10x | 4.86 | 67.1% | Noise |
| S1 36m | 0.834 | -0.009 | -0.042 to +0.031 | 12.2% | 13.5% | -19.1% | 6.93x | 4.92 | 68.3% | Noise |
| S1 60m | 0.833 | -0.010 | -0.044 to +0.025 | 12.2% | 13.5% | -18.6% | 6.85x | 5.08 | 72.0% | Noise |
| S2 | 0.855 | +0.012 | -0.024 to +0.054 | 12.4% | 13.4% | -18.8% | 6.85x | 4.86 | 67.7% | Noise |
| S3 | 0.822 | -0.021 | -0.049 to +0.009 | 11.9% | 13.4% | -19.0% | 6.81x | 4.81 | 60.9% | Noise |
| S4 | 0.834 | -0.009 | -0.041 to +0.032 | 12.1% | 13.4% | -18.7% | 6.88x | 5.05 | 72.7% | Noise |

### Longest available history for each variant

Sharpe levels are only comparable within a row, because start dates differ.

| Variant | Start | Months | `lam = 8`: Sharpe vs S0 | Delta (95% interval) | `lam = 0`: Sharpe vs S0 | Delta (95% interval) |
|---|---|---:|---|---|---|---|
| S1 12m | 2001-09 | 208 | 0.945 vs 0.924 | +0.022 (-0.012 to +0.058) | 0.907 vs 0.901 | +0.006 (-0.040 to +0.057) |
| S1 36m | 2003-08 | 185 | 1.000 vs 0.959 | +0.041 (+0.011 to +0.073) | 0.947 vs 0.931 | +0.015 (-0.028 to +0.069) |
| S1 60m | 2005-08 | 161 | 0.893 vs 0.852 | +0.041 (+0.015 to +0.067) | 0.833 vs 0.843 | -0.010 (-0.044 to +0.025) |
| S2 | 2001-09 | 208 | 0.917 vs 0.924 | -0.006 (-0.046 to +0.032) | 0.922 vs 0.901 | +0.021 (-0.013 to +0.060) |
| S3 | 2001-09 | 208 | 0.946 vs 0.924 | +0.022 (-0.001 to +0.049) | 0.898 vs 0.901 | -0.003 (-0.033 to +0.033) |
| S4 | 2003-08 | 185 | 0.968 vs 0.959 | +0.008 (-0.029 to +0.048) | 0.936 vs 0.931 | +0.005 (-0.031 to +0.051) |

## 5. Analysis

S1 with a 36-month beta was the headline residual momentum test. At `lam = 8`, it added
0.028 Sharpe over the common sample and 0.041 over its longest available history. The
common-sample interval runs from +0.001 to +0.055, so the gain is too small to separate
from noise at this sample size. S1 with a 60-month beta also measured +0.041 in the
common sample, but that window was included as a robustness check.

The study made 12 variant comparisons (six signals at two `lam` values), so one or two
intervals could exclude zero by chance. The two S1 intervals that exclude zero in the
common sample also come from closely related signals and should not be counted as
independent evidence.

The S1 gain only appears with the crowding penalty on. At `lam = 0`, S1 36m changed
Sharpe by -0.009 over the common sample and +0.015 over its longest history, and S1 60m
changed it by -0.010. These tests do not explain why the two interact.

The signal changed holdings much more than it changed performance. At `lam = 8`, S1 36m
held a different set of sectors from S0 in 56.5% of common-sample months, while annual
return moved from 12.3% to 12.6% and max drawdown stayed at -18.5%.

The common sample starts in August 2005, and S1 36m's longest history starts in August
2003. Neither includes the 2001 to 2002 portion of the dot-com bear market, so S1 36m
has not been tested through that drawdown.

## 6. Implementation choices

- S2 and S3 volatility skips the latest month, matching the return window.
- S4 uses residual volatility over each horizon (3, 6, or 12 months).
- The final score stays the average of three z-scores, as in production. Re-scaling it
  would break the exact S0 match. Average score spread stays comparable: 0.82 to 0.88
  across variants, against 0.85 for S0.
- One beta is estimated at each formation date and applied to that date's residual
  window.

## 7. Holdout status

The holdout period, January 2019 to October 2026, has not been run for any variant.

Two limits apply to this period:

- 2019+ is not perfectly clean, because some production rules were chosen with knowledge
  of that period.
- About 94 months is too short to reliably confirm a gain as small as 0.03 Sharpe.

## 8. Files and reproduction

| File | Purpose |
|---|---|
| `strategy/sector_signal_research.py` | Runs all checks and variants |
| `strategy/sector_signal_output/in_sample_results.csv` | Full results table |
| `strategy/sector_signal_output/score_dispersion.csv` | Average spread of each final score |

From the `strategy/` folder:

```
python sector_signal_research.py
```

Run on commit `602e047`, with prices and T-bill data downloaded on 2026-11-23. The data
files are gitignored, and Yahoo's adjusted prices can change slightly between downloads.
The environment used `yfinance` 0.2.66 and `numpy` 2.3.4, while `requirements.txt` pins
1.4.1 and 2.4.0.
