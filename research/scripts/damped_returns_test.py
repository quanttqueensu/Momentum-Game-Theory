"""
damped_returns_test.py -- IN-SAMPLE ONLY (2001-2018) test of idea 1:
damp each ETF's monthly return before it enters the momentum score.

Rule (fixed before looking at results):
  cap each monthly return at +/- K * sigma, where sigma is that ETF's own
  std of monthly returns over the PRIOR 36 months (min 24; shifted one month so
  the month being damped never inflates its own scale). No history -> no damping.
  K = 2.0 is primary; 1.5 and 3.0 are sensitivity only, not to be picked from.

Scope: STYLE sleeve scores only. The T-bill hurdles (tot6/tot12), the sector
sleeve scores, regime rules and costs are all untouched production code.

Run:  python research/scripts/damped_returns_test.py
Out:  research/results/damped_returns_insample.png
"""
import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import warnings
warnings.filterwarnings("ignore")

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "strategy"))  # for strategy_lib
import strategy_lib as S

HERE = os.path.dirname(os.path.abspath(__file__))
PRIMARY_K = 2.0
SENS_K = (1.5, 3.0)
SIGMA_WIN, SIGMA_MIN = 36, 24

print("[data] loading ...")
DI = S.get_data()


def damp_monthly(monthly, k):
    sigma = monthly.rolling(SIGMA_WIN, min_periods=SIGMA_MIN).std().shift(1)
    cap = k * sigma
    out = monthly.clip(lower=-cap, upper=cap)        # NaN cap -> unchanged
    out = out.where(cap.notna(), monthly)
    return out


def run(k=None):
    """k=None -> production baseline. Returns (monthly returns, stats, style path)."""
    di = DI
    if k is not None:
        di = {**DI, "monthly": DAMPED[k]}            # style scores only; hurdles use tot6/tot12
    ps = S.style_weight_path(di)
    p6 = S.sector_weight_path(DI, ps)                # sector scores stay undamped
    wcomb = S.combine_paths([(ps, S.W_STYLE), (p6, S.W_SECTOR)])
    t_last = S.latest_formation(DI, ps, p6)
    wcomb = {t: w for t, w in wcomb.items() if t <= t_last}
    r, st = S.simulate(wcomb, DI)
    return r, st, ps


DAMPED = {k: damp_monthly(DI["monthly"][S.STYLES], k) for k in (PRIMARY_K,) + SENS_K}
# style_weight_path only reads DI["monthly"] via composite(STYLES); keep other cols intact
for k in DAMPED:
    full = DI["monthly"].copy()
    full[S.STYLES] = DAMPED[k]
    DAMPED[k] = full

print("[run] baseline + damped variants ...")
base_r, base_st, base_ps = run(None)
native, _ = S.build_strategy(DI=DI)
pd.testing.assert_series_equal(base_r, native)       # baseline == production
print("  baseline matches production build_strategy.")

variants = {"Current score": (base_r, base_st, base_ps)}
for k in (PRIMARY_K,) + SENS_K:
    variants[f"Damped k={k:g}"] = run(k)

spy = DI["monthly"]["SPY"]
agg = DI["monthly"]["AGG"].where(DI["monthly"]["AGG"].notna(), DI["tbill_m"])
bal = (0.6 * spy + 0.4 * agg).dropna()

A, B = S.IS_START, S.IS_END
mask = lambda x: S.in_sample_mask(x.index, A, B)


def style_changes(ps):
    ts = [t for t in sorted(ps) if A <= str(t.date()) <= B]
    held = [tuple(sorted(ps[t].index)) for t in ts]
    return sum(h != p for h, p in zip(held[1:], held[:-1]))


print("\n" + "=" * 100)
print(f"IN-SAMPLE {A[:4]}-{B[:4]}  (net {S.COST_BPS:.0f} bps; damping on style-sleeve scores only)")
print("=" * 100)
rows = []
for name, (r, st, ps) in variants.items():
    mt = S.metrics(r, mask(r))
    rows.append((name, mt, style_changes(ps)))
    print(f"  {name:<16} Sharpe {mt['sharpe']:+5.3f}  ret {mt['ann_ret']:+6.2%}  "
          f"vol {mt['ann_vol']:5.1%}  DD {mt['max_dd']:+6.1%}  Calmar {mt['calmar']:4.2f}  "
          f"style changes {style_changes(ps):>3}")
