"""
sector_signal_research.py  --  in-sample test of sector-sleeve momentum signals.

Only the 35% sector sleeve's score changes. The 65% style sleeve, the crowding
game, the regime filter, the buffer, costs and the simulator all come from
strategy_lib, which is imported and never modified.

VARIANTS (each horizon h in {3, 6, 12} skips the latest month)
  S0       Production: compounded h-month return.
  S1-N     Residual momentum: sum of (sector return - beta * SPY return) over h
           months. Beta is a no-intercept regression on the N months ending at
           the formation date. N = 36 is the headline; 12 and 60 are robustness.
  S2       h-month return / standard deviation of monthly returns over those
           same h months.
  S3       h-month return / standard deviation over the 12-month window.
  S4       36-month-beta residual sum / standard deviation of those residuals
           over the same h months.

Every variant z-scores each horizon across sectors and averages the three
z-scores, exactly the way strategy_lib.composite builds the production score.

HOLDOUT PROTECTION
Variants only ever receive data cut at IS_END, so 2019+ cannot be computed for
them. The only full-history run is the S0 identity check against production,
and it prints a pass/fail rather than performance.

WARM-UP
A variant needs enough history for all 11 sectors. Until then the sleeve uses
the production score, so the book is continuous, and those months are excluded
from that variant's evaluation. Two samples are reported:
  own     from each variant's first valid month
  common  from the first month every variant is valid (like-for-like)

Run:  python research/scripts/sector_signal_research.py
"""
import os
import warnings

import numpy as np
import pandas as pd

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "strategy"))  # for strategy_lib
import strategy_lib as S

warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = HERE
HORIZONS = (3, 6, 12)
LAMS = (8.0, 0.0)
N_BOOT, BLOCK, SEED = 10_000, 12, 20261123
IS_END = pd.Timestamp(S.IS_END)


# ---- signals ------------------------------------------------------------------------
def average_z(by_horizon):
    """Same construction as strategy_lib.composite."""
    return sum(S.cs_z(by_horizon[h]) for h in HORIZONS) / len(HORIZONS)


def residual_panels(monthly, beta_window):
    """Residual sum and residual volatility per formation date and horizon.

    One beta is estimated at each formation date from the beta_window months
    ending at that date, then applied to the skip-month residuals. Nothing
    after the formation date is used."""
    sectors = monthly[S.SECTORS].to_numpy()
    spy = monthly["SPY"].to_numpy()
    n_t, n_a = sectors.shape
    sums = {h: np.full((n_t, n_a), np.nan) for h in HORIZONS}
    vols = {h: np.full((n_t, n_a), np.nan) for h in HORIZONS}
    for pos in range(n_t):
        start = pos - beta_window + 1
        if start < 0 or pos < max(HORIZONS):
            continue
        x = spy[start:pos + 1]
        if np.isnan(x).any():
            continue
        for a in range(n_a):
            y = sectors[start:pos + 1, a]
            if np.isnan(y).any():
                continue
            beta = float(x @ y) / float(x @ x)
            for h in HORIZONS:
                res = sectors[pos - h:pos, a] - beta * spy[pos - h:pos]
                if np.isnan(res).any():
                    continue
                sums[h][pos, a] = res.sum()
                vols[h][pos, a] = res.std(ddof=1)
    wrap = lambda arr: pd.DataFrame(arr, index=monthly.index, columns=S.SECTORS)
    return ({h: wrap(v) for h, v in sums.items()},
            {h: wrap(v).replace(0, np.nan) for h, v in vols.items()})


def build_scores(monthly):
    r = monthly[S.SECTORS]
    raw = {h: S.mom(r, 1, h) for h in HORIZONS}
    own_vol = {h: r.shift(1).rolling(h).std().replace(0, np.nan) for h in HORIZONS}
    vol12 = own_vol[12]

    scores = {"S0": S.composite(monthly, S.SECTORS)}
    for n in (12, 36, 60):
        res_sum, _ = residual_panels(monthly, n)
        scores[f"S1-{n}"] = average_z(res_sum)
    scores["S2"] = average_z({h: raw[h] / own_vol[h] for h in HORIZONS})
    scores["S3"] = average_z({h: raw[h] / vol12 for h in HORIZONS})
    res36, resvol36 = residual_panels(monthly, 36)
    scores["S4"] = average_z({h: res36[h] / resvol36[h] for h in HORIZONS})
    return scores


