"""
breadth_sizing_test.py -- "breadth sizing" for the 65% STYLE sleeve: in-sample 2002-2018 and holdout 2019-01..2026-10.

Candidate (found 2026-11-26 as variant V2 of the graded-hurdle sandbox test; frozen exactly as there, nothing re-tuned):
  Pick: production ranking (composite 3/6/12m skip-1) + incumbency buffer, but WITHOUT the hurdle as a filter.
  Breadth b = share of the 7 style ETFs that pass the production hurdle (12m OR 6m total return > T-bills).
  Weight in the pick = b if the pick itself passes the hurdle, else 0. Remainder -> production defensive pick
  (IEF if its 12m return beats T-bills, else cash). Idea: hold the leader in full only when most of the style
  universe is trending up; scale down when the uptrend is narrow.
  Everything else is production: 35% sector sleeve (S.sector_weight_path on the new style path), 65/35, 10 bps, simulator.

Comparators:
  Production (S.style_weight_path).
  Production DILUTED to the same average exposure: w = e * production + (1 - e) * defensive pick, where e = the
  candidate's mean pick weight over 2002-2018 (measured in-sample, per offset, then frozen). This separates
  "better timing" from "just holding less".

Rules (fixed before running; see research/sandbox/graded_hurdle/PREREG.md and HOLDOUT_PREREG.md):
  In-sample pass bar (2002-2018, 4 rebalance offsets 0/5/10/15): beats production on mean Sharpe AND CAGR, wins >= 3 of 4
  offsets, higher CAGR in both 2002-09 and 2010-18, mean paired t >= 2.5.
  Holdout 2019-01..2026-10 (single use, already run once on 2026-11-26): CONFIRMED only if, averaged over 4 offsets,
  (1) Sharpe > production, (2) smaller max drawdown than production, (3) Sharpe > the diluted control.
  Results (2026-11-26): in-sample FAIL (t 0.35, CAGR lower in 2010-18); holdout NOT CONFIRMED (Sharpe 0.745 vs 0.859).
  This script reproduces both; rerunning it is not a new trial.

Run:  python research/scripts/breadth_sizing_test.py
Out:  research/results/breadth_sizing_insample.png, research/results/breadth_sizing_holdout.png
      research/tables/breadth_sizing/insample.csv, holdout.csv
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
TABLES = os.path.join(HERE, "..", "tables", "breadth_sizing")
RESULTS = os.path.join(HERE, "..", "results")
os.makedirs(TABLES, exist_ok=True)

RAW = S.load_prices()
DI0 = S.get_data()
TB = DI0["tbill_m"]
OFFS = [0, 5, 10, 15]
IS0, IS1, MID = pd.Timestamp("2002-01-31"), pd.Timestamp("2018-12-31"), pd.Timestamp("2009-12-31")
HO0, HO1 = pd.Timestamp("2019-01-31"), pd.Timestamp("2026-10-31")
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


def passes(di, t, a):
    """Production hurdle: 12m OR 6m total return beats the compounded T-bill."""
    tb12, tb6 = di["tbill12"].get(t, np.nan), di["tbill6"].get(t, np.nan)
    p12 = (not np.isnan(tb12)) and (di["tot12"].loc[t, a] > tb12)
    p6 = (not np.isnan(tb6)) and (di["tot6"].loc[t, a] > tb6)
    return p12 or p6


def breadth_path(di):
    """Breadth-sized style sleeve: {formation_ts: weights}."""
    scores = S.composite(di["monthly"], S.STYLES)
    out, cur = {}, set()
    for t in scores.index:
        row = scores.loc[t].dropna()
        if len(row) < 3:
            continue
        rk = row.rank(ascending=False)
        entry = {a for a in row.index if rk[a] <= 1}
        hold = {a for a in row.index if rk[a] <= 2}
        pick = sorted((cur & hold) | entry, key=lambda a: rk[a])[0]
        cur = {pick}
        b = np.mean([passes(di, t, a) for a in row.index])
        f = b if passes(di, t, pick) else 0.0
        w = pd.Series(dtype=float)
        if f > 1e-9:
            w[pick] = f
        if 1 - f > 1e-9:
            d = S.pick_defensive(di, t)
            w[d] = w.get(d, 0.0) + 1 - f
        out[t] = w
    return out


def exposure(ps):
    ts = [t for t in ps if IS0 <= t <= IS1]
    return float(np.mean([sum(x for a, x in ps[t].items() if a in S.STYLES) for t in ts]))


def dilute(ps, di, e):
    out = {}
    for t, w in ps.items():
        n = pd.Series(dtype=float)
        for a, x in w.items():
            n[a] = n.get(a, 0) + e * x
        d = S.pick_defensive(di, t)
        n[d] = n.get(d, 0) + 1 - e
        out[t] = n
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


NAMES = ["Production", "Breadth sizing", "Production diluted"]
res, EXP = {}, {}
for k in OFFS:
    print(f"[offset {k}] running ...", flush=True)
    di, ck = di_k(k)
    pp, pb = S.style_weight_path(di), breadth_path(di)
    EXP[k] = exposure(pb)
    res["Production", k] = run(di, ck, pp)
    res["Breadth sizing", k] = run(di, ck, pb)
    res["Production diluted", k] = run(di, ck, dilute(pp, di, EXP[k]))
print("  in-sample pick exposure by offset:", {k: round(v, 3) for k, v in EXP.items()})

prod_full, _ = S.build_strategy(DI=DI0)
j = res["Production", 0].index.intersection(prod_full.index)
print("  production offset-0 vs build_strategy, max abs diff:",
      float((res["Production", 0][j] - prod_full[j]).abs().max()))


def paired_t(a, b):
    d = (a - b).dropna()
    return d.mean() / (d.std() / np.sqrt(len(d))) if d.std() > 0 else 0.0


def table(a, b, label):
    rows, st = [], {}
    for n in NAMES:
        rs = [res[n, k].loc[a:b] for k in OFFS]
        ms = [S.metrics(r, rf=TB) for r in rs]
        dds = [mx(r) for r in rs]
        st[n] = dict(sharpe=np.mean([m["sharpe"] for m in ms]), cagr=np.mean([m["ann_ret"] for m in ms]),
                     vol=np.mean([m["ann_vol"] for m in ms]), max_dd=np.mean(dds))
        row = dict(period=label, variant=n, months=len(rs[0]), **st[n],
                   sharpe_by_offset=" ".join(f"{m['sharpe']:.3f}" for m in ms),
                   cagr_by_offset=" ".join(f"{m['ann_ret']:.2%}" for m in ms),
                   maxdd_by_offset=" ".join(f"{d:.1%}" for d in dds))
        if n != "Production":
            row["paired_t_vs_prod"] = np.mean([paired_t(res[n, k].loc[a:b], res["Production", k].loc[a:b]) for k in OFFS])
            row["offsets_won"] = sum(
                (S.metrics(res[n, k].loc[a:b], rf=TB)["sharpe"] > S.metrics(res["Production", k].loc[a:b], rf=TB)["sharpe"])
                and (S.metrics(res[n, k].loc[a:b], rf=TB)["ann_ret"] > S.metrics(res["Production", k].loc[a:b], rf=TB)["ann_ret"])
                for k in OFFS)
        rows.append(row)
    print("\n" + "=" * 100)
    print(f"{label}  -- mean over 4 rebalance offsets")
    print("=" * 100)
    print(f"  {'variant':<20}{'months':>7}{'Sharpe':>8}{'CAGR':>8}{'vol':>7}{'MaxDD':>8}{'t vs prod':>11}{'won':>5}   Sharpe by offset")
    for r in rows:
        print(f"  {r['variant']:<20}{r['months']:>7}{r['sharpe']:>8.3f}{r['cagr']:>8.2%}{r['vol']:>7.1%}{r['max_dd']:>8.1%}"
              f"{r.get('paired_t_vs_prod', np.nan):>11.2f}{r.get('offsets_won', 0):>3}/4   {r['sharpe_by_offset']}")
    return pd.DataFrame(rows), st


ins, st_in = table(IS0, IS1, "IN-SAMPLE 2002-2018")
halves = {}
for n in NAMES[1:]:
    for nm, (a, b) in {"2002-09": (IS0, MID), "2010-18": (MID + pd.offsets.MonthEnd(1), IS1)}.items():
        halves[n, nm] = np.mean([S.metrics(res[n, k].loc[a:b], rf=TB)["ann_ret"] -
                                 S.metrics(res["Production", k].loc[a:b], rf=TB)["ann_ret"] for k in OFFS])
print("  CAGR vs production by half:", {f"{n} {h}": f"{v:+.2%}" for (n, h), v in halves.items()})
bv = ins.set_index("variant").loc["Breadth sizing"]
ok = (st_in["Breadth sizing"]["sharpe"] > st_in["Production"]["sharpe"] and
      st_in["Breadth sizing"]["cagr"] > st_in["Production"]["cagr"] and bv["offsets_won"] >= 3 and
      halves["Breadth sizing", "2002-09"] > 0 and halves["Breadth sizing", "2010-18"] > 0 and bv["paired_t_vs_prod"] >= 2.5)
print(f"  IN-SAMPLE VERDICT: {'PASS' if ok else 'FAIL'}")
ins.to_csv(os.path.join(TABLES, "insample.csv"), index=False)

ho, st_ho = table(HO0, HO1, "HOLDOUT 2019-01..2026-10")
c1 = st_ho["Breadth sizing"]["sharpe"] > st_ho["Production"]["sharpe"]
c2 = st_ho["Breadth sizing"]["max_dd"] > st_ho["Production"]["max_dd"]
c3 = st_ho["Breadth sizing"]["sharpe"] > st_ho["Production diluted"]["sharpe"]
print(f"  HOLDOUT VERDICT: {'CONFIRMED' if (c1 and c2 and c3) else 'NOT CONFIRMED'} "
      f"(Sharpe > prod {c1}, smaller DD {c2}, Sharpe > diluted {c3})")
ho.to_csv(os.path.join(TABLES, "holdout.csv"), index=False)


# ---- charts (same layout as strategy/backtest.png; drawdown = production vs new idea only) ----
def chart(a, b, title, fname):
    spy = DI0["monthly"]["SPY"].loc[a:b]
    agg = DI0["monthly"]["AGG"].where(DI0["monthly"]["AGG"].notna(), DI0["tbill_m"])
    bal = (0.6 * DI0["monthly"]["SPY"] + 0.4 * agg).dropna().loc[a:b]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), gridspec_kw={"height_ratios": [2.2, 1]})
    for label, x, c, lw, ls in [("Production", res["Production", 0].loc[a:b], "#1f77b4", 2.4, "-"),
                                ("Breadth sizing", res["Breadth sizing", 0].loc[a:b], "#2ca02c", 2.0, "-"),
                                ("Production diluted to same exposure", res["Production diluted", 0].loc[a:b], "#7f7f7f", 1.4, "--"),
                                ("SPY", spy, "#d62728", 1.2, "-"), ("60/40", bal, "#ff7f0e", 1.2, "-")]:
        ax1.plot((1 + x).cumprod(), label=label, color=c, lw=lw, ls=ls)
    ax1.set_yscale("log")
    ax1.set_title(title + "\n(net 10 bps; rebalance offset 0 of 4, single offset; the tables average over 4)")
    ax1.set_ylabel("Growth of $1"); ax1.legend(loc="upper left"); ax1.grid(alpha=0.3)
    for label, x, c in [("Production", res["Production", 0].loc[a:b], "#b0b0b0"),
                        ("Breadth sizing", res["Breadth sizing", 0].loc[a:b], "#2ca02c")]:
        eq = (1 + x).cumprod()
        dd = eq / eq.cummax() - 1
        if label == "Production":
            ax2.fill_between(eq.index, dd, 0, color=c, alpha=0.7, label=label)
        else:
            ax2.plot(eq.index, dd, color=c, lw=1.8, label=label)
    ax2.set_title("Drawdown: production (grey area) vs breadth sizing (line); rebalance offset 0 of 4")
    ax2.legend(loc="lower left"); ax2.grid(alpha=0.3)
    ax2.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v:.0%}"))
    plt.tight_layout()
    out = os.path.join(RESULTS, fname)
    plt.savefig(out, dpi=150)
    plt.close(fig)
    print(f"Saved -> {out}")


chart(IS0, IS1, "Breadth sizing vs production -- IN-SAMPLE 2002-2018 (style sleeve; full strategy)",
      "breadth_sizing_insample.png")
chart(HO0, HO1, "Breadth sizing vs production -- HOLDOUT 2019-01 to 2026-10 (style sleeve; full strategy)",
      "breadth_sizing_holdout.png")
