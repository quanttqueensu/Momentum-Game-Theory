"""
strategy_core.py — shared logic for the residual-momentum strategy.

Single source of truth for: data loading, residual-momentum scoring, buffered
book construction, the comomentum crowding signal (with on-disk caching), the
crowding gate, volatility scaling, and metric/cost helpers.

The comomentum signal is the expensive part (≈50 daily regressions × ~230 months).
It only depends on the residuals, the prices, and a few params — none of which
change between backtest runs — so we cache it to parquet keyed by those inputs.
compute_comomentum() recomputes only when an input changes (or rebuild=True).
"""

from __future__ import annotations
import os
import json
import numpy as np
import pandas as pd

# ── Data ─────────────────────────────────────────────────────────────────────
def load_panels(residuals_path, prices_path, market="SPY", max_abs_ret=1.0):
    """Return (close, daily_ret, market_ret, monthly_ret, residuals)."""
    residuals = pd.read_parquet(residuals_path)
    residuals.index = pd.to_datetime(residuals.index)

    prices = pd.read_parquet(prices_path)
    prices["date"] = pd.to_datetime(prices["date"], unit="ms")
    close = prices.pivot(index="date", columns="ticker", values="close").sort_index()

    daily_ret   = close.pct_change(fill_method=None)
    market_ret  = daily_ret[market]
    monthly_ret = close.resample("ME").last().pct_change(fill_method=None)
    monthly_ret = monthly_ret.mask(monthly_ret.abs() > max_abs_ret)
    return close, daily_ret, market_ret, monthly_ret, residuals


# ── Signal ───────────────────────────────────────────────────────────────────
def residual_scores(residuals, skip=1, window=12):
    """Standardised residual momentum: sum/std of residuals over the formation
    window, skipping the most recent `skip` month(s). 12-1 = skip=1, window=12."""
    s = residuals.shift(skip).rolling(window)
    return s.sum() / s.std()


# ── Cross-sectional factor helpers (for the long-only strategy_v2) ───────────
def cs_zscore(panel):
    """Cross-sectional z-score each month: (x - row mean) / row std.
    Puts heterogeneous factors (momentum, low-vol, …) on one comparable scale
    so they can be averaged into a composite score."""
    return panel.sub(panel.mean(axis=1), axis=0).div(panel.std(axis=1), axis=0)


def low_vol_score(residuals, window=12):
    """Low idiosyncratic-volatility factor: NEGATIVE trailing residual vol, so a
    HIGH score = a LOW-vol (defensive) name. The classic low-volatility anomaly."""
    return -residuals.rolling(window).std()


# ── Long-only book construction (with optional rank buffering) ───────────────
def build_long_book(scores, monthly_ret, n_entry=50, n_exit=100,
                    use_buffer=True, inv_vol_weight=None):
    """Long-only top-N book each month; returns a frame indexed by formation date
    with columns: gross (next-month return), turnover (Σ|Δw|).

    Same rank-buffer hysteresis as build_book (a name stays in the book while it
    remains inside the wider `n_exit` band, only churning when it drops out), but
    long-only and fully invested (weights sum to 1).

    inv_vol_weight: optional frame (formation date × ticker) of a positive
    risk proxy (e.g. trailing daily vol). If given, names are weighted ∝ 1/vol
    (risk-balanced); otherwise equal-weighted.
    """
    dates = sorted(set(scores.index) & set(monthly_ret.index))
    prev_w = pd.Series(dtype=float)
    cur_long = set()
    out = []
    for i, t in enumerate(dates[:-1]):
        row = scores.loc[t].dropna()
        if len(row) < n_entry * 2:
            continue
        ranked = row.rank(ascending=False)          # 1 = best
        n = len(ranked)
        entry = set(ranked[ranked <= n_entry].index)
        if use_buffer:
            hold = set(ranked[ranked <= n_exit].index)
            longs = (cur_long & hold) | entry
        else:
            longs = entry
        longs = list(longs)

        if inv_vol_weight is not None and t in inv_vol_weight.index:
            iv = 1.0 / inv_vol_weight.loc[t, [c for c in longs if c in inv_vol_weight.columns]].replace(0, np.nan)
            iv = iv.dropna()
            w = (iv / iv.sum()) if len(iv) else pd.Series(1.0 / len(longs), index=longs)
        else:
            w = pd.Series(1.0 / len(longs), index=longs)

        allk = prev_w.index.union(w.index)
        turn = (w.reindex(allk).fillna(0) - prev_w.reindex(allk).fillna(0)).abs().sum()
        fwd = monthly_ret.loc[dates[i + 1]]
        common = w.index.intersection(fwd.dropna().index)
        gross = (w[common] * fwd[common]).sum()
        out.append({"date": t, "gross": gross, "turnover": turn, "n_held": len(longs)})
        prev_w, cur_long = w, set(longs)
    return pd.DataFrame(out).set_index("date")