def with_warmup(score, base):
    """Use the production score until all 11 sectors have a valid variant score."""
    ready = score[S.SECTORS].notna().all(axis=1)
    first = ready[ready].index[0]
    out = score.copy()
    out.loc[out.index < first] = base.loc[out.index < first]
    return out, first


# ---- sector sleeve: strategy_lib.sector_weight_path with score and lam as inputs ----
def sector_path(DI, scores, style_path, lam, w_style=S.W_STYLE, w_sector=S.W_SECTOR):
    reg = DI["regime"].reindex(scores.index).fillna(1.0)
    rets = DI["rets"]
    out, cur_held = {}, set()
    for t in scores.index:
        row = scores.loc[t].dropna()
        if len(row) < S.TOP_K:
            continue
        if reg.loc[t] == 0.0:
            out[t] = pd.Series({S.pick_defensive(DI, t): 1.0})
            cur_held = set()
            continue
        names = list(row.index)
        sw = style_path.get(t, pd.Series(dtype=float))
        spriced = [a for a in sw.index if a in rets.columns]
        hist = rets[list(dict.fromkeys(names + spriced))].loc[:t].tail(S.GAME_CORR_DAYS)
        C = hist.corr().fillna(0.0)
        corr = C.loc[names, names].to_numpy(copy=True)
        np.fill_diagonal(corr, 1.0)
        exo = np.zeros(len(names))
        for a in spriced:
            exo += w_style * float(sw[a]) * C.loc[names, a].to_numpy()
        eq = pd.Series(S.congestion_equilibrium(row.to_numpy(), corr, lam=lam, exo=exo,
                                                total=w_sector), index=names)
        ranked = eq.rank(ascending=False)
        entry = set(ranked[ranked <= S.TOP_K].index)
        hold = set(ranked[ranked <= S.BUFFER_EXIT].index)
        held = sorted((cur_held & hold) | entry)
        out[t] = pd.Series(1.0 / len(held), index=held)
        cur_held = set(held)
    return out


def run_book(DI, scores, style_path, lam):
    """Mirror of strategy_lib.build_strategy."""
    sectors = sector_path(DI, scores, style_path, lam)
    book = S.combine_paths([(style_path, S.W_STYLE), (sectors, S.W_SECTOR)])
    t_last = S.latest_formation(DI, style_path, sectors)
    book = {t: w for t, w in book.items() if t <= t_last}
    r, stats = S.simulate(book, DI, book_vt=S.BOOK_VT, cost_bps=S.COST_BPS)
    return dict(r=r, stats=stats, sectors=sectors, book=book)


def truncate(DI):
    """Copy of the data with nothing after IS_END. exec_rets is dropped because it
    is built with a one-day forward shift and the simulator does not use it."""
    return {k: v.loc[:IS_END] for k, v in DI.items() if k != "exec_rets"}


# ---- step 0 -------------------------------------------------------------------------
def step0(DI):
    r, st = S.build_strategy(DI=DI)
    is_m = S.metrics(r, S.in_sample_mask(r.index))
    last_complete = S.latest_formation(DI, S.style_weight_path(DI),
                                       S.sector_weight_path(DI, S.style_weight_path(DI)))
    full_m = S.metrics(r.loc[:last_complete])
    print(f"[step 0] production: IS Sharpe {is_m['sharpe']:.4f} | full Sharpe through "
          f"{last_complete.date()} {full_m['sharpe']:.4f} | turnover {st['ann_turnover']:.2f}x")
    if abs(is_m["sharpe"] - 0.924) > 0.001 or abs(full_m["sharpe"] - 0.92) > 0.005 \
            or abs(st["ann_turnover"] - 6.9) > 0.05:
        raise SystemExit("STOP: production does not match the expected values.")

    style = S.style_weight_path(DI)
    copy = run_book(DI, S.composite(DI["monthly"], S.SECTORS), style, S.GAME_LAM)
    same = copy["r"].index.equals(r.index) and np.array_equal(copy["r"].values, r.values) \
        and copy["stats"]["ann_turnover"] == st["ann_turnover"]
    if not same:
        raise SystemExit("STOP: the S0 copy does not match build_strategy.")
    print("[step 0] S0 copy vs build_strategy, full history: exact match")
    return r


# ---- evaluation ---------------------------------------------------------------------
def sharpe_arrays(x, rf):
    return (x - rf).mean(axis=-1) * 12 / (x.std(axis=-1, ddof=1) * np.sqrt(12))


