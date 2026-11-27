"""
factor_momentum_test.py -- factor momentum for the 65% STYLE sleeve.
IN-SAMPLE ONLY: French factor data up to 1999 (fresh), ETFs 2001-2018. 2019+ untouched.

Idea (Arnott, Kalesnik & Linnainmaa, "Factor Momentum", RFS 2023): style ETFs are a few
bets on factors (growth vs value, small vs large, international vs US). Instead of ranking
the 7 ETFs against each other, follow each factor SPREAD's own trend and build the pick
from the tilts that are winning. The paper finds factor momentum works best on 1-12 month
lookbacks that INCLUDE the latest month.

Rules (fixed before running):

  STAGE A -- does factor momentum work on data the repo never touched? (Kenneth French)
    Spreads: SMB (small - big), HML (value - growth),
             Developed ex-US market - US market, Emerging market - Developed ex-US market.
    Signal:  sign of the spread's summed return over the past 12 months, INCLUDING month t.
    Timing return at t+1 = sign(signal_t) x spread_{t+1}.
    PRIMARY sample for SMB and HML: 1963-07 to 1999-12 (pre-ETF, never used by the repo).
    "Supported" = mean timing return > 0 with Newey-West t >= 2.
    Shown for context only: 1927-1962, 2000-2018 and by decade. International spreads exist
    only from 1990/91, so they overlap the ETF era and are context, not pass/fail.

  STAGE B -- does it pick a better style ETF? (ETF backtest, full production strategy)
    Same spreads built from the ETFs themselves (h-month compounded return differences):
        i = EFA - SPY   (international vs US)     e = EEM - EFA   (emerging vs developed)
        s = IWM - SPY   (small vs large)          g = IWF - IWD   (growth vs value)
        q = QQQ - IWF   (Nasdaq-100 vs broad growth)
    Pick (decision tree, ties/negative -> second branch; missing data -> skip that branch):
        if i > 0:   EEM if e > 0 else EFA                 (international)
        elif s > 0: IWM                                   (US small)
        elif g > 0: QQQ if q > 0 else IWF                 (US large growth)
        else:       IWD                                   (US large value)
    Runner-up (used only by the production incumbency buffer) = the other leaf at the last
    split taken (IWM's runner-up = what the US-large branch would pick).
    SPY is never the pick; it is the neutral blend of the tilts.
    Everything else is production: T-bill hurdle (12m OR 6m), IEF/cash fallback, buffer,
    the 35% sector sleeve, 65/35 weights, 10 bps costs, simulator. strategy_lib untouched.

    PRIMARY:     12-month lookback, no skip (as in the paper).
    Sensitivity: 6-month no skip; 12-month skipping 1 month. Reported, NOT to be picked from.

    Pass bar (same as high_score_penalty_test), 2002-2018, 4 rebalance offsets (0/5/10/15
    trading days before month-end): beats production on mean Sharpe AND CAGR across offsets,
    wins on >= 3 of 4 offsets, higher CAGR in both 2002-09 and 2010-18, mean paired t >= 2.

  Trials added: 3 (1 primary + 2 sensitivities).

Run:  python research/scripts/factor_momentum_test.py
Out:  research/results/factor_momentum_insample.png   (ETF backtest)
      research/results/factor_momentum_french.png     (Stage A)
      research/tables/factor_momentum/stage_a_french.csv, stage_b_offsets.csv
Data: research/data/french/  (Kenneth French data library CSVs,
      downloaded 2026-11-25 from mba.tuck.dartmouth.edu/pages/faculty/ken.french/)
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
FD = os.path.join(HERE, "..", "data", "french")


def nw_t(x, lags=3):
    x = pd.Series(x).dropna().values
    n = len(x)
    if n < 10:
        return np.nan
    e = x - x.mean()
    var = e @ e / n
    for L in range(1, lags + 1):
        var += 2 * (1 - L / (lags + 1)) * (e[L:] @ e[:-L]) / n
    return x.mean() / np.sqrt(var / n) if var > 0 else np.nan


# =====================================================================================
# STAGE A -- French factors
# =====================================================================================
def read_french(fname):
    """Monthly block of a French data-library CSV -> DataFrame of decimal returns."""
    with open(os.path.join(FD, fname), encoding="latin-1") as f:
        lines = f.read().splitlines()
    i = next(k for k, l in enumerate(lines) if l.startswith(","))
    cols = [c.strip() for c in lines[i].split(",")[1:]]
    rows = {}
    for l in lines[i + 1:]:
        parts = [p.strip() for p in l.split(",")]
        if not (parts[0].isdigit() and len(parts[0]) == 6):
            break
        rows[pd.Period(f"{parts[0][:4]}-{parts[0][4:]}", "M")] = [float(p) for p in parts[1:]]
    df = pd.DataFrame.from_dict(rows, orient="index", columns=cols).replace(-99.99, np.nan) / 100
    df.index = df.index.to_timestamp("M")
    return df


us = read_french("F-F_Research_Data_Factors.csv")
dev = read_french("Developed_ex_US_3_Factors.csv")
em = read_french("Emerging_5_Factors.csv")
SPREADS = {
    "SMB (small - big)": us["SMB"],
    "HML (value - growth)": us["HML"],
    "Developed ex-US - US": (dev["Mkt-RF"] - us["Mkt-RF"]).dropna(),
    "Emerging - Developed ex-US": (em["Mkt-RF"] - dev["Mkt-RF"]).dropna(),
}


def timing(x, h=12):
    sig = np.sign(x.rolling(h).sum())          # includes month t
    return (sig * x.shift(-1)).dropna()        # earned over t+1, indexed at t


A_PERIODS = [("1927-1962 (context)", "1927-01-01", "1962-12-31"),
             ("1963-1999 PRIMARY", "1963-07-01", "1999-12-31"),
             ("2000-2018 (ETF era)", "2000-01-01", "2018-12-31")]
rowsA = []
print("=" * 104)
print("STAGE A -- factor momentum on French data (12m sign incl. latest month -> next-month spread)")
print("=" * 104)
print(f"  {'spread':<28}{'period':<22}{'months':>7}{'timing /yr':>12}{'t':>7}{'% right':>9}"
      f"{'buy&hold /yr':>14}{'signal>0':>10}")
TIM = {}
for name, x in SPREADS.items():
    tr = timing(x)
    TIM[name] = tr
    periods = A_PERIODS if name.startswith(("SMB", "HML")) else [("1991-2018 (context)", "1991-01-01", "2018-12-31")]
    for p, a, b in periods:
        d = tr.loc[a:b]
        if len(d) < 24:
            continue
        nxt = x.shift(-1).loc[d.index]
        sig = np.sign(x.rolling(12).sum()).loc[d.index]
        row = dict(spread=name, period=p, months=len(d), timing_ann=d.mean() * 12, t=nw_t(d),
                   pct_right=(d > 0).mean(), buyhold_ann=nxt.mean() * 12, pct_signal_pos=(sig > 0).mean())
        rowsA.append(row)
        print(f"  {name:<28}{p:<22}{row['months']:>7}{row['timing_ann']:>+12.2%}{row['t']:>7.2f}"
              f"{row['pct_right']:>9.0%}{row['buyhold_ann']:>+14.2%}{row['pct_signal_pos']:>10.0%}")
print("\n  by decade (timing return /yr, t):")
for name in ["SMB (small - big)", "HML (value - growth)"]:
    tr = TIM[name]
    parts = []
    for dec in range(1930, 2020, 10):
        d = tr.loc[f"{dec}-01-01":f"{dec + 9}-12-31"]
        if len(d) > 24:
            parts.append(f"{dec}s {d.mean() * 12:+.1%} ({nw_t(d):+.1f})")
            rowsA.append(dict(spread=name, period=f"{dec}s", months=len(d), timing_ann=d.mean() * 12, t=nw_t(d)))
    print(f"  {name:<22} " + "  ".join(parts))
pd.DataFrame(rowsA).to_csv(os.path.join(HERE, "..", "tables", "factor_momentum", "stage_a_french.csv"), index=False)
for name in ["SMB (small - big)", "HML (value - growth)"]:
    r = next(r for r in rowsA if r["spread"] == name and r["period"] == "1963-1999 PRIMARY")
    print(f"  STAGE A verdict {name}: {'SUPPORTED' if r['timing_ann'] > 0 and r['t'] >= 2 else 'not supported'}"
          f" (timing {r['timing_ann']:+.2%}/yr, t {r['t']:.2f})")

# Stage A chart
fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 9))
for name, c in [("SMB (small - big)", "#1f77b4"), ("HML (value - growth)", "#d62728")]:
    tr = TIM[name].loc["1927-01-01":"2018-12-31"]
    a1.plot((1 + tr).cumprod(), label=f"{name}: follow 12m trend", color=c, lw=2)
    bh = SPREADS[name].shift(-1).loc[tr.index]
    a1.plot((1 + bh).cumprod(), label=f"{name}: always long", color=c, lw=1, ls="--", alpha=0.7)
a1.axvspan(pd.Timestamp("1963-07-01"), pd.Timestamp("1999-12-31"), color="grey", alpha=0.12,
           label="primary test window 1963-1999")
a1.set_yscale("log"); a1.grid(alpha=0.3); a1.legend(loc="upper left", fontsize=9)
a1.set_title("Stage A: US factor momentum (Kenneth French data), growth of $1 in the long-short spread (monthly data; no rebalance offset applies)")
for name, c in [("Developed ex-US - US", "#2ca02c"), ("Emerging - Developed ex-US", "#9467bd")]:
    tr = TIM[name].loc["1991-01-01":"2018-12-31"]
    a2.plot((1 + tr).cumprod(), label=f"{name}: follow 12m trend", color=c, lw=2)
    bh = SPREADS[name].shift(-1).loc[tr.index]
    a2.plot((1 + bh).cumprod(), label=f"{name}: always long", color=c, lw=1, ls="--", alpha=0.7)
a2.set_yscale("log"); a2.grid(alpha=0.3); a2.legend(loc="upper left", fontsize=9)
a2.set_title("International spreads 1991-2018 (context only: overlaps the ETF era)")
plt.tight_layout()
plt.savefig(os.path.join(HERE, "..", "results", "factor_momentum_french.png"), dpi=150)
plt.close(fig)

# =====================================================================================
# STAGE B -- ETF backtest of the style sleeve
# =====================================================================================
print("\n[data] loading ETF data and building 4 rebalance offsets ...")
RAW = S.load_prices()
DI0 = S.get_data()
TB = DI0["tbill_m"]
OFFS = [0, 5, 10, 15]
W0, W1, WM = pd.Timestamp("2002-01-31"), pd.Timestamp("2018-12-31"), pd.Timestamp("2009-12-31")
_DIK = {}


def di_k(k):
    """Data built as if every month ended k trading days earlier (same as high_score_penalty_test)."""
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


def tree_score(h, skip):
    """Score frame for S.STYLES: pick = 2, runner-up = 1, other ETFs with data = 0."""
    def f(m, cols):
        R = {a: S.mom(m[a], skip, h) for a in cols}
        i, e = R["EFA"] - R["SPY"], R["EEM"] - R["EFA"]
        s, g, q = R["IWM"] - R["SPY"], R["IWF"] - R["IWD"], R["QQQ"] - R["IWF"]
        out = pd.DataFrame(np.nan, index=m.index, columns=cols)
        for t in m.index:
            if any(pd.isna(v.loc[t]) for v in (s, g, q)):
                continue
            if g.loc[t] > 0:
                large, large_ru = ("QQQ", "IWF") if q.loc[t] > 0 else ("IWF", "QQQ")
            else:
                large, large_ru = "IWD", ("QQQ" if q.loc[t] > 0 else "IWF")
            us_pick, us_ru = ("IWM", large) if s.loc[t] > 0 else (large, large_ru)
            if pd.notna(i.loc[t]) and i.loc[t] > 0:
                if pd.notna(e.loc[t]) and e.loc[t] > 0:
                    pick, ru = "EEM", "EFA"
                else:
                    pick, ru = "EFA", ("EEM" if pd.notna(e.loc[t]) else us_pick)
            else:
                pick, ru = us_pick, us_ru
            have = [a for a in cols if pd.notna(R[a].loc[t])]
            out.loc[t, have] = 0.0
            out.loc[t, ru] = 1.0
            out.loc[t, pick] = 2.0
        return out
    return f


VARS = {"Current score": None,
        "Factor mom 12m (PRIMARY)": tree_score(12, 0),
        "Factor mom 6m (sens.)": tree_score(6, 0),
        "Factor mom 12m skip1 (sens.)": tree_score(12, 1)}
PRIMARY = "Factor mom 12m (PRIMARY)"


def run(name, k):
    di, ck = di_k(k)
    orig = S.composite
    try:
        if VARS[name] is not None:
            S.composite = VARS[name]           # style sleeve only
        ps = S.style_weight_path(di)
    finally:
        S.composite = orig
    p6 = S.sector_weight_path(di, ps)          # sector sleeve: production score
    w = S.combine_paths([(ps, S.W_STYLE), (p6, S.W_SECTOR)])
    tl = S.latest_formation(di, ps, p6)
    w = {t: x for t, x in w.items() if t <= min(tl, pd.Timestamp(S.IS_END))}
    _, st = S.simulate(w, di)
    nav = st["nav"].copy()
    nav.index = RAW.index[ck.index.get_indexer(nav.index)]
    return nav.resample("ME").last().pct_change().dropna(), ps, st["ann_turnover"]


print("[run] 4 variants x 4 offsets ...")
res = {(n, k): run(n, k) for n in VARS for k in OFFS}
prod, _ = S.build_strategy(DI=DI0, end=S.IS_END)
j = res["Current score", 0][0].index.intersection(prod.index)
print("  baseline offset-0 vs production build_strategy, max abs diff:",
      float((res["Current score", 0][0][j] - prod[j]).abs().max()))

win = lambda r: r[(r.index >= W0) & (r.index <= W1)]


def mx(r):
    e = (1 + r).cumprod()
    return (e / e.cummax() - 1).min()


print("\n" + "=" * 118)
print("STAGE B -- full strategy, style-sleeve pick changed only; 2002-2018, mean over 4 rebalance offsets")
print("=" * 118)
print(f"  {'variant':<30}{'Sharpe':>8}{'CAGR':>8}{'MaxDD':>8}{'dSharpe':>9}{'dCAGR':>8}{'wins':>6}"
      f"{'d02-09':>8}{'d10-18':>8}{'t':>7}{'dMaxDD':>8}{'turnover':>10}  verdict")
rowsB = []
for n in VARS:
    sh, cg, dd, dS, dC, wins, dA, dB, ts, dD, tov = [], [], [], [], [], 0, [], [], [], [], []
    for k in OFFS:
        b, v = win(res["Current score", k][0]), win(res[n, k][0])
        mb, mv = S.metrics(b, rf=TB), S.metrics(v, rf=TB)
        sh.append(mv["sharpe"]); cg.append(mv["ann_ret"]); dd.append(mx(v)); tov.append(res[n, k][2])
        dS.append(mv["sharpe"] - mb["sharpe"]); dC.append(mv["ann_ret"] - mb["ann_ret"])
        wins += (dS[-1] > 1e-6) and (dC[-1] > 1e-6)
        d = v - b
        ts.append(d.mean() / (d.std() / np.sqrt(len(d))) if d.std() > 0 else 0.0)
        h1 = b.index <= WM
        dA.append(S.metrics(v[h1], rf=TB)["ann_ret"] - S.metrics(b[h1], rf=TB)["ann_ret"])
        dB.append(S.metrics(v[~h1], rf=TB)["ann_ret"] - S.metrics(b[~h1], rf=TB)["ann_ret"])
        dD.append(mx(v) - mx(b))
    base = n == "Current score"
    ok = (not base) and np.mean(dS) > 0 and np.mean(dC) > 0 and wins >= 3 \
        and np.mean(dA) > 0 and np.mean(dB) > 0 and np.mean(ts) >= 2
    rowsB.append(dict(variant=n, sharpe=np.mean(sh), cagr=np.mean(cg), max_dd=np.mean(dd),
                      d_sharpe=np.mean(dS), d_cagr=np.mean(dC), wins=wins, d_cagr_0209=np.mean(dA),
                      d_cagr_1018=np.mean(dB), paired_t=np.mean(ts), d_max_dd=np.mean(dD),
                      turnover=np.mean(tov), sharpe_by_offset=[round(x, 3) for x in sh],
                      verdict="baseline" if base else ("PASS" if ok else "fail")))
    print(f"  {n:<30}{np.mean(sh):>8.3f}{np.mean(cg):>8.2%}{np.mean(dd):>8.1%}"
          + ("" if base else f"{np.mean(dS):>+9.3f}{np.mean(dC):>+8.2%}{wins:>4}/4{np.mean(dA):>+8.2%}"
             f"{np.mean(dB):>+8.2%}{np.mean(ts):>+7.2f}{np.mean(dD):>+8.1%}")
          + (f"{'':>62}" if base else "") + f"{np.mean(tov):>9.1f}x  {rowsB[-1]['verdict']}")
pd.DataFrame(rowsB).to_csv(os.path.join(HERE, "..", "tables", "factor_momentum", "stage_b_offsets.csv"), index=False)

# what does the style sleeve actually hold? (offset 0, in-sample)
A, B = S.IS_START, S.IS_END
print("\n[style sleeve holdings, offset 0, 2001-2018: share of months]")
hold = {}
for n in VARS:
    ps = res[n, 0][1]
    ts_ = [t for t in sorted(ps) if A <= str(t.date()) <= B]
    hold[n] = pd.Series([ps[t].idxmax() for t in ts_ if len(ps[t])], index=[t for t in ts_ if len(ps[t])])
tab = pd.DataFrame({n: h.value_counts(normalize=True) for n, h in hold.items()}).fillna(0)
print(tab.reindex(S.STYLES + ["IEF", "CASH"]).fillna(0).map(lambda v: f"{v:.0%}").to_string())
jj = hold[PRIMARY].index.intersection(hold["Current score"].index)
same = (hold[PRIMARY][jj] == hold["Current score"][jj]).mean()
print(f"  PRIMARY holds the same thing as production in {same:.0%} of months")

# ---- chart (in-sample, offset 0) -----------------------------------------------------
spy = DI0["monthly"]["SPY"]
agg = DI0["monthly"]["AGG"].where(DI0["monthly"]["AGG"].notna(), DI0["tbill_m"])
bal = (0.6 * spy + 0.4 * agg).dropna()
mask = lambda x: S.in_sample_mask(x.index, A, B)
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), gridspec_kw={"height_ratios": [2.2, 1]})
styles = [("Current score", "#1f77b4", 2.4), (PRIMARY, "#2ca02c", 2.0),
          ("Factor mom 6m (sens.)", "#9467bd", 1.0), ("Factor mom 12m skip1 (sens.)", "#8c564b", 1.0)]
for name, c, lw in styles:
    x = res[name, 0][0]
    x = x[mask(x)].dropna()
    ax1.plot((1 + x).cumprod(), label=name, color=c, lw=lw)
for label, x, c in [("SPY", spy, "#d62728"), ("60/40", bal, "#ff7f0e")]:
    xx = x[mask(x)].dropna()
    ax1.plot((1 + xx).cumprod(), label=label, color=c, lw=1.2, alpha=0.8)
ax1.set_yscale("log")
ax1.set_title("Factor momentum for the style sleeve -- IN-SAMPLE 2001-2018 (full strategy; net 10 bps;\nrebalance offset 0 of 4, single offset; the Stage B table averages over 4 offsets)")
ax1.set_ylabel("Growth of $1"); ax1.legend(loc="upper left"); ax1.grid(alpha=0.3)
for name in ("Current score", PRIMARY):
    x = res[name, 0][0]
    x = x[mask(x)].dropna()
    eq = S.equity_curve(x)
    dd = eq / eq.cummax() - 1
    if name == "Current score":
        ax2.fill_between(eq.index, dd, 0, color="#b0b0b0", alpha=0.7, label="Production (current score)")
    else:
        ax2.plot(eq.index, dd, color="#2ca02c", lw=1.8, label=name)
ax2.set_title("Drawdown: production (grey area) vs new idea (line); rebalance offset 0 of 4"); ax2.legend(); ax2.grid(alpha=0.3)
ax2.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v:.0%}"))
plt.tight_layout()
out = os.path.join(HERE, "..", "results", "factor_momentum_insample.png")
plt.savefig(out, dpi=150)
print(f"\nSaved -> {HERE}")