# ── Book construction (with optional rank buffering) ─────────────────────────
def build_book(res_scores, monthly_ret, n_long=50, n_short=50,
               use_buffer=True, n_entry=50, n_exit=100):
    """Dollar-neutral L/S book each month; returns a frame indexed by formation
    date with columns: gross (next-month return), turnover (Σ|Δw|).

    Rank buffering (hysteresis): a name is in the book if it's a NEW entrant in
    the decile (top/bottom n_entry) OR an INCUMBENT still inside the wider band
    (top/bottom n_exit). This removes edge-of-decile churn.
    """
    dates = sorted(set(res_scores.index) & set(monthly_ret.index))
    prev_w = pd.Series(dtype=float)
    cur_long, cur_short = set(), set()
    out = []
    for i, t in enumerate(dates[:-1]):
        row = res_scores.loc[t].dropna()
        if len(row) < n_entry * 2:
            continue
        ranked = row.rank(ascending=False)          # 1 = best (winner)
        n = len(ranked)
        top_entry = set(ranked[ranked <= n_entry].index)
        bot_entry = set(ranked[ranked >  n - n_entry].index)

        if use_buffer:
            top_hold = set(ranked[ranked <= n_exit].index)
            bot_hold = set(ranked[ranked >  n - n_exit].index)
            longs  = (cur_long  & top_hold) | top_entry
            shorts = (cur_short & bot_hold) | bot_entry
        else:
            longs, shorts = top_entry, bot_entry
        longs -= shorts

        w = _equal_weights(longs, shorts)
        allk = prev_w.index.union(w.index)
        turn = (w.reindex(allk).fillna(0) - prev_w.reindex(allk).fillna(0)).abs().sum()

        fwd = monthly_ret.loc[dates[i + 1]]
        common = w.index.intersection(fwd.dropna().index)
        gross = (w[common] * fwd[common]).sum()
        out.append({"date": t, "gross": gross, "turnover": turn,
                    "n_long": len(longs), "n_short": len(shorts)})
        prev_w, cur_long, cur_short = w, longs, shorts
    return pd.DataFrame(out).set_index("date")


def _equal_weights(longs, shorts):
    w = pd.Series(0.0, dtype=float)
    if longs:  w = pd.concat([w, pd.Series(0.5 / len(longs),  index=list(longs))])
    if shorts: w = pd.concat([w, pd.Series(-0.5 / len(shorts), index=list(shorts))])
    return w.groupby(level=0).sum()


# ── Comomentum crowding signal (cached) ──────────────────────────────────────
def _market_residualise(block, mkt, min_days):
    mkt = mkt.reindex(block.index); good = mkt.notna()
    block, mkt = block.loc[good], mkt.loc[good]
    X = np.column_stack([np.ones(len(mkt)), mkt.to_numpy()])
    out = {}
    for col in block.columns:
        y = block[col]; m = y.notna()
        if m.sum() < min_days:
            continue
        beta, *_ = np.linalg.lstsq(X[m.values], y[m].to_numpy(), rcond=None)
        out[col] = pd.Series(y[m].to_numpy() - X[m.values] @ beta, index=y[m].index)
    return pd.DataFrame(out)


def _avg_pairwise_corr(resid_df):
    if resid_df.shape[1] < 2:
        return np.nan
    C = resid_df.corr(); n = C.shape[0]
    return (C.values.sum() - n) / (n * (n - 1))


def compute_comomentum(res_scores, daily_ret, market_ret, *,
                       n_winners=50, corr_days=252, min_days=200,
                       residuals_path, prices_path, formation=(1, 12),
                       cache_path="comomentum_cache.parquet", rebuild=False, verbose=True):
    """Average market-residualised pairwise correlation among the winner decile,
    over a trailing daily window. Cached to parquet keyed by the inputs below;
    recomputed only when an input changes or rebuild=True."""
    key = {
        "n_winners": n_winners, "corr_days": corr_days, "min_days": min_days,
        "formation": list(formation),
        "residuals_mtime": _mtime(residuals_path),
        "prices_mtime": _mtime(prices_path),
    }
    meta_path = cache_path + ".meta.json"
    if not rebuild and os.path.exists(cache_path) and os.path.exists(meta_path):
        if json.load(open(meta_path)) == key:
            if verbose:
                print(f"[comomentum] loaded cache → {cache_path}")
            return pd.read_parquet(cache_path)["comomentum"]

    if verbose:
        print("[comomentum] computing (no valid cache)…")
    records = []
    for t in res_scores.index:
        row = res_scores.loc[t].dropna()
        if len(row) < n_winners:
            continue
        winners = row.nlargest(n_winners).index
        window  = daily_ret.loc[:t].iloc[-corr_days:]
        block   = window[[c for c in winners if c in window.columns]]
        com_t   = _avg_pairwise_corr(_market_residualise(block, market_ret, min_days))
        records.append({"date": t, "comomentum": com_t})

    com = pd.DataFrame(records).set_index("date").dropna()
    com.to_parquet(cache_path)
    json.dump(key, open(meta_path, "w"), indent=2)
    if verbose:
        print(f"[comomentum] saved cache → {cache_path}  ({len(com)} months)")
    return com["comomentum"]