def block_ci(v, b, rf):
    """Paired circular block bootstrap of Sharpe(v) - Sharpe(b)."""
    T = len(v)
    rng = np.random.default_rng(SEED)
    n_blocks = int(np.ceil(T / BLOCK))
    starts = rng.integers(0, T, size=(N_BOOT, n_blocks))
    idx = ((starts[:, :, None] + np.arange(BLOCK)) % T).reshape(N_BOOT, -1)[:, :T]
    diff = sharpe_arrays(v[idx], rf[idx]) - sharpe_arrays(b[idx], rf[idx])
    return tuple(np.percentile(diff, [2.5, 97.5]))


def window_turnover(run, DI, first_month):
    """Annualized turnover from trades executed in the evaluation window."""
    p = first_month - pd.offsets.MonthEnd(1)
    nav = run["stats"]["nav"]
    total = run["stats"]["ann_turnover"] * len(nav) / 252
    prior = {t: w for t, w in run["book"].items() if t < p}
    before = 0.0
    if prior:
        _, st = S.simulate(prior, DI, book_vt=S.BOOK_VT, cost_bps=S.COST_BPS)
        before = st["ann_turnover"] * len(st["nav"]) / 252
    return (total - before) / int((nav.index > p).sum()) * 252


def verdict(d, lo, hi):
    if abs(d) < 0.03:
        return "noise"
    if abs(d) < 0.05:
        return "borderline noise"
    return "beyond noise" if lo > 0 or hi < 0 else "large but CI spans 0"


def evaluate(name, lam, run, base, DI, first, sample):
    idx = run["r"].index[run["r"].index >= first]
    v = run["r"].reindex(idx)
    b = base["r"].reindex(idx)
    rf = DI["tbill_m"].reindex(idx).fillna(0.0)
    m = S.metrics(v, rf=rf)
    b_m = S.metrics(b, rf=rf)

    forms = [t for t in run["sectors"]
             if t + pd.offsets.MonthEnd(1) in idx and t in base["sectors"]]
    differs = np.mean([set(run["sectors"][t].index) != set(base["sectors"][t].index)
                       for t in forms])
    counts = [sum(a in S.SECTORS for a in run["sectors"][t].index) for t in forms]
    counts = [c for c in counts if c > 0]

    row = dict(sample=sample, variant=name, lam=int(lam), start=idx[0].strftime("%Y-%m"),
               months=len(idx), sharpe=m["sharpe"], ann_ret=m["ann_ret"], ann_vol=m["ann_vol"],
               max_dd=m["max_dd"], turnover=window_turnover(run, DI, idx[0]),
               avg_sectors=float(np.mean(counts)), pct_months_differ=float(differs),
               base_sharpe=b_m["sharpe"], d_sharpe=m["sharpe"] - b_m["sharpe"])
    if name == "S0":
        row.update(ci_low=0.0, ci_high=0.0, verdict="baseline")
    else:
        lo, hi = block_ci(v.to_numpy(), b.to_numpy(), rf.to_numpy())
        row.update(ci_low=lo, ci_high=hi, verdict=verdict(row["d_sharpe"], lo, hi))
    return row


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("[data] loading ...")
    full = S.get_data()
    production = step0(full)

    DI = truncate(full)
    if DI["close"].index.max() > IS_END:
        raise SystemExit("STOP: research data extends past the in-sample end.")
    style = S.style_weight_path(DI)
    raw_scores = build_scores(DI["monthly"])
    base_score = raw_scores["S0"]

    scores, ready = {"S0": base_score}, {}
    for name, score in raw_scores.items():
        if name != "S0":
            scores[name], ready[name] = with_warmup(score, base_score)
    common_ready = max(ready.values())

    runs = {}
    for lam in LAMS:
        for name, score in scores.items():
            print(f"[run] {name} lam={lam:g}")
            runs[name, lam] = run_book(DI, score, style, lam)
            if runs[name, lam]["r"].index.max() > IS_END:
                raise SystemExit("STOP: a variant produced a post-2018 return.")

    prod_is = production[S.in_sample_mask(production.index)]
    s0_is = runs["S0", S.GAME_LAM]["r"]
    if not (s0_is.index.equals(prod_is.index) and np.allclose(s0_is, prod_is, atol=1e-12, rtol=0)):
        raise SystemExit("STOP: truncated S0 does not match production in-sample.")
    print("[step 0] truncated S0 vs production, 2001-2018: match")

    rows = []
    for lam in LAMS:
        base = runs["S0", lam]
        for name in scores:
            own = base["r"].index.min() if name == "S0" else \
                run_first_month(base["r"], ready[name])
            rows.append(evaluate(name, lam, runs[name, lam], base, DI, own, "own"))
            rows.append(evaluate(name, lam, runs[name, lam], base, DI,
                                 run_first_month(base["r"], common_ready), "common"))
    table = pd.DataFrame(rows)
    table.to_csv(os.path.join(OUT_DIR, "..", "tables", "sector_signal", "in_sample_results.csv"), index=False)

    dispersion = pd.Series({k: v.loc[v.index >= common_ready].std(axis=1).mean()
                            for k, v in scores.items()}, name="avg_cross_sectional_std")
    dispersion.to_csv(os.path.join(OUT_DIR, "..", "tables", "sector_signal", "score_dispersion.csv"))

    show = table.copy()
    for c in ("ann_ret", "ann_vol", "max_dd", "pct_months_differ"):
        show[c] = (show[c] * 100).round(1)
    for c in ("sharpe", "base_sharpe", "d_sharpe", "ci_low", "ci_high"):
        show[c] = show[c].round(3)
    show["turnover"] = show["turnover"].round(2)
    show["avg_sectors"] = show["avg_sectors"].round(2)
    pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_rows", 100)
    for sample in ("common", "own"):
        for lam in LAMS:
            print(f"\n=== {sample} sample, lam={lam:g} ===")
            print(show[(show["sample"] == sample) & (show["lam"] == int(lam))]
                  .drop(columns=["sample", "lam"]).to_string(index=False))
    print("\nAverage cross-sectional std of final score (common sample):")
    print(dispersion.round(3).to_string())
    plot_backtest(full, runs, run_first_month(runs["S0", S.GAME_LAM]["r"], common_ready))
    print(f"\nSaved -> {OUT_DIR}")


