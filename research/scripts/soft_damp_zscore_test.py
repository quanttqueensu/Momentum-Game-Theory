"""
soft_damp_zscore_test.py -- IN-SAMPLE ONLY (2001-2018) test of idea 2:
soft-damp each lookback's cross-sectional z-score before the 3/6/12m average.

Rule (fixed before looking at results):
  z' = C * tanh(z / C)   applied to the 3m, 6m and 12m z-scores separately,
  then averaged as in production. Near zero z' ~ z, extreme z is squeezed toward +/-C.
  C = 1.5 is primary; 1.0 and 2.0 are sensitivity only, not to be picked from.

Scope: STYLE sleeve scores only. T-bill hurdles, sector scores, regime rules and
costs are untouched production code.

Run:  python research/scripts/soft_damp_zscore_test.py
Out:  research/results/soft_damp_zscore_insample.png
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
PRIMARY_C = 1.5
SENS_C = (1.0, 2.0)

print("[data] loading ...")
DI = S.get_data()


def damped_composite(c):
    def comp(monthly, cols):
        r = monthly[cols]
        zs = [S.cs_z(S.mom(r, 1, h)) for h in (3, 6, 12)]
        return sum(c * np.tanh(z / c) for z in zs) / 3
    return comp


def run(c=None):
    """c=None -> production baseline. Damping is swapped in for the STYLE path only."""
    orig = S.composite
    try:
        if c is not None:
            S.composite = damped_composite(c)
        ps = S.style_weight_path(DI)
    finally:
        S.composite = orig                           # sector sleeve always uses production scores
    p6 = S.sector_weight_path(DI, ps)
    wcomb = S.combine_paths([(ps, S.W_STYLE), (p6, S.W_SECTOR)])
    t_last = S.latest_formation(DI, ps, p6)
    wcomb = {t: w for t, w in wcomb.items() if t <= t_last}
    r, st = S.simulate(wcomb, DI)
    return r, st, ps


print("[run] baseline + damped variants ...")
base = run(None)
native, _ = S.build_strategy(DI=DI)
pd.testing.assert_series_equal(base[0], native)      # baseline == production
print("  baseline matches production build_strategy.")

variants = {"Current score": base}
for c in (PRIMARY_C,) + SENS_C:
    variants[f"tanh c={c:g}"] = run(c)

spy = DI["monthly"]["SPY"]
agg = DI["monthly"]["AGG"].where(DI["monthly"]["AGG"].notna(), DI["tbill_m"])
bal = (0.6 * spy + 0.4 * agg).dropna()

A, B = S.IS_START, S.IS_END
mask = lambda x: S.in_sample_mask(x.index, A, B)
PNAME = f"tanh c={PRIMARY_C:g}"


def style_changes(ps):
    ts = [t for t in sorted(ps) if A <= str(t.date()) <= B]
    held = [tuple(sorted(ps[t].index)) for t in ts]
    return sum(h != p for h, p in zip(held[1:], held[:-1]))


print("\n" + "=" * 100)
print(f"IN-SAMPLE {A[:4]}-{B[:4]}  (net {S.COST_BPS:.0f} bps; z-score damping on style-sleeve scores only)")
print("=" * 100)
for name, (r, st, ps) in variants.items():
    mt = S.metrics(r, mask(r))
    print(f"  {name:<16} Sharpe {mt['sharpe']:+5.3f}  ret {mt['ann_ret']:+6.2%}  "
          f"vol {mt['ann_vol']:5.1%}  DD {mt['max_dd']:+6.1%}  Calmar {mt['calmar']:4.2f}  "
          f"style changes {style_changes(ps):>3}")
for label, x in [("SPY", spy), ("60/40", bal)]:
    mt = S.metrics(x, S.in_sample_mask(x.index, A, B))
    print(f"  {label:<16} Sharpe {mt['sharpe']:+5.3f}  ret {mt['ann_ret']:+6.2%}  "
          f"vol {mt['ann_vol']:5.1%}  DD {mt['max_dd']:+6.1%}  Calmar {mt['calmar']:4.2f}")

print("\n[vs benchmarks, IS]  worst month / t-stat / worst 12m gap / calendar years beating SPY")
for name, (r, _, _) in variants.items():
    m_ = mask(r)
    mt = S.metrics(r, m_)
    rg = S.regret_vs_spy(r, DI, start=A, end=B)
    print(f"  {name:<16} worst {r[m_].min():+6.1%}  t {mt['tstat']:+5.2f}  "
          f"worst 12m gap {rg['worst12']:+.1%}  years beating SPY {rg['yrs_w']}/{rg['yrs_n']}")
for label, x in [("SPY", spy), ("60/40", bal)]:
    m_ = S.in_sample_mask(x.index, A, B)
    print(f"  {label:<16} worst {x[m_].min():+6.1%}  t {S.metrics(x, m_)['tstat']:+5.2f}")

# how often does damping bind?
r_ = DI["monthly"][S.STYLES]
ism = S.in_sample_mask(r_.index, A, B)
zs = [S.cs_z(S.mom(r_, 1, h)) for h in (3, 6, 12)]
tot = sum(int(z.notna().values[ism].sum()) for z in zs)
beyond = sum(int((z.abs() > PRIMARY_C).values[ism].sum()) for z in zs)
print(f"\n[binding, c={PRIMARY_C:g}] {beyond} of {tot} IS z-scores have |z| > c")

dr = variants[PNAME][0]
diff = (dr - base[0])[mask(base[0])].dropna()
print(f"[paired, c={PRIMARY_C:g} minus current] {diff.mean()*12:+.2%}/yr, "
      f"t {diff.mean()/(diff.std()/np.sqrt(len(diff))):+.2f}, "
      f"months differing >10bps: {(diff.abs() > 0.001).sum()}/{len(diff)}")
ps_b, ps_d = base[2], variants[PNAME][2]
n_diff = sum(set(ps_b[t].index) != set(ps_d[t].index)
             for t in ps_b if t in ps_d and A <= str(t.date()) <= B)
print(f"[decisions] style holding differs from current in {n_diff} IS months")

# ---- chart (in-sample only) ----------------------------------------------------------
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), gridspec_kw={"height_ratios": [2.2, 1]})
for name, c, lw in [("Current score", "#1f77b4", 2.4), (PNAME, "#2ca02c", 2.0),
                    (f"tanh c={SENS_C[0]:g}", "#9467bd", 1.0),
                    (f"tanh c={SENS_C[1]:g}", "#8c564b", 1.0)]:
    x = variants[name][0]
    x = x[mask(x)].dropna()
    ax1.plot((1 + x).cumprod(), label=name, color=c, lw=lw)
for label, x, c in [("SPY", spy, "#d62728"), ("60/40", bal, "#ff7f0e")]:
    xx = x[S.in_sample_mask(x.index, A, B)].dropna()
    ax1.plot((1 + xx).cumprod(), label=label, color=c, lw=1.2, alpha=0.8)
ax1.set_yscale("log")
ax1.set_title("Soft-damped z-scores (tanh) before averaging -- IN-SAMPLE 2001-2018 "
              "(style sleeve; net 10 bps;\nrebalance offset 0 of 4, single offset, not averaged)")
ax1.set_ylabel("Growth of $1"); ax1.legend(loc="upper left"); ax1.grid(alpha=0.3)

for name in ("Current score", PNAME):
    x = variants[name][0]
    x = x[S.in_sample_mask(x.index, A, B)].dropna()
    eq = S.equity_curve(x)
    dd = eq / eq.cummax() - 1
    if name == "Current score":
        ax2.fill_between(eq.index, dd, 0, color="#b0b0b0", alpha=0.7, label="Production (current score)")
    else:
        ax2.plot(eq.index, dd, color="#2ca02c", lw=1.8, label=name)
ax2.set_title("Drawdown: production (grey area) vs new idea (line); rebalance offset 0 of 4"); ax2.legend(); ax2.grid(alpha=0.3)
ax2.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v:.0%}"))

plt.tight_layout()
out = os.path.join(HERE, "..", "results", "soft_damp_zscore_insample.png")
plt.savefig(out, dpi=150)
print(f"\nSaved -> {out}")
