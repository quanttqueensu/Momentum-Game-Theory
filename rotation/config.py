"""All tunable parameters and layer switches in one place.

Every layer can be toggled independently so ablation runs are pure config
changes, never code edits.
"""

from dataclasses import dataclass


@dataclass
class Config:
    # --- momentum layer ---
    lookbacks: tuple = (63, 126, 252)  # ~3m / 6m / 12m in trading days
    skip: int = 21                     # 12m leg skips the most recent month (12-1 momentum)
    top_n: int = 6                     # positions held
    abs_filter: bool = True            # blended raw momentum must be > 0, else slot goes to cash
    min_eligible: int = 15             # backtest starts once this many ETFs have full history

    # --- game theory layer: capital-competition congestion game ---
    game_mode: str = "selector"        # "selector" | "sizing" | "crowdfade" (see game.py)
    game_pool: int = 12                # game is played over the top-2N momentum candidates
    crowding_aversion: float = 4.0     # lambda: congestion tax on correlated bets
    corr_lookback: int = 126           # trading days used for the correlation matrix
    min_weight: float = 0.02           # prune dust positions after the equilibrium solve
    crowd_thresh: float = 0.9          # crowdfade mode: percentile that triggers the fade
    crowd_cut: float = 0.5             # crowdfade mode: invested-fraction multiplier when triggered

    # --- risk layer ---
    vol_target: float = 0.18           # annualized target vol (~SPY's long-run realized vol)
    vol_lookback: int = 21             # trailing window for realized vol (fast reaction wins)
    max_exposure: float = 1.0          # long-only, no leverage
    dd_trigger: float = 0.15           # de-risk when strategy drawdown exceeds this
    dd_derisk: float = 0.7             # exposure multiplier while de-risked
    dd_recover: float = 0.10           # restore full exposure once drawdown is back above this

    # --- execution ---
    cost_bps: float = 5.0              # one-way cost (bps) per unit of turnover

    # --- layer switches (ablation) ---
    use_momentum: bool = True          # off -> equal-weight all eligible ETFs
    use_game: bool = True
    use_risk: bool = True