def run_first_month(r, ready_date):
    """First earned month after the formation date where a signal became valid."""
    return r.index[r.index > ready_date][0]


def plot_backtest(full, runs, start):
    """Same layout as strategy/backtest.png; common in-sample window, lam = 8 (production)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mtick
    cut = lambda x: x[(x.index >= start) & (x.index <= IS_END)].dropna()
    spy = full["monthly"]["SPY"]
    agg = full["monthly"]["AGG"].where(full["monthly"]["AGG"].notna(), full["tbill_m"])
    bal = (0.6 * spy + 0.4 * agg).dropna()
    lines = [("S0 production", runs["S0", S.GAME_LAM]["r"], "#1f77b4", 2.4),
             ("S1-36 residual (headline)", runs["S1-36", S.GAME_LAM]["r"], "#2ca02c", 2.0),
             ("S2 return / own vol", runs["S2", S.GAME_LAM]["r"], "#9467bd", 1.0),
             ("S3 return / 12m vol", runs["S3", S.GAME_LAM]["r"], "#8c564b", 1.0),
             ("S4 residual / residual vol", runs["S4", S.GAME_LAM]["r"], "#e377c2", 1.0),
             ("SPY", spy, "#d62728", 1.2), ("60/40", bal, "#ff7f0e", 1.2)]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), gridspec_kw={"height_ratios": [2.2, 1]})
    for label, x, c, lw in lines:
        ax1.plot((1 + cut(x)).cumprod(), label=label, color=c, lw=lw)
    ax1.set_yscale("log")
    ax1.set_title(f"Sector-sleeve signals -- IN-SAMPLE {start:%Y-%m} to 2018 "
                  "(full book; crowding lam = 8; net 10 bps;\nrebalance offset 0 of 4, single offset; see tables for offset averages)")
    ax1.set_ylabel("Growth of $1"); ax1.legend(loc="upper left"); ax1.grid(alpha=0.3)
    for label, x, c, _ in [lines[0], lines[1]]:
        eq = (1 + cut(x)).cumprod()
        dd = eq / eq.cummax() - 1
        if label == "S0 production":
            ax2.fill_between(eq.index, dd, 0, color="#b0b0b0", alpha=0.7, label=label)
        else:
            ax2.plot(eq.index, dd, color=c, lw=1.8, label=label)
    ax2.set_title("Drawdown: production (grey area) vs S1-36 residual (line); rebalance offset 0 of 4"); ax2.legend(); ax2.grid(alpha=0.3)
    ax2.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v:.0%}"))
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "..", "results", "sector_signal_insample.png")
    plt.savefig(out, dpi=150)
    plt.close(fig)
    print(f"Saved -> {out}")


if __name__ == "__main__":
    main()
