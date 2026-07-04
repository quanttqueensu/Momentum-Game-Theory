"""
backtest.py  --  full backtest of THE strategy (IS 2001-18 | 2019+ | full).

Note: 2019+ is NOT clean OOS for this exact config (fast re-entry was chosen
after S11's one-shot OOS reveal; see README disclosures). It is shown because
the club needs honest full-cycle expectations, not as fresh statistical proof.
"""
import os
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
OOS_START = "2019-01-01"

print("[data] loading ...")
DI = S.get_data()

print("[run] the two-engine book ...")
r, st = S.build_strategy(DI=DI)

spy = DI["monthly"]["SPY"]
agg = DI["monthly"]["AGG"].where(DI["monthly"]["AGG"].notna(), DI["tbill_m"])
bal = (0.6 * spy + 0.4 * agg).dropna()
END = r.index.max()


def report(label, x, a, b):
    m = S.in_sample_mask(x.index, a, b)
    mt = S.metrics(x, m)
    xx = x[m].dropna()
    print(f"  {label:<28} Sharpe {mt['sharpe']:+5.2f}  ret {mt['ann_ret']:+6.1%}  "
          f"vol {mt['ann_vol']:5.1%}  DD {mt['max_dd']:+5.0%}  worst {xx.min():+6.1%}  "
          f"t {mt['tstat']:+5.2f}")


print("\n" + "=" * 96)
print("THE TWO-ENGINE BOOK  (65% style / 35% sector, both fast re-entry, 15% throttle)")
print("=" * 96)
for tag, a, b in [("IS  2001-2018", S.IS_START, S.IS_END),
                  ("2019 -> now", OOS_START, str(END.date())),
                  ("FULL 2001 ->", S.IS_START, str(END.date()))]:
    print(f"\n[{tag}]")
    report("Two-engine book", r, a, b)
    report("SPY buy-and-hold", spy, a, b)
    report("60/40", bal, a, b)

for tag, a, b in [("IS", S.IS_START, S.IS_END),
                  ("2019->", OOS_START, str(END.date()))]:
    rg = S.regret_vs_spy(r, DI, start=a, end=b)
    print(f"\n[club metrics vs SPY, {tag}]  worst 12m gap {rg['worst12']:+.1%}   "
          f"p(12m lag > 5pts) {rg['p_lag5']:.0%}   bull yrs {rg['bull_w']}/{rg['bull_n']}   "
          f"all yrs {rg['yrs_w']}/{rg['yrs_n']}")

# alpha/beta, full
df = pd.concat([r.rename("r"), spy.reindex(r.index).rename("b")], axis=1).dropna()
beta, alpha_m = np.polyfit(df["b"], df["r"], 1)
print(f"\n[full-cycle vs SPY]  alpha {alpha_m*12:+.1%}/yr   beta {beta:+.2f}   "
      f"monthly hit rate {(df['r'] > df['b']).mean():.0%}")

# calendar years with gaps -- the framing table
print(f"\n[calendar years]  gap = strategy - SPY   (B = SPY bull year > +15%)")
sp = spy.reindex(r.index).dropna()
sy = (1 + sp).groupby(sp.index.year).prod() - 1
print(f"{'year':<6}{'SPY':>9}{'strat':>9}{'gap':>9}")
gaps_bull = []
for y in sy.index:
    ry = (1 + r[r.index.year == y]).prod() - 1
    g = ry - sy[y]
    tag = " B" if sy[y] > 0.15 else "  "
    if sy[y] > 0.15:
        gaps_bull.append(g)
    print(f"{y:<6}{sy[y]:>9.1%}{ry:>9.1%}{g:>+9.1%}" + tag)
print(f"\nbull-year gaps: median {np.median(gaps_bull):+.1%}, "
      f"mean {np.mean(gaps_bull):+.1%}, range {min(gaps_bull):+.1%} .. {max(gaps_bull):+.1%} "
      f"({len(gaps_bull)} bull years)")

nav = st["nav"]
print(f"[daily-NAV max drawdown]  FULL {(nav / nav.cummax() - 1).min():+.1%}   "
      f"turnover {st['ann_turnover']:.1f}x/yr")

# ---- chart --------------------------------------------------------------------------
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9),
                               gridspec_kw={"height_ratios": [2.2, 1]})
for label, x, c, lw in [("Two-Engine Book", r, "#1f77b4", 2.4),
                        ("SPY", spy, "#d62728", 1.3),
                        ("60/40", bal, "#ff7f0e", 1.3)]:
    xx = x[x.index >= pd.Timestamp(S.IS_START)].dropna()
    ax1.plot((1 + xx).cumprod(), label=label, color=c, lw=lw)
ax1.axvline(pd.Timestamp(OOS_START), color="k", ls="--", lw=1, alpha=0.6)
ax1.set_yscale("log")
ax1.set_title("The Two-Engine Book, 2001 -> present (net 10 bps; dashed = 2019)")
ax1.set_ylabel("Growth of $1"); ax1.legend(loc="upper left"); ax1.grid(alpha=0.3)

for label, x, c in [("Book", r, "#1f77b4"), ("SPY", spy, "#d62728")]:
    xx = x[x.index >= pd.Timestamp(S.IS_START)].dropna()
    eq = (1 + xx).cumprod()
    ax2.fill_between(eq.index, eq / eq.cummax() - 1, 0, color=c, alpha=0.4, label=label)
ax2.axvline(pd.Timestamp(OOS_START), color="k", ls="--", lw=1, alpha=0.6)
ax2.set_title("Drawdown"); ax2.legend(); ax2.grid(alpha=0.3)
ax2.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"{x:.0%}"))

plt.tight_layout()
out = os.path.join(HERE, "backtest.png")
plt.savefig(out, dpi=150)
print(f"\nSaved -> {out}")
