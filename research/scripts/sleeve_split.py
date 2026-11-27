"""
sleeve_split.py -- IN-SAMPLE ONLY (2002-2018) measurement, not a pre-registered strategy test.

Question: where does the 65% STYLE sleeve's edge come from -- the momentum RANKING or the
T-bill HURDLE? Five versions of the style sleeve, everything else production (35% sector
sleeve, IEF/cash defensive rule, 10 bps costs, simulator), 4 rebalance offsets (0/5/10/15
trading days before month-end), as in the other research scripts:
  Ranking + hurdle (production)        S.style_weight_path
  Ranking only, no hurdle              production top-1 + buffer, always invested
  Hurdle only: random passing ETF      one random ETF among those passing the hurdle
                                       (mean of 30 seeds for the sleeve, 10 for the book)
  Hurdle only: equal-weight passing    each style ETF gets 1/N; held if it passes the hurdle
                                       (12m OR 6m return > T-bills), else its slot goes to IEF/cash
  Neither: equal-weight all 7          always invested, no ranking, no hurdle

Reported for the style sleeve alone (100%) and for the full 65/35 book.
"Equal-weight passing" came out best on risk (higher Sharpe, much smaller drawdown, lower
CAGR). It was found by this measurement, not pre-registered, so it still needs its own
pre-registered test and the 2019+ check before any adoption.

Run:  python research/scripts/sleeve_split.py
Out:  research/results/sleeve_split_insample.png
      research/tables/sleeve_split/sleeve_split.csv
"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "strategy"))  # for strategy_lib
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
import strategy_lib as S

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.path.join(HERE, "..", "tables", "sleeve_split")
RESULTS = os.path.join(HERE, "..", "results")
os.makedirs(TABLES, exist_ok=True)

RAW = S.load_prices(); DI0 = S.get_data(); TB = DI0["tbill_m"]
OFFS = [0, 5, 10, 15]
W0, W1 = pd.Timestamp("2002-01-31"), pd.Timestamp("2018-12-31")
_DIK = {}
def di_k(k):
    if k in _DIK: return _DIK[k]
    ck = RAW if k == 0 else RAW.iloc[:-k].copy()
    if k: ck.index = RAW.index[k:]
    orig = S.load_prices; S.load_prices = lambda refresh=False: ck
    try: di = S.build_data()
    finally: S.load_prices = orig
    _DIK[k] = (di, ck); return _DIK[k]

def passing_set(di, t, names):
    tb12, tb6 = di["tbill12"].get(t, np.nan), di["tbill6"].get(t, np.nan)
    out = set()
    for a in names:
        p12 = (not np.isnan(tb12)) and (di["tot12"].loc[t, a] > tb12)
        p6 = (not np.isnan(tb6)) and (di["tot6"].loc[t, a] > tb6)
        if p12 or p6: out.add(a)
    return out

def path(di, mode, rng=None):
    """mode: rank_hurdle (production), rank_only, ew_hurdle, random_hurdle, ew_only"""
    if mode == "rank_hurdle":
        return S.style_weight_path(di)
    scores = S.composite(di["monthly"], S.STYLES)
    out, cur = {}, set()
    for t in scores.index:
        row = scores.loc[t].dropna()
        if len(row) < 3: continue
        names = list(row.index)
        if mode == "rank_only":                      # production ranking + buffer, no hurdle
            rk = row.rank(ascending=False)
            entry = {a for a in names if rk[a] <= 1}
            hold = {a for a in names if rk[a] <= 2}
            held = sorted((cur & hold) | entry, key=lambda a: rk[a])[:1]
            w = pd.Series(1.0, index=held); cur = set(held)
        elif mode == "ew_only":
            w = pd.Series(1.0 / len(names), index=names)
        else:
            ps_ = passing_set(di, t, names)
            if mode == "ew_hurdle":                  # each ETF 1/n, failing slots -> defensive
                w = pd.Series(1.0 / len(names), index=sorted(ps_))
            else:                                    # random_hurdle: one random passing ETF
                w = pd.Series(1.0, index=[rng.choice(sorted(ps_))]) if ps_ else pd.Series(dtype=float)
        d = 1.0 - float(w.sum())
        if d > 1e-9:
            dd = S.pick_defensive(di, t); w[dd] = w.get(dd, 0.0) + d
        out[t] = w
    return out

def run(ps, di, ck, book):
    if book:
        p6 = S.sector_weight_path(di, ps)
        w = S.combine_paths([(ps, S.W_STYLE), (p6, S.W_SECTOR)])
    else:
        w = dict(ps)
    w = {t: x for t, x in w.items() if t <= pd.Timestamp(S.IS_END)}
    _, st = S.simulate(w, di)
    nav = st["nav"].copy(); nav.index = RAW.index[ck.index.get_indexer(nav.index)]
    r = nav.resample("ME").last().pct_change().dropna()
    return r[(r.index >= W0) & (r.index <= W1)]

def mx(r):
    e = (1 + r).cumprod(); return (e / e.cummax() - 1).min()

MODES = [("Ranking + hurdle (production)", "rank_hurdle"),
         ("Ranking only, no hurdle", "rank_only"),
         ("Hurdle only: random passing ETF", "random_hurdle"),
         ("Hurdle only: equal-weight passing", "ew_hurdle"),
         ("Neither: equal-weight all 7", "ew_only")]
NSEED = 30
res, SERIES = {}, {}
t0 = time.time()
for book in (False, True):
    for label, mode in MODES:
        stats = []
        for k in OFFS:
            di, ck = di_k(k)
            if mode == "random_hurdle":
                rs = [run(path(di, mode, np.random.default_rng(s)), di, ck, book) for s in range(NSEED if not book else 10)]
                ms = [S.metrics(r, rf=TB) for r in rs]
                stats.append(dict(sharpe=np.mean([m["sharpe"] for m in ms]), cagr=np.mean([m["ann_ret"] for m in ms]),
                                  vol=np.mean([m["ann_vol"] for m in ms]), dd=np.mean([mx(r) for r in rs]),
                                  sharpe_p95=np.percentile([m["sharpe"] for m in ms], 95)))
            else:
                r = run(path(di, mode), di, ck, book); m = S.metrics(r, rf=TB)
                if k == 0:
                    SERIES[(book, label)] = r
                stats.append(dict(sharpe=m["sharpe"], cagr=m["ann_ret"], vol=m["ann_vol"], dd=mx(r)))
        res[(book, label)] = stats
    print(f"[{'book' if book else 'sleeve'} done {time.time()-t0:.0f}s]", flush=True)

spy = DI0["monthly"]["SPY"]; spy = spy[(spy.index >= W0) & (spy.index <= W1)]
ms = S.metrics(spy, rf=TB)
for book in (False, True):
    print("\n" + "=" * 100)
    print(("FULL BOOK (65% style variant + production 35% sector)" if book else "STYLE SLEEVE ALONE (100%)")
          + " -- 2002-2018, mean over 4 rebalance offsets")
    print("=" * 100)
    print(f"  {'variant':<36}{'Sharpe':>8}{'CAGR':>9}{'vol':>8}{'MaxDD':>9}   Sharpe by offset")
    for label, _ in MODES:
        st = res[(book, label)]
        print(f"  {label:<36}{np.mean([s['sharpe'] for s in st]):>8.3f}{np.mean([s['cagr'] for s in st]):>9.2%}"
              f"{np.mean([s['vol'] for s in st]):>8.1%}{np.mean([s['dd'] for s in st]):>9.1%}   "
              + " ".join(f"{s['sharpe']:.3f}" for s in st)
              + (f"   (random: 95th pct Sharpe {np.mean([s['sharpe_p95'] for s in st]):.3f})" if "random" in label else ""))
    if not book:
        print(f"  {'SPY buy & hold':<36}{ms['sharpe']:>8.3f}{ms['ann_ret']:>9.2%}{ms['ann_vol']:>8.1%}{mx(spy):>9.1%}")

# ---- table ----------------------------------------------------------------------------
rows = []
for book in (False, True):
    for label, _ in MODES:
        st = res[(book, label)]
        rows.append(dict(scope="full book" if book else "style sleeve alone", variant=label,
                         sharpe=np.mean([s["sharpe"] for s in st]), cagr=np.mean([s["cagr"] for s in st]),
                         vol=np.mean([s["vol"] for s in st]), max_dd=np.mean([s["dd"] for s in st]),
                         sharpe_by_offset=" ".join(f"{s['sharpe']:.3f}" for s in st)))
pd.DataFrame(rows).to_csv(os.path.join(TABLES, "sleeve_split.csv"), index=False)

# ---- chart (full book, offset 0; same layout as strategy/backtest.png) -----------------
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
agg = DI0["monthly"]["AGG"].where(DI0["monthly"]["AGG"].notna(), DI0["tbill_m"])
bal = (0.6 * DI0["monthly"]["SPY"] + 0.4 * agg).dropna()
bal = bal[(bal.index >= W0) & (bal.index <= W1)]
lines = [("Ranking + hurdle (production)", "#1f77b4", 2.4), ("Hurdle only: equal-weight passing", "#2ca02c", 2.0),
         ("Ranking only, no hurdle", "#9467bd", 1.0), ("Neither: equal-weight all 7", "#7f7f7f", 1.0)]
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), gridspec_kw={"height_ratios": [2.2, 1]})
for label, c, lw in lines:
    ax1.plot((1 + SERIES[(True, label)]).cumprod(), label=label, color=c, lw=lw)
ax1.plot((1 + spy).cumprod(), label="SPY", color="#d62728", lw=1.2, alpha=0.8)
ax1.plot((1 + bal).cumprod(), label="60/40", color="#ff7f0e", lw=1.2, alpha=0.8)
ax1.set_yscale("log")
ax1.set_title("Style sleeve split: ranking vs T-bill hurdle -- IN-SAMPLE 2002-2018 "
              "(full book; net 10 bps;\nrebalance offset 0 of 4, single offset; the table averages over 4)")
ax1.set_ylabel("Growth of $1"); ax1.legend(loc="upper left"); ax1.grid(alpha=0.3)
for label, x, c in [("Production", SERIES[(True, lines[0][0])], "#b0b0b0"),
                    ("Hurdle + equal-weight passing", SERIES[(True, lines[1][0])], "#2ca02c")]:
    eq = (1 + x).cumprod()
    dd = eq / eq.cummax() - 1
    if label == "Production":
        ax2.fill_between(eq.index, dd, 0, color=c, alpha=0.7, label=label)
    else:
        ax2.plot(eq.index, dd, color=c, lw=1.8, label=label)
ax2.set_title("Drawdown: production (grey area) vs hurdle + equal-weight passing (line); rebalance offset 0 of 4"); ax2.legend(); ax2.grid(alpha=0.3)
ax2.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v:.0%}"))
plt.tight_layout()
out = os.path.join(RESULTS, "sleeve_split_insample.png")
plt.savefig(out, dpi=150)
print(f"\nSaved -> {out}")
