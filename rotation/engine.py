"""Backtest engine and risk management layer.

Timeline: signals use data through month-end close t; positions are effective
from the next trading day (no look-ahead). Between rebalances positions drift
buy-and-hold. Cash earns 0% — deliberately conservative given 2022-2026 T-bill
yields.

Risk layer (both components applied as one exposure scalar at each rebalance):
  (a) vol targeting: exposure = min(vol_target / realized_vol, max_exposure)
      using the trailing vol of the strategy's own pre-risk return stream;
  (b) drawdown de-risking with hysteresis: exposure is halved once the
      realized (post-risk) equity drawdown exceeds dd_trigger and restored
      only after it recovers above dd_recover.

Costs: cost_bps one-way on every unit of weight traded, charged on the first
day of each holding period.
"""

import numpy as np
import pandas as pd

from config import Config


def _period_returns(w0: pd.Series, rets: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Daily portfolio returns and end-of-period drifted weights for one holding period."""
    gross = (1 + rets.fillna(0)).cumprod()
    value = gross.mul(w0, axis=1).sum(axis=1) + (1 - w0.sum())  # cash leg
    daily = value / value.shift(1).fillna(1.0) - 1
    w_end = gross.iloc[-1] * w0 / value.iloc[-1]
    return daily, w_end


def run_backtest(weights: pd.DataFrame, px: pd.DataFrame, cfg: Config) -> dict:
    """Simulate a weight schedule. Returns daily returns, turnover, exposure path."""
    rets = px.pct_change()
    dates = list(weights.index)

    # pass 1: pre-risk daily returns (used for the vol-targeting estimate)
    pre_parts = []
    for j, t in enumerate(dates):
        t_next = dates[j + 1] if j + 1 < len(dates) else rets.index[-1]
        period = rets.loc[rets.index > t].loc[:t_next]
        if period.empty:
            continue
        daily, _ = _period_returns(weights.loc[t], period)
        pre_parts.append(daily)
    pre = pd.concat(pre_parts)

    # pass 2: apply risk layer sequentially, charge costs on actual trades
    ann = np.sqrt(252)
    post_parts, exposures, one_way_turnover = [], [], 0.0
    w_prev_end = pd.Series(0.0, index=px.columns)
    equity, peak, derisked = 1.0, 1.0, False
    for j, t in enumerate(dates):
        t_next = dates[j + 1] if j + 1 < len(dates) else rets.index[-1]
        period = rets.loc[rets.index > t].loc[:t_next]
        if period.empty:
            continue

        scalar = 1.0
        if cfg.use_risk:
            hist = pre.loc[:t].tail(cfg.vol_lookback)
            if len(hist) >= cfg.vol_lookback:
                realized = hist.std() * ann
                if realized > 0:
                    scalar = min(cfg.vol_target / realized, cfg.max_exposure)
            dd = 1 - equity / peak
            if derisked and dd < cfg.dd_recover:
                derisked = False
            elif not derisked and dd > cfg.dd_trigger:
                derisked = True
            if derisked:
                scalar *= cfg.dd_derisk
        exposures.append((t, scalar))

        w_new = weights.loc[t] * scalar
        traded = (w_new - w_prev_end).abs().sum()
        one_way_turnover += traded / 2
        cost = traded * cfg.cost_bps / 1e4

        daily, w_prev_end = _period_returns(w_new, period)
        daily.iloc[0] -= cost
        post_parts.append(daily)
        equity *= float((1 + daily).prod())
        peak = max(peak, equity)

    post = pd.concat(post_parts)
    years = len(post) / 252
    return {
        "returns": post,
        "pre_risk_returns": pre,
        "annual_turnover": one_way_turnover / years,
        "exposure": pd.Series(dict(exposures)),
    }
