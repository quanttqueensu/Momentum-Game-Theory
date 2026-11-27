"""
switch_band_test.py -- "switch band" (T2) for the 65% STYLE sleeve: in-sample 2002-2018 and holdout 2019-01..2026-10.

Rule (fixed before running in research/swarm/PLAN_R6.md, round 6; nothing re-tuned):
  Production picks the #1 style ETF by composite() each month and switches whenever a different ETF is #1, however
  small the lead. T2 keeps the current ETF (if it still passes the T-bill hurdle) unless the new #1's composite score
  beats the current ETF's score by MORE THAN 0.5 (z units). Everything else is production: the hurdle is still checked
  monthly (a failing ETF still goes to IEF/cash at once), re-entry from defensive is as production, the 35% sector
  sleeve (S.sector_weight_path on the new style path), 65/35, 10 bps costs, simulator.
  Band 0.25 and 1.0 are sensitivities: reported, never selected.

Pass rule (implementation non-inferiority; fixed before running):
  (1) style-sleeve turnover falls >= 25% vs production (mean over 4 offsets);
  (2) mean CAGR >= production - 0.25 pp/yr AND mean Sharpe >= production - 0.02;
  (3) in-sample only: CAGR not lower than production by more than 0.5 pp/yr in either half (2002-09, 2010-18);
  (4) mean max drawdown not worse than production by more than 2 pp.
  (5) (long US history 1964-2018, French data, net of costs; research/swarm/work/r6_long/) CAGR not lower than
      production by more than 0.5 pp/yr -> passed (+0.03 pp, turnover -24%).
  Results (2026-11-26): in-sample PASS (1)-(4); holdout 2019-01..2026-10 CONFIRMED (single use).
  This script reproduces both; rerunning it is not a new trial.

Run:  python research/scripts/switch_band_test.py
Out:  research/results/switch_band_insample.png, research/results/switch_band_holdout.png
      research/tables/switch_band/insample.csv, holdout.csv
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
TABLES = os.path.join(HERE, "..", "tables", "switch_band")
RESULTS = os.path.join(HERE, "..", "results")
os.makedirs(TABLES, exist_ok=True)

RAW = S.load_prices()
DI0 = S.get_data()
TB = DI0["tbill_m"]
OFFS = [0, 5, 10, 15]
IS0, IS1, MID = pd.Timestamp("2002-01-31"), pd.Timestamp("2018-12-31"), pd.Timestamp("2009-12-31")
HO0, HO1 = pd.Timestamp("2019-01-31"), pd.Timestamp("2026-10-31")
BAND = 0.5
_DIK = {}


def di_k(k):
    """Data built as if every month ended k trading days earlier (same harness as the other experiments)."""
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


def style_path(DI, band=None):
    """Copy of S.style_weight_path; band=None reproduces production, a number applies the switch band."""
    scores = S.composite(DI["monthly"], S.STYLES)
    out, cur_held = {}, set()
    for t in scores.index:
        row = scores.loc[t].dropna()
        if len(row) < 3:
            continue
        tb12, tb6 = DI["tbill12"].get(t, np.nan), DI["tbill6"].get(t, np.nan)
        passing = set()
        for a in row.index:
            p12 = (not np.isnan(tb12)) and (DI["tot12"].loc[t, a] > tb12)
            p6 = (not np.isnan(tb6)) and (DI["tot6"].loc[t, a] > tb6)
            if p12 or p6:
                passing.add(a)
        ranked = row.rank(ascending=False)
        entry = {a for a in row.index if ranked[a] <= S.STYLE_K and a in passing}
        hold = {a for a in row.index if ranked[a] <= S.STYLE_K + S.STYLE_BUFFER and a in passing}
        held = sorted((cur_held & hold) | entry, key=lambda a: ranked[a])[:S.STYLE_K]
        inc = next(iter(cur_held)) if cur_held else None
        if band is not None and inc is not None and inc in passing and entry:
            new = next(iter(entry))
            if new != inc and not (row[new] - row[inc] > band):
                held = [inc]                      # lead too small: keep the current ETF
        w = (pd.Series(1.0 / S.STYLE_K, index=held, dtype=float) if held else pd.Series(dtype=float))
        def_wt = 1.0 - float(w.sum())
        if def_wt > 1e-9:
            d = S.pick_defensive(DI, t)
            w[d] = w.get(d, 0.0) + def_wt
        out[t] = w
        cur_held = set(held)
    return out


def run(ps, di, ck):
    p6 = S.sector_weight_path(di, ps)
    w = S.combine_paths([(ps, S.W_STYLE), (p6, S.W_SECTOR)])
    tl = S.latest_formation(di, ps, p6)
    w = {t: x for t, x in w.items() if t <= tl}
    _, st = S.simulate(w, di)
    nav = st["nav"].copy()
    nav.index = RAW.index[ck.index.get_indexer(nav.index)]
    return nav.resample("ME").last().pct_change().dropna()


def style_trades(ps):
    """One-way style-sleeve turnover per formation (sum |dw| / 2); 1.0 = one full ETF switch."""
    ts = sorted(ps)
    out = {}
    for a, b in zip(ts[:-1], ts[1:]):
        out[b] = sum(abs(ps[b].get(k, 0) - ps[a].get(k, 0)) for k in set(ps[a].index) | set(ps[b].index)) / 2
    return pd.Series(out)


def mx(r):
    e = (1 + r).cumprod()
    return (e / e.cummax() - 1).min()


VARS = {"Production": None, "Switch band 0.5": BAND, "Band 0.25 (sens.)": 0.25, "Band 1.0 (sens.)": 1.0}
res, trades = {}, {}
for k in OFFS:
    print(f"[offset {k}] running ...", flush=True)
    di, ck = di_k(k)
    for n, band in VARS.items():
        ps = style_path(di, band)
        res[n, k] = run(ps, di, ck)
        trades[n, k] = style_trades(ps)

ref = S.style_weight_path(DI0)
mine = style_path(DI0, None)
same = all(set(ref[t].index) == set(mine[t].index) and np.allclose(ref[t].values, mine[t][ref[t].index].values) for t in ref)
prod_full, _ = S.build_strategy(DI=DI0)
j = res["Production", 0].index.intersection(prod_full.index)
print("  production style path copy == S.style_weight_path:", same)
print("  production offset-0 vs build_strategy, max abs diff:",
      float((res["Production", 0][j] - prod_full[j]).abs().max()))


def table(a, b, label, halves):
    rows, st = [], {}
    for n in VARS:
        rs = [res[n, k].loc[a:b] for k in OFFS]
        ms = [S.metrics(r, rf=TB) for r in rs]
        yrs = (b - a).days / 365.25
        turn = np.mean([trades[n, k].loc[a:b].sum() / yrs for k in OFFS])
        st[n] = dict(sharpe=np.mean([m["sharpe"] for m in ms]), cagr=np.mean([m["ann_ret"] for m in ms]),
                     max_dd=np.mean([mx(r) for r in rs]), style_turnover=turn)
        row = dict(period=label, variant=n, months=len(rs[0]), **st[n],
                   sharpe_by_offset=" ".join(f"{m['sharpe']:.3f}" for m in ms),
                   cagr_by_offset=" ".join(f"{m['ann_ret']:.2%}" for m in ms))
        if halves:
            for nm, (x, y) in {"d_cagr_2002_09": (a, MID), "d_cagr_2010_18": (MID + pd.offsets.MonthEnd(1), b)}.items():
                row[nm] = np.mean([S.metrics(res[n, k].loc[x:y], rf=TB)["ann_ret"] -
                                   S.metrics(res["Production", k].loc[x:y], rf=TB)["ann_ret"] for k in OFFS])
        rows.append(row)
    P = st["Production"]
    for row in rows:
        row["turnover_change"] = row["style_turnover"] / P["style_turnover"] - 1
        c1 = row["turnover_change"] <= -0.25
        c2 = row["cagr"] >= P["cagr"] - 0.0025 and row["sharpe"] >= P["sharpe"] - 0.02
        c3 = (not halves) or (row["d_cagr_2002_09"] >= -0.005 and row["d_cagr_2010_18"] >= -0.005)
        c4 = row["max_dd"] >= P["max_dd"] - 0.02
        row["verdict"] = "baseline" if row["variant"] == "Production" else ("PASS" if (c1 and c2 and c3 and c4) else "fail")
    print("\n" + "=" * 104)
    print(f"{label}  -- mean over 4 rebalance offsets")
    print("=" * 104)
    print(f"  {'variant':<20}{'Sharpe':>8}{'CAGR':>8}{'MaxDD':>8}{'style switches/yr':>19}{'change':>8}   verdict   Sharpe by offset")
    for r in rows:
        print(f"  {r['variant']:<20}{r['sharpe']:>8.3f}{r['cagr']:>8.2%}{r['max_dd']:>8.1%}{r['style_turnover']:>19.2f}"
              f"{r['turnover_change']:>+8.0%}   {r['verdict']:<9} {r['sharpe_by_offset']}")
    return pd.DataFrame(rows)


ins = table(IS0, IS1, "IN-SAMPLE 2002-2018", halves=True)
ins.to_csv(os.path.join(TABLES, "insample.csv"), index=False)
ho = table(HO0, HO1, "HOLDOUT 2019-01..2026-10", halves=False)
ho.to_csv(os.path.join(TABLES, "holdout.csv"), index=False)
v = ho.set_index("variant").loc["Switch band 0.5", "verdict"]
print(f"  HOLDOUT VERDICT (switch band 0.5): {'CONFIRMED' if v == 'PASS' else 'NOT CONFIRMED'}")


# ---- charts: growth, drawdown (production vs switch band only), cumulative style switches ----
def chart(a, b, title, fname):
    spy = DI0["monthly"]["SPY"].loc[a:b]
    agg = DI0["monthly"]["AGG"].where(DI0["monthly"]["AGG"].notna(), DI0["tbill_m"])
    bal = (0.6 * DI0["monthly"]["SPY"] + 0.4 * agg).dropna().loc[a:b]
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(13, 11), gridspec_kw={"height_ratios": [2.2, 1, 1]})
    for label, x, c, lw in [("Production", res["Production", 0].loc[a:b], "#1f77b4", 2.4),
                            ("Switch band 0.5", res["Switch band 0.5", 0].loc[a:b], "#2ca02c", 2.0),
                            ("SPY", spy, "#d62728", 1.2), ("60/40", bal, "#ff7f0e", 1.2)]:
        ax1.plot((1 + x).cumprod(), label=label, color=c, lw=lw)
    ax1.set_yscale("log")
    ax1.set_title(title + "\n(net 10 bps; rebalance offset 0 of 4, single offset; the tables average over 4)")
    ax1.set_ylabel("Growth of $1"); ax1.legend(loc="upper left"); ax1.grid(alpha=0.3)
    for label, x, c in [("Production", res["Production", 0].loc[a:b], "#b0b0b0"),
                        ("Switch band 0.5", res["Switch band 0.5", 0].loc[a:b], "#2ca02c")]:
        eq = (1 + x).cumprod()
        dd = eq / eq.cummax() - 1
        if label == "Production":
            ax2.fill_between(eq.index, dd, 0, color=c, alpha=0.7, label=label)
        else:
            ax2.plot(eq.index, dd, color=c, lw=1.8, label=label)
    ax2.set_title("Drawdown: production (grey area) vs switch band (line); rebalance offset 0 of 4")
    ax2.legend(loc="lower left"); ax2.grid(alpha=0.3)
    ax2.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v:.0%}"))
    for label, c in [("Production", "#1f77b4"), ("Switch band 0.5", "#2ca02c")]:
        cum = trades[label, 0].loc[a:b].cumsum()
        ax3.step(cum.index, cum.values, where="post", color=c, lw=2, label=f"{label} ({cum.iloc[-1]:.0f} total)")
    ax3.set_title("Cumulative style-sleeve trading (1 = one full switch of the 65% sleeve); rebalance offset 0 of 4")
    ax3.set_ylabel("Full switches"); ax3.legend(loc="upper left"); ax3.grid(alpha=0.3)
    plt.tight_layout()
    out = os.path.join(RESULTS, fname)
    plt.savefig(out, dpi=150)
    plt.close(fig)
    print(f"Saved -> {out}")


chart(IS0, IS1, "Switch band (T2) vs production -- IN-SAMPLE 2002-2018 (style sleeve; full strategy)",
      "switch_band_insample.png")
chart(HO0, HO1, "Switch band (T2) vs production -- HOLDOUT 2019-01 to 2026-10 (style sleeve; full strategy)",
      "switch_band_holdout.png")
