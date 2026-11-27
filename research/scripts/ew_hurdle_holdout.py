"""
ew_hurdle_holdout.py -- OUT-OF-SAMPLE (2019+) check of the "equal-weight passing" style sleeve.

Candidate (found by sleeve_split.py on 2002-2018; frozen exactly as there, nothing re-tuned):
  STYLE sleeve: each style ETF with a production score that month gets 1/N; it is held if it
  passes the production T-bill hurdle (12m OR 6m total return > T-bills), otherwise its slot
  goes to the production defensive pick (IEF if it beats T-bills, else cash). No ranking, no
  buffer. Everything else is production: 35% sector sleeve, 65/35 weights, 10 bps, simulator.

Rules (fixed before running):
  Holdout window: earned months 2019-01 .. 2026-10 (last complete month; the Nov-2026 stub
  is excluded as in production's latest_formation rule). 4 rebalance offsets (0/5/10/15).
  The candidate is CONFIRMED if, averaged over the 4 offsets, it has
    (1) a higher Sharpe than production, AND
    (2) a smaller (less negative) max drawdown than production.
  CAGR difference and the paired t-stat are reported but not required: ~94 months cannot
  confirm a small return difference, and the candidate is expected to earn somewhat less.
  The holdout is single-use for this candidate: whatever it shows is reported as is.
  Caveat: 2019+ was used for two earlier production decisions (strategy/README.md), so it is
  not perfectly clean for production; it has never been used for this candidate.

Run:  python research/scripts/ew_hurdle_holdout.py
Out:  research/results/ew_hurdle_holdout.png   (full history, dashed line = 2019, as backtest.png)
      research/tables/ew_hurdle_holdout/holdout.csv
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "strategy"))  # for strategy_lib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import warnings
warnings.filterwarnings("ignore")

import strategy_lib as S

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.path.join(HERE, "..", "tables", "ew_hurdle_holdout")
RESULTS = os.path.join(HERE, "..", "results")
os.makedirs(TABLES, exist_ok=True)

RAW = S.load_prices()
DI0 = S.get_data()
TB = DI0["tbill_m"]
OFFS = [0, 5, 10, 15]
PERIODS = {"HOLDOUT 2019-01..2026-10": ("2019-01-31", "2026-10-31"),
           "in-sample 2002-2018 (for reference)": ("2002-01-31", "2018-12-31"),
           "full 2002-01..2026-10": ("2002-01-31", "2026-10-31")}
_DIK = {}


def di_k(k):
    if k in _DIK:
        return _DIK[k]
    ck = RAW if k == 0 else RAW.iloc[:-k].copy()
    if k:
        ck.index = RAW.index[k:]
    orig = S.load_prices
    S.load_prices = lambda refresh=False: ck
    try:
        di = S.build_data()
    finally:
        S.load_prices = orig
    _DIK[k] = (di, ck)
    return _DIK[k]


def ew_hurdle_path(di):
    """Identical to sleeve_split.path(mode='ew_hurdle')."""
    scores = S.composite(di["monthly"], S.STYLES)
    out = {}
    for t in scores.index:
        row = scores.loc[t].dropna()
        if len(row) < 3:
            continue
        names = list(row.index)
        tb12, tb6 = di["tbill12"].get(t, np.nan), di["tbill6"].get(t, np.nan)
        passing = [a for a in names
                   if ((not np.isnan(tb12)) and di["tot12"].loc[t, a] > tb12)
                   or ((not np.isnan(tb6)) and di["tot6"].loc[t, a] > tb6)]
        w = pd.Series(1.0 / len(names), index=sorted(passing), dtype=float)
        d = 1.0 - float(w.sum())
        if d > 1e-9:
            dd = S.pick_defensive(di, t)
            w[dd] = w.get(dd, 0.0) + d
        out[t] = w
    return out


def run(di, ck, ps):
    p6 = S.sector_weight_path(di, ps)
    w = S.combine_paths([(ps, S.W_STYLE), (p6, S.W_SECTOR)])
    tl = S.latest_formation(di, ps, p6)
    w = {t: x for t, x in w.items() if t <= tl}
    _, st = S.simulate(w, di)
    nav = st["nav"].copy()
    nav.index = RAW.index[ck.index.get_indexer(nav.index)]
    return nav.resample("ME").last().pct_change().dropna()


def mx(r):
    e = (1 + r).cumprod()
    return (e / e.cummax() - 1).min()


res = {}
for k in OFFS:
    print(f"[offset {k}] running production and EW-hurdle ...", flush=True)
    di, ck = di_k(k)
    res["Production", k] = run(di, ck, S.style_weight_path(di))
    res["EW-hurdle", k] = run(di, ck, ew_hurdle_path(di))

prod_full, _ = S.build_strategy(DI=DI0)
j = res["Production", 0].index.intersection(prod_full.index)
print("  production offset-0 vs build_strategy, max abs diff:",
      float((res["Production", 0][j] - prod_full[j]).abs().max()))

rows = []
for p, (a, b) in PERIODS.items():
    print("\n" + "=" * 104)
    print(f"{p}  -- mean over 4 rebalance offsets")
    print("=" * 104)
    print(f"  {'variant':<12}{'months':>7}{'Sharpe':>8}{'CAGR':>8}{'vol':>7}{'MaxDD':>8}   Sharpe by offset          MaxDD by offset")
    stat = {}
    for n in ["Production", "EW-hurdle"]:
        rs = [res[n, k].loc[a:b] for k in OFFS]
        ms = [S.metrics(r, rf=TB) for r in rs]
        dds = [mx(r) for r in rs]
        stat[n] = dict(sh=np.mean([m["sharpe"] for m in ms]), cagr=np.mean([m["ann_ret"] for m in ms]),
                       vol=np.mean([m["ann_vol"] for m in ms]), dd=np.mean(dds))
        rows.append(dict(period=p, variant=n, months=len(rs[0]), **stat[n],
                         sharpe_by_offset=" ".join(f"{m['sharpe']:.3f}" for m in ms),
                         maxdd_by_offset=" ".join(f"{d:.1%}" for d in dds)))
        print(f"  {n:<12}{len(rs[0]):>7}{stat[n]['sh']:>8.3f}{stat[n]['cagr']:>8.2%}{stat[n]['vol']:>7.1%}"
              f"{stat[n]['dd']:>8.1%}   {' '.join(f'{m['sharpe']:.3f}' for m in ms):<26}"
              f"{' '.join(f'{d:.1%}' for d in dds)}")
    ts = []
    for k in OFFS:
        d = (res["EW-hurdle", k] - res["Production", k]).loc[a:b].dropna()
        ts.append(d.mean() / (d.std() / np.sqrt(len(d))))
    e, pr = stat["EW-hurdle"], stat["Production"]
    print(f"  EW-hurdle minus production: Sharpe {e['sh'] - pr['sh']:+.3f}, CAGR {e['cagr'] - pr['cagr']:+.2%}, "
          f"MaxDD {e['dd'] - pr['dd']:+.1%}, mean paired t {np.mean(ts):+.2f}")
    if p.startswith("HOLDOUT"):
        ok = e["sh"] > pr["sh"] and e["dd"] > pr["dd"]
        print(f"  HOLDOUT VERDICT: {'CONFIRMED' if ok else 'NOT CONFIRMED'} "
              f"(higher Sharpe: {e['sh'] > pr['sh']}, smaller max drawdown: {e['dd'] > pr['dd']})")
pd.DataFrame(rows).to_csv(os.path.join(TABLES, "holdout.csv"), index=False)

# ---- chart: full history, dashed line at 2019 (same layout as strategy/backtest.png) ----
a, b = PERIODS["full 2002-01..2026-10"]
spy = DI0["monthly"]["SPY"].loc[a:b]
agg = DI0["monthly"]["AGG"].where(DI0["monthly"]["AGG"].notna(), DI0["tbill_m"])
bal = (0.6 * DI0["monthly"]["SPY"] + 0.4 * agg).dropna().loc[a:b]
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), gridspec_kw={"height_ratios": [2.2, 1]})
for label, x, c, lw in [("Production", res["Production", 0].loc[a:b], "#1f77b4", 2.4),
                        ("EW-hurdle (equal-weight passing)", res["EW-hurdle", 0].loc[a:b], "#2ca02c", 2.0),
                        ("SPY", spy, "#d62728", 1.2), ("60/40", bal, "#ff7f0e", 1.2)]:
    ax1.plot((1 + x).cumprod(), label=label, color=c, lw=lw)
ax1.axvline(pd.Timestamp("2019-01-01"), color="k", ls="--", lw=1, alpha=0.6)
ax1.set_yscale("log")
ax1.set_title("Equal-weight passing style sleeve vs production, 2002 -> 2026-10 "
              "(net 10 bps; dashed = 2019 holdout start;\nrebalance offset 0 of 4, single offset; holdout.csv averages over 4)")
ax1.set_ylabel("Growth of $1"); ax1.legend(loc="upper left"); ax1.grid(alpha=0.3)
for label, x, c in [("Production", res["Production", 0].loc[a:b], "#b0b0b0"),
                    ("EW-hurdle", res["EW-hurdle", 0].loc[a:b], "#2ca02c")]:
    eq = (1 + x).cumprod()
    dd = eq / eq.cummax() - 1
    if label == "Production":
        ax2.fill_between(eq.index, dd, 0, color=c, alpha=0.7, label=label)
    else:
        ax2.plot(eq.index, dd, color=c, lw=1.8, label=label)
ax2.axvline(pd.Timestamp("2019-01-01"), color="k", ls="--", lw=1, alpha=0.6)
ax2.set_title("Drawdown: production (grey area) vs EW-hurdle (line); rebalance offset 0 of 4"); ax2.legend(); ax2.grid(alpha=0.3)
ax2.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v:.0%}"))
plt.tight_layout()
out = os.path.join(RESULTS, "ew_hurdle_holdout.png")
plt.savefig(out, dpi=150)
print(f"\nSaved -> {out}")
