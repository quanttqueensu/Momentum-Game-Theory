"""
score_predictive_power.py -- IN-SAMPLE ONLY (2001-2018) descriptive check, no new strategy.

Question: does the production momentum score tell us anything about NEXT month?
This is a measurement, not a variant, so it adds no trial to the project's count.

Fixed before running:
  Score      = production S.composite (mean of 3/6/12m cross-sectional z-scores, skip 1).
  Next month = DI["exec_rets"] at t+1 (next-day-close execution, production convention).

  A. RANKING (cross-sectional): does a higher score mean a higher next-month return
     than the other ETFs in the same sleeve?
       - Rank IC: Spearman correlation of score vs next-month return, each month,
         across the sleeve (need >= 5 ETFs with data). Report mean, t-stat, % months > 0.
       - Top-k spread: next-month return of the top-k by score minus the sleeve's
         equal-weight mean (k = 1 for styles, 4 for sectors: what production holds,
         ignoring hurdle / crowding / buffer).
       - The same for each lookback alone (3m, 6m, 12m) to see what drives it.
  B. TREND (time-series): does an ETF that beat T-bills over the past 12 / 6 months
     beat T-bills next month more than one that didn't? This is what the T-bill hurdle uses.
     Pooled over the sleeve's ETFs; reported as mean next-month excess return over T-bills
     when trailing return > T-bills vs when it isn't.

  Periods: 2001-2018 (in-sample), and the two halves 2001-2009 / 2010-2018.
  t-stats on monthly series use Newey-West standard errors, 3 lags.

Run:  python research/scripts/score_predictive_power.py
Out:  research/tables/score_predictive_power/monthly_ic.csv
      research/tables/score_predictive_power/summary.csv
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "strategy"))  # for strategy_lib
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

import strategy_lib as S

HERE = os.path.dirname(os.path.abspath(__file__))
DI = S.get_data()
M, EX = DI["monthly"], DI["exec_rets"]
NXT = EX.shift(-1)                                  # return earned over month t+1
TB_NEXT = DI["tbill_m"].shift(-1)                   # T-bill over month t+1
PERIODS = {"2001-2018": ("2001-01-01", "2018-12-31"),
           "2001-2009": ("2001-01-01", "2009-12-31"),
           "2010-2018": ("2010-01-01", "2018-12-31")}
MIN_N = 5


def nw_t(x, lags=3):
    """Mean / Newey-West standard error."""
    x = pd.Series(x).dropna().values
    n = len(x)
    if n < 10:
        return np.nan
    e = x - x.mean()
    var = e @ e / n
    for L in range(1, lags + 1):
        var += 2 * (1 - L / (lags + 1)) * (e[L:] @ e[:-L]) / n
    return x.mean() / np.sqrt(var / n) if var > 0 else np.nan


def scores(cols):
    r = M[cols]
    return {"composite": S.composite(M, cols),
            "3m only": S.cs_z(S.mom(r, 1, 3)),
            "6m only": S.cs_z(S.mom(r, 1, 6)),
            "12m only": S.cs_z(S.mom(r, 1, 12))}


def monthly_ranking(sc, cols, k):
    """Per-month rank IC and top-k-minus-sleeve spread."""
    out = {}
    for t in sc.index:
        s, y = sc.loc[t, cols], NXT.loc[t, cols]
        ok = s.notna() & y.notna()
        if ok.sum() < MIN_N:
            continue
        s, y = s[ok], y[ok]
        top = s.sort_values(ascending=False).index[:k]
        out[t] = dict(ic=s.rank().corr(y.rank()), spread=y[top].mean() - y.mean(), n=int(ok.sum()))
    return pd.DataFrame(out).T


def summarize_ranking(df, a, b):
    d = df.loc[a:b]
    return dict(months=len(d), mean_IC=d.ic.mean(), t_IC=nw_t(d.ic), pct_IC_pos=(d.ic > 0).mean(),
                topk_spread_mo=d.spread.mean(), t_spread=nw_t(d.spread),
                topk_spread_ann=d.spread.mean() * 12)


def trend(cols, h, a, b):
    """Pooled: next-month excess over T-bills, split by trailing h-month return vs T-bills."""
    tot = DI["tot12"] if h == 12 else DI["tot6"]
    tb = DI["tbill12"] if h == 12 else DI["tbill6"]
    above = tot[cols].gt(tb, axis=0)
    valid = tot[cols].notna() & tb.notna().values[:, None] & NXT[cols].notna()
    xs = NXT[cols].sub(TB_NEXT, axis=0)
    sl = slice(a, b)
    # month-by-month average across ETFs in each group, so each month counts once
    up = xs.where(above & valid).loc[sl].mean(axis=1)
    dn = xs.where(~above & valid).loc[sl].mean(axis=1)
    diff = (up - dn).dropna()
    return dict(above_n=int((above & valid).loc[sl].values.sum()), below_n=int((~above & valid).loc[sl].values.sum()),
                xs_when_above_mo=up.mean(), xs_when_below_mo=dn.mean(),
                diff_mo=diff.mean(), t_diff=nw_t(diff), months_both=len(diff))


rows, ic_out = [], []
for sleeve, cols, k in [("STYLE", S.STYLES, 1), ("SECTOR", S.SECTORS, 4)]:
    for name, sc in scores(cols).items():
        df = monthly_ranking(sc, cols, k)
        ic_out.append(df.assign(sleeve=sleeve, score=name))
        for p, (a, b) in PERIODS.items():
            rows.append(dict(sleeve=sleeve, test="A ranking", score=name, period=p, k=k, **summarize_ranking(df, a, b)))
    for h in (12, 6):
        for p, (a, b) in PERIODS.items():
            rows.append(dict(sleeve=sleeve, test="B trend", score=f"{h}m vs T-bill", period=p, **trend(cols, h, a, b)))

summary = pd.DataFrame(rows)
ic_all = pd.concat(ic_out).rename_axis("month")
ic_all[ic_all.index <= "2018-12-31"].to_csv(os.path.join(HERE, "..", "tables", "score_predictive_power", "monthly_ic.csv"))
summary.to_csv(os.path.join(HERE, "..", "tables", "score_predictive_power", "summary.csv"), index=False)

pd.set_option("display.width", 200)
pct = lambda x: f"{x:+.2%}" if pd.notna(x) else "  n/a"
for sleeve in ["STYLE", "SECTOR"]:
    print("\n" + "=" * 100)
    print(f"{sleeve} sleeve -- A. RANKING (does a higher score beat the other ETFs next month?)")
    print("=" * 100)
    print(f"  {'score':<11}{'period':<11}{'months':>7}{'mean IC':>9}{'t':>7}{'% IC>0':>8}"
          f"{'top-k minus sleeve /mo':>24}{'t':>7}{'per yr':>9}")
    for _, r in summary[(summary.sleeve == sleeve) & (summary.test == "A ranking")].iterrows():
        print(f"  {r.score:<11}{r.period:<11}{r.months:>7.0f}{r.mean_IC:>9.3f}{r.t_IC:>7.2f}{r.pct_IC_pos:>8.0%}"
              f"{pct(r.topk_spread_mo):>24}{r.t_spread:>7.2f}{pct(r.topk_spread_ann):>9}")
    print(f"\n{sleeve} sleeve -- B. TREND (does beating T-bills over the past h months predict beating them next month?)")
    print(f"  {'signal':<15}{'period':<11}{'next-mo excess if above':>25}{'if below':>10}{'difference':>12}{'t':>7}{'obs above/below':>18}")
    for _, r in summary[(summary.sleeve == sleeve) & (summary.test == "B trend")].iterrows():
        print(f"  {r.score:<15}{r.period:<11}{pct(r.xs_when_above_mo):>25}{pct(r.xs_when_below_mo):>10}"
              f"{pct(r.diff_mo):>12}{r.t_diff:>7.2f}{f'{r.above_n}/{r.below_n}':>18}")
print(f"\nSaved -> {HERE}")
