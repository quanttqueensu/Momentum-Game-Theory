"""Game theory layer: capital-competition congestion game, three modes.

Mechanism: the top-2N momentum candidates are players competing for the
portfolio's capital. Allocating weight w_i to ETF i earns its momentum score
mu_i but pays a congestion cost lambda * w_i * (rho @ w)_i that grows with how
much capital already sits in assets correlated with i. Correlated winners
(e.g. XLK / IWF / MTUM in a tech run) share one "capital pool" instead of
being triple-counted as independent bets. This is a potential game: its Nash
equilibrium maximizes  U(w) = mu.w - (lambda/2) w' rho w  on the simplex,
which replicator dynamics finds reliably.

Modes (cfg.game_mode) — all preserve the momentum layer's invested fraction,
so ablation differences are pure composition/timing effects:
  "selector"  - equilibrium decides WHICH top_n ETFs to hold from the top-2N
                pool, equal weight decides sizing. Rationale: raw equilibrium
                weights are too concentrated; equal weight is hard to beat as
                a sizing rule, so use the game only for substitution.
  "sizing"    - hold the equilibrium weights directly (documented negative
                result: concentrates and underperforms at every lambda).
  "crowdfade" - comomentum throttle: when avg pairwise correlation of the
                held basket is in the top decile of its own history, scale
                invested fraction by crowd_cut (momentum-crash insurance).
"""

import numpy as np
import pandas as pd

from config import Config
from signals import base_weights, momentum_scores, rebalance_dates


def congestion_equilibrium(mu: np.ndarray, corr: np.ndarray, lam: float,
                           iters: int = 300, eta: float = 0.1) -> np.ndarray:
    w = np.full(len(mu), 1.0 / len(mu))
    for _ in range(iters):
        grad = mu - lam * corr @ w
        w = w * np.exp(eta * (grad - grad.max()))  # shift for numerical stability
        w /= w.sum()
    return w


def _equilibrium_rows(px: pd.DataFrame, cfg: Config, as_selector: bool) -> pd.DataFrame:
    z, raw = momentum_scores(px, cfg)
    rets = px.pct_change()
    dates = rebalance_dates(px, cfg)
    rows = []
    for t in dates:
        zt, rawt = z.loc[t], raw.loc[t]
        pool = zt.dropna()
        if cfg.abs_filter:
            pool = pool[rawt[pool.index] > 0]
        invested = min(len(pool), cfg.top_n) / cfg.top_n
        w = pd.Series(0.0, index=px.columns)
        if invested > 0:
            cands = pool.nlargest(cfg.game_pool)
            corr = rets[cands.index].loc[:t].tail(cfg.corr_lookback).corr().to_numpy()
            eq = congestion_equilibrium(cands.to_numpy(), corr, cfg.crowding_aversion)
            if as_selector:
                picks = pd.Series(eq, index=cands.index).nlargest(min(cfg.top_n, len(cands))).index
                w[picks] = invested / len(picks)
            else:
                eq[eq < cfg.min_weight] = 0.0
                eq /= eq.sum()
                w[cands.index] = eq * invested
        rows.append(w)
    return pd.DataFrame(rows, index=dates)


def _crowdfade(px: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    base = base_weights(px, cfg)
    rets = px.pct_change()
    vals = {}
    for t in base.index:
        held = base.loc[t]
        held = held[held > 0].index
        if len(held) < 2:
            vals[t] = np.nan
            continue
        c = rets[held].loc[:t].tail(cfg.corr_lookback).corr().to_numpy()
        vals[t] = c[np.triu_indices(len(held), 1)].mean()
    crowd = pd.Series(vals)
    # percentile vs the signal's own expanding history (3y burn-in, no look-ahead)
    pct = crowd.expanding(36).apply(lambda x: (x.iloc[-1] >= x).mean())
    scale = pd.Series(1.0, index=base.index)
    scale[pct > cfg.crowd_thresh] = cfg.crowd_cut
    return base.mul(scale, axis=0)


def game_weights(px: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    if cfg.game_mode == "selector":
        return _equilibrium_rows(px, cfg, as_selector=True)
    if cfg.game_mode == "sizing":
        return _equilibrium_rows(px, cfg, as_selector=False)
    if cfg.game_mode == "crowdfade":
        return _crowdfade(px, cfg)
    raise ValueError(cfg.game_mode)
