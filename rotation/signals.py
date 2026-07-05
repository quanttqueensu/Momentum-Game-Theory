"""Momentum signal layer.

Cross-sectional blended momentum: mean of z-scored 3m, 6m and 12-1m total
returns, computed only over ETFs that have full lookback history at that date
(point-in-time eligibility — late-inception ETFs simply join the pool once
they have enough history, so there is no look-ahead or survivorship issue).

An absolute (time-series) filter sends a slot to cash when an ETF's raw
blended momentum is negative, so breadth of positive momentum controls gross
exposure before the risk layer even acts.
"""

import numpy as np
import pandas as pd

from config import Config


def month_end_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(index.to_series().resample("ME").last().dropna())


def momentum_scores(px: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (z-score blend, raw blend) daily frames. NaN where ineligible."""
    l3, l6, l12 = cfg.lookbacks
    r3 = px / px.shift(l3) - 1
    r6 = px / px.shift(l6) - 1
    r12 = px.shift(cfg.skip) / px.shift(l12 + cfg.skip) - 1  # 12-1 momentum

    def zscore(df: pd.DataFrame) -> pd.DataFrame:
        return df.sub(df.mean(axis=1), axis=0).div(df.std(axis=1), axis=0)

    z = (zscore(r3) + zscore(r6) + zscore(r12)) / 3
    raw = (r3 + r6 + r12) / 3
    return z, raw


def rebalance_dates(px: pd.DataFrame, cfg: Config) -> pd.DatetimeIndex:
    """Month-ends from the first date with enough eligible ETFs onward."""
    z, _ = momentum_scores(px, cfg)
    me = month_end_dates(px.index)
    eligible = z.loc[me].notna().sum(axis=1)
    start = eligible[eligible >= cfg.min_eligible].index[0]
    return me[me >= start]


def base_weights(px: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Momentum-layer weights at each rebalance date (rows sum to invested fraction)."""
    z, raw = momentum_scores(px, cfg)
    dates = rebalance_dates(px, cfg)
    rows = []
    for t in dates:
        zt, rawt = z.loc[t], raw.loc[t]
        pool = zt.dropna()
        if cfg.abs_filter:
            pool = pool[rawt[pool.index] > 0]
        picks = pool.nlargest(cfg.top_n)
        w = pd.Series(0.0, index=px.columns)
        if len(picks):
            w[picks.index] = 1.0 / cfg.top_n  # unfilled slots stay in cash
        rows.append(w)
    return pd.DataFrame(rows, index=dates)


def equal_weights(px: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """No-momentum ablation: equal-weight every eligible ETF, fully invested."""
    z, _ = momentum_scores(px, cfg)
    dates = rebalance_dates(px, cfg)
    rows = []
    for t in dates:
        elig = z.loc[t].dropna().index
        w = pd.Series(0.0, index=px.columns)
        w[elig] = 1.0 / len(elig)
        rows.append(w)
    return pd.DataFrame(rows, index=dates)


def random_weights(px: pd.DataFrame, cfg: Config, seed: int) -> pd.DataFrame:
    """Agent 0: random top_n picks from the eligible pool, equal weight."""
    rng = np.random.default_rng(seed)
    z, _ = momentum_scores(px, cfg)
    dates = rebalance_dates(px, cfg)
    rows = []
    for t in dates:
        elig = list(z.loc[t].dropna().index)
        picks = rng.choice(elig, size=min(cfg.top_n, len(elig)), replace=False)
        w = pd.Series(0.0, index=px.columns)
        w[picks] = 1.0 / cfg.top_n
        rows.append(w)
    return pd.DataFrame(rows, index=dates)