for label, x in [("SPY", spy), ("60/40", bal)]:
    m_ = S.in_sample_mask(x.index, A, B)
    mt = S.metrics(x, m_)
    print(f"  {label:<16} Sharpe {mt['sharpe']:+5.3f}  ret {mt['ann_ret']:+6.2%}  "
          f"vol {mt['ann_vol']:5.1%}  DD {mt['max_dd']:+6.1%}  Calmar {mt['calmar']:4.2f}")

print("\n[vs benchmarks, IS]  worst month / t-stat / calendar-year wins vs SPY")
for name, (r, _, _) in variants.items():
    m_ = mask(r)
    mt = S.metrics(r, m_)
    rg = S.regret_vs_spy(r, DI, start=A, end=B)
    print(f"  {name:<16} worst {r[m_].min():+6.1%}  t {mt['tstat']:+5.2f}  "
          f"worst 12m gap vs SPY {rg['worst12']:+.1%}  years beating SPY {rg['yrs_w']}/{rg['yrs_n']}")
for label, x in [("SPY", spy), ("60/40", bal)]:
    m_ = S.in_sample_mask(x.index, A, B)
    print(f"  {label:<16} worst {x[m_].min():+6.1%}  t {S.metrics(x, m_)['tstat']:+5.2f}")

# how much did damping actually change decisions / bind?
raw = DI["monthly"][S.STYLES]
d = DAMPED[PRIMARY_K][S.STYLES]
ism = S.in_sample_mask(raw.index, A, B)
bound = ((raw - d).abs() > 1e-12) & ism[:, None]
print(f"\n[binding, k={PRIMARY_K:g}] {int(bound.values.sum())} of "
      f"{int(raw.notna().values[ism].sum())} IS ETF-months clipped")
print(bound.sum().to_string())

dr = variants[f"Damped k={PRIMARY_K:g}"][0]
diff = (dr - base_r)[mask(base_r)].dropna()
print(f"\n[paired, k={PRIMARY_K:g} minus current] mean monthly diff {diff.mean()*12:+.2%}/yr annualized, "
      f"t {diff.mean()/(diff.std()/np.sqrt(len(diff))):+.2f}, "
      f"months differing >10bps: {(diff.abs() > 0.001).sum()}/{len(diff)}")

ps_b, ps_d = variants["Current score"][2], variants[f"Damped k={PRIMARY_K:g}"][2]
n_diff = sum(set(ps_b[t].index) != set(ps_d[t].index)
             for t in ps_b if t in ps_d and A <= str(t.date()) <= B)
print(f"[decisions] style holding differs from current in {n_diff} IS months")

# ---- chart (in-sample only) ----------------------------------------------------------
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), gridspec_kw={"height_ratios": [2.2, 1]})
styles = [("Current score", "#1f77b4", 2.4),
          (f"Damped k={PRIMARY_K:g}", "#2ca02c", 2.0),
          (f"Damped k={SENS_K[0]:g}", "#9467bd", 1.0),
          (f"Damped k={SENS_K[1]:g}", "#8c564b", 1.0)]
for name, c, lw in styles:
    x = variants[name][0]
    x = x[mask(x)].dropna()
    ax1.plot((1 + x).cumprod(), label=name, color=c, lw=lw)
for label, x, c in [("SPY", spy, "#d62728"), ("60/40", bal, "#ff7f0e")]:
    xx = x[S.in_sample_mask(x.index, A, B)].dropna()
    ax1.plot((1 + xx).cumprod(), label=label, color=c, lw=1.2, alpha=0.8)
ax1.set_yscale("log")
ax1.set_title("Damped monthly returns before scoring -- IN-SAMPLE 2001-2018 "
              "(style sleeve; net 10 bps;\nrebalance offset 0 of 4, single offset, not averaged)")
ax1.set_ylabel("Growth of $1"); ax1.legend(loc="upper left"); ax1.grid(alpha=0.3)

for name in ("Current score", f"Damped k={PRIMARY_K:g}"):
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
out = os.path.join(HERE, "..", "results", "damped_returns_insample.png")
plt.savefig(out, dpi=150)
print(f"\nSaved -> {out}")