def _mtime(path):
    return os.path.getmtime(path) if os.path.exists(path) else None


# ── Overlays ─────────────────────────────────────────────────────────────────
def expanding_z(series, warmup=36):
    m = series.expanding(min_periods=warmup).mean()
    s = series.expanding(min_periods=warmup).std()
    return (series - m) / s


def gate_scalar(zscore, index, k=0.15, floor=0.0, cap=1.0):
    """Crowding gate exposure multiplier, aligned to `index` (1x before warmup)."""
    g = (1 - k * zscore).clip(lower=floor, upper=cap)
    return g.reindex(index).fillna(1.0)


def regime_filter(close, index, market="SPY", ma_days=200, floor=0.0):
    """Layer 4: de-risk when the market is below its long moving average.
    Returns an exposure multiplier (1x in bull regimes, `floor` in bear), aligned
    to `index`. Uses the month-end MA cross, known at formation (no look-ahead)."""
    spy = close[market]
    on = (spy > spy.rolling(ma_days).mean()).resample("ME").last()
    return on.reindex(index).fillna(True).map({True: 1.0, False: floor})


def vol_scalar(returns, index, window=6, lev_cap=2.0, is_mask=None):
    """Vol-targeting leverage. Target = mean realised vol over `is_mask` (so avg
    leverage ≈ 1x in-sample). Uses trailing realised vol, lagged (no look-ahead)."""
    rv = returns.rolling(window).std().shift(1)
    base = rv if is_mask is None else rv[is_mask]
    target = base.mean()
    v = (target / rv).clip(upper=lev_cap)
    return v.reindex(index).fillna(1.0)


# ── Metrics & costs ──────────────────────────────────────────────────────────
def net_of_cost(gross, traded, cost_bps=10):
    """gross return minus Σ|Δw|×cost. `traded` is the per-period turnover, optionally
    scaled by the layer's exposure."""
    return gross - traded * (cost_bps / 10000.0)


def metrics(returns, mask=None):
    r = (returns[mask] if mask is not None else returns).dropna()
    n = len(r)
    if n < 2:
        return dict(ann_ret=np.nan, ann_vol=np.nan, sharpe=np.nan, tstat=np.nan, max_dd=np.nan, n=n)
    ann_ret = (1 + r).prod() ** (12 / n) - 1
    ann_vol = r.std() * np.sqrt(12)
    sharpe  = ann_ret / ann_vol if ann_vol else np.nan
    tstat   = r.mean() / (r.std() / np.sqrt(n))
    eq      = (1 + r).cumprod()
    max_dd  = (eq / eq.cummax() - 1).min()
    return dict(ann_ret=ann_ret, ann_vol=ann_vol, sharpe=sharpe, tstat=tstat, max_dd=max_dd, n=n)


def in_sample_mask(index, start, end):
    return (index >= pd.Timestamp(start)) & (index <= pd.Timestamp(end))


def alpha_beta_ir(returns, benchmark, mask=None, ppy=12):
    """Benchmark-relative skill metrics. Regresses strategy returns on the
    benchmark (r = α + β·b + ε) for the CAPM alpha/beta, and measures the
    information ratio from the raw active return (r − b).

    Returns annualised alpha, beta, tracking error, information ratio, the
    annualised active return, and the monthly hit rate (% of months beating
    the benchmark). For an equal-weight selection vs an equal-weight benchmark
    β≈1, so the active return ≈ the alpha — and IR is the honest 'skill' number.
    """
    if mask is not None:
        returns = returns[mask]                          # mask aligns to returns.index
    df = pd.concat([returns.rename("r"), benchmark.rename("b")], axis=1).dropna()
    if len(df) < 6:
        return dict(alpha_ann=np.nan, beta=np.nan, te=np.nan, ir=np.nan,
                    active_ann=np.nan, hit=np.nan, n=len(df))
    beta, alpha_m = np.polyfit(df["b"], df["r"], 1)     # slope, intercept
    active = df["r"] - df["b"]
    te = active.std() * np.sqrt(ppy)
    ir = (active.mean() * ppy) / te if te else np.nan
    return dict(alpha_ann=alpha_m * ppy, beta=beta, te=te, ir=ir,
                active_ann=active.mean() * ppy, hit=(active > 0).mean(), n=len(df))
