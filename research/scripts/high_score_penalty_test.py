"""
high_score_penalty_test.py -- IN-SAMPLE ONLY (2002-2018), 4 rebalance offsets (0,5,10,15 days before month-end).

Rule (fixed before running): composite = mean of 3/6/12m z-scores (production), then
    score' = score - LAM * max(0, score - THR)
i.e. an asset whose composite is far above the cross-section is pulled back toward the pack.
Primary: LAM=0.5, THR=1.0, style sleeve only. Sensitivities: LAM=1.0; THR=1.5; primary on both sleeves.
Bar (as before): beats production on mean Sharpe AND CAGR across offsets, wins >=3/4 offsets,
better in both 2002-09 and 2010-18, mean paired t >= 2. Also report max drawdown EXCLUDING 2008-09.

Run: python research/scripts/high_score_penalty_test.py
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "strategy"))  # for strategy_lib
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
import strategy_lib as S

RAW = S.load_prices(); DI0 = S.get_data(); TB = DI0["tbill_m"]
OFFS = [0, 5, 10, 15]
W0, W1, WM = pd.Timestamp("2002-01-31"), pd.Timestamp("2018-12-31"), pd.Timestamp("2009-12-31")
_DIK = {}

def di_k(k):
    if k in _DIK: return _DIK[k]
    ck = RAW if k == 0 else RAW.iloc[:-k].copy()
    if k: ck.index = RAW.index[k:]
    orig = S.load_prices
    S.load_prices = lambda refresh=False: ck
    try: di = S.build_data()
    finally: S.load_prices = orig
    _DIK[k] = (di, ck); return _DIK[k]

def base_comp(m, c):
    r = m[c]
    return sum(S.cs_z(S.mom(r, 1, h)) for h in (3, 6, 12)) / 3

def pen(lam, thr):
    def f(m, c):
        s = base_comp(m, c)
        return s - lam * (s - thr).clip(lower=0)
    return f

VARS = {"base": (None, None),
        "PRIMARY lam .5 thr 1.0 (style)": (pen(.5, 1.0), None),
        "lam 1.0 thr 1.0 (style)": (pen(1.0, 1.0), None),
        "lam .5 thr 1.5 (style)": (pen(.5, 1.5), None),
        "lam .5 thr 1.0 BOTH sleeves": (pen(.5, 1.0), pen(.5, 1.0))}

def run(name, k):
    di, ck = di_k(k); orig = S.composite
    sf, sec = VARS[name]
    try:
        S.composite = sf or orig
        ps = S.style_weight_path(di)
        S.composite = sec or orig
        p6 = S.sector_weight_path(di, ps)
    finally:
        S.composite = orig
    w = S.combine_paths([(ps, S.W_STYLE), (p6, S.W_SECTOR)])
    tl = S.latest_formation(di, ps, p6)
    w = {t: x for t, x in w.items() if t <= min(tl, pd.Timestamp(S.IS_END))}
    _, st = S.simulate(w, di)
    nav = st["nav"].copy(); nav.index = RAW.index[ck.index.get_indexer(nav.index)]
    return nav.resample("ME").last().pct_change().dropna()

res = {(n, k): run(n, k) for n in VARS for k in OFFS}
prod, _ = S.build_strategy(DI0, end=S.IS_END) if False else S.build_strategy(DI=DI0, end=S.IS_END)
j = res["base", 0].index.intersection(prod.index)
print("baseline offset-0 vs production max abs diff:", float((res["base", 0][j] - prod[j]).abs().max()))

win = lambda r: r[(r.index >= W0) & (r.index <= W1)]
exg = lambda r: pd.concat([r[(r.index >= W0) & (r.index <= "2007-12-31")], r[(r.index >= "2010-01-31") & (r.index <= W1)]])
def mx(r):
    e = (1 + r).cumprod(); return (e / e.cummax() - 1).min()

print(f"\n{'variant':<34}{'dSharpe':>8}{'dCAGR':>8}{'wins':>6}{'d02-09':>8}{'d10-18':>8}{'t':>7}{'dMaxDD':>8}{'dMaxDD exGFC':>14}{'months chg':>11}  verdict")
for n in VARS:
    if n == "base": continue
    dS, dC, w, dA, dB, ts, dD, dX, nc = [], [], 0, [], [], [], [], [], []
    for k in OFFS:
        b, v = win(res["base", k]), win(res[n, k])
        mb, mv = S.metrics(b, rf=TB), S.metrics(v, rf=TB)
        dS.append(mv["sharpe"] - mb["sharpe"]); dC.append(mv["ann_ret"] - mb["ann_ret"])
        w += (mv["sharpe"] - mb["sharpe"] > 1e-6) and (mv["ann_ret"] - mb["ann_ret"] > 1e-6)
        d = (v - b); nc.append(int((d.abs() > 1e-9).sum()))
        ts.append(d.mean() / (d.std() / np.sqrt(len(d))) if d.std() > 0 else 0.0)
        h1 = b.index <= WM
        dA.append(S.metrics(v[h1], rf=TB)["ann_ret"] - S.metrics(b[h1], rf=TB)["ann_ret"])
        dB.append(S.metrics(v[~h1], rf=TB)["ann_ret"] - S.metrics(b[~h1], rf=TB)["ann_ret"])
        dD.append(mx(v) - mx(b)); dX.append(mx(exg(v)) - mx(exg(b)))
    ok = np.mean(dS) > 0 and np.mean(dC) > 0 and w >= 3 and np.mean(dA) > 0 and np.mean(dB) > 0 and np.mean(ts) >= 2
    print(f"{n:<34}{np.mean(dS):>+8.3f}{np.mean(dC):>+8.2%}{w:>5}/4{np.mean(dA):>+8.2%}{np.mean(dB):>+8.2%}{np.mean(ts):>+7.2f}{np.mean(dD):>+8.1%}{np.mean(dX):>+14.1%}{str(nc):>11}  {'PASS' if ok else '-'}")
bm = [S.metrics(win(res['base', k]), rf=TB) for k in OFFS]
print("\nbaseline mean over offsets: Sharpe %.3f  CAGR %.2f%%   (new trials: 4; project total now 32)" % (np.mean([m['sharpe'] for m in bm]), 100 * np.mean([m['ann_ret'] for m in bm])))

# ---- chart (in-sample 2002-2018, rebalance offset 0 of 4; same layout as strategy/backtest.png) ----
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
HERE = os.path.dirname(os.path.abspath(__file__))
spy = DI0["monthly"]["SPY"]
agg = DI0["monthly"]["AGG"].where(DI0["monthly"]["AGG"].notna(), DI0["tbill_m"])
bal = (0.6 * spy + 0.4 * agg).dropna()
lines = [("Current score", win(res["base", 0]), "#1f77b4", 2.4),
         ("Penalty lam .5 thr 1.0 (PRIMARY)", win(res["PRIMARY lam .5 thr 1.0 (style)", 0]), "#2ca02c", 2.0),
         ("lam 1.0 thr 1.0", win(res["lam 1.0 thr 1.0 (style)", 0]), "#9467bd", 1.0),
         ("lam .5 thr 1.5", win(res["lam .5 thr 1.5 (style)", 0]), "#8c564b", 1.0),
         ("lam .5 thr 1.0 both sleeves", win(res["lam .5 thr 1.0 BOTH sleeves", 0]), "#e377c2", 1.0),
         ("SPY", win(spy), "#d62728", 1.2), ("60/40", win(bal), "#ff7f0e", 1.2)]
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), gridspec_kw={"height_ratios": [2.2, 1]})
for label, x, c, lw in lines:
    ax1.plot((1 + x.dropna()).cumprod(), label=label, color=c, lw=lw)
ax1.set_yscale("log")
ax1.set_title("High-score penalty -- IN-SAMPLE 2002-2018 (style sleeve; net 10 bps;\nrebalance offset 0 of 4, single offset; the table averages over 4)")
ax1.set_ylabel("Growth of $1"); ax1.legend(loc="upper left"); ax1.grid(alpha=0.3)
for label, x, c, _ in [lines[0], lines[1]]:
    eq = (1 + x.dropna()).cumprod()
    dd = eq / eq.cummax() - 1
    if label == "Current score":
        ax2.fill_between(eq.index, dd, 0, color="#b0b0b0", alpha=0.7, label="Production (current score)")
    else:
        ax2.plot(eq.index, dd, color=c, lw=1.8, label=label)
ax2.set_title("Drawdown: production (grey area) vs PRIMARY (line); rebalance offset 0 of 4"); ax2.legend(); ax2.grid(alpha=0.3)
ax2.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v:.0%}"))
plt.tight_layout()
out = os.path.join(HERE, "..", "results", "high_score_penalty_insample.png")
plt.savefig(out, dpi=150)
print(f"\nSaved -> {out}")
