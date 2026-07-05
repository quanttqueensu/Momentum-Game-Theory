"""Entry point: run the strategy, its ablations, Agent 0 and benchmarks,
and print side-by-side metric tables for each evaluation window.

Usage:
    python3 run.py                     # full ablation grid
    python3 run.py momentum            # single variant
    python3 run.py momentum game risk  # chosen variants
"""

import sys
from dataclasses import replace

import numpy as np
import pandas as pd

import data
import game
import signals
from config import Config
from engine import run_backtest
from metrics import perf_stats, table

WINDOWS = {
    "FULL HISTORY (first rebalance .. 2026-07)": (None, None),
    "SANITY WINDOW (2003 .. 2018)": ("2003-01-01", "2018-12-31"),
    "TRAILING 7Y (2019 .. 2026-07)": ("2019-01-01", None),
}

VARIANTS = {
    "momentum": "Momentum only (no game, no risk)",
    "game": "Momentum + game (no risk)",
    "mom_risk": "Momentum + risk (no game)",
    "full": "FULL: momentum + game + risk",
    "no_mom": "Equal-weight eligible + risk (no momentum)",
    "agent0": "Agent 0: random picks + risk (100 seeds, median)",
}

N_SEEDS = 100


def build(name: str, px: pd.DataFrame, cfg: Config):
    if name == "momentum":
        return signals.base_weights(px, cfg), replace(cfg, use_risk=False)
    if name == "game":
        return game.game_weights(px, cfg), replace(cfg, use_risk=False)
    if name == "mom_risk":
        return signals.base_weights(px, cfg), cfg
    if name == "full":
        return game.game_weights(px, cfg), cfg
    if name == "no_mom":
        return signals.equal_weights(px, cfg), cfg
    raise ValueError(name)


def main() -> None:
    chosen = sys.argv[1:] or list(VARIANTS)
    cfg = Config()
    px, bench = data.load()
    spy = bench["SPY"].pct_change()
    qqq = bench["QQQ"].pct_change()

    runs: dict[str, dict] = {}
    for name in chosen:
        if name == "agent0":
            continue
        w, c = build(name, px, cfg)
        runs[VARIANTS[name]] = run_backtest(w, px, c)
        print(f"ran {name}", flush=True)

    agent0_runs = []
    if "agent0" in chosen:
        for seed in range(N_SEEDS):
            w = signals.random_weights(px, cfg, seed)
            agent0_runs.append(run_backtest(w, px, cfg))
        print("ran agent0 x", N_SEEDS, flush=True)

    start = next(iter(runs.values()))["returns"].index[0] if runs else agent0_runs[0]["returns"].index[0]
    print(f"first day of strategy returns: {start.date()}")

    for title, (lo, hi) in WINDOWS.items():
        rows: dict[str, dict] = {}
        for label, res in runs.items():
            r = res["returns"].loc[lo:hi]
            rows[label] = perf_stats(r, spy, res["annual_turnover"])
        if agent0_runs:
            stats = [perf_stats(res["returns"].loc[lo:hi], spy, res["annual_turnover"])
                     for res in agent0_runs]
            df = pd.DataFrame(stats)
            med = df.median(numeric_only=True).to_dict()
            rows[VARIANTS["agent0"]] = med
            # where does the full strategy land in the random distribution?
            key = VARIANTS.get("full")
            if key in rows:
                pct = (df["CAGR"] < rows[key]["CAGR"]).mean()
                rows[VARIANTS["agent0"]]["12m>SPY %"] = med["12m>SPY %"]
                print(f"[{title}] full strategy CAGR beats {pct:.0%} of random seeds")
        for label, series in (("SPY (benchmark)", spy), ("QQQ (benchmark)", qqq)):
            r = series.loc[start:].loc[lo:hi]
            rows[label] = perf_stats(r, spy)
        print(f"\n=== {title} ===")
        print(table(rows).to_string())


if __name__ == "__main__":
    main()
