"""Performance metrics. Sharpe/Sortino use rf = 0 for simplicity and
comparability across the full sample.

Includes the rolling-12-month comparison vs SPY ("club survival" metrics):
the share of rolling 1-year windows in which the strategy beats SPY and the
worst 1-year shortfall — for an investor who benchmarks against SPY on a
~1-year horizon, this matters more than full-sample Sharpe.
"""

import numpy as np
import pandas as pd

ANN = 252


def perf_stats(r: pd.Series, spy: pd.Series, turnover: float | None = None) -> dict:
    r = r.dropna()
    spy = spy.reindex(r.index).fillna(0)
    cum = (1 + r).cumprod()
    years = len(r) / ANN

    cagr = cum.iloc[-1] ** (1 / years) - 1
    vol = r.std() * np.sqrt(ANN)
    sharpe = r.mean() / r.std() * np.sqrt(ANN) if r.std() > 0 else np.nan
    downside = r[r < 0].std() * np.sqrt(ANN)
    sortino = r.mean() * ANN / downside if downside > 0 else np.nan
    dd = (cum / cum.cummax() - 1).min()
    calmar = cagr / abs(dd) if dd < 0 else np.nan
    corr = r.corr(spy)

    r12 = cum / cum.shift(ANN) - 1
    spy12 = (1 + spy).cumprod().pipe(lambda c: c / c.shift(ANN) - 1)
    gap = (r12 - spy12).dropna()

    out = {
        "CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "Sortino": sortino,
        "MaxDD": dd, "Calmar": calmar, "Corr(SPY)": corr,
        "12m>SPY %": (gap >= 0).mean(), "Worst 12m vs SPY": gap.min(),
    }
    if turnover is not None:
        out["Turnover"] = turnover
    return out


def table(results: dict[str, dict]) -> pd.DataFrame:
    df = pd.DataFrame(results).T
    pct = ["CAGR", "Vol", "MaxDD", "12m>SPY %", "Worst 12m vs SPY"]
    for c in df.columns:
        if c in pct:
            df[c] = df[c].map(lambda x: f"{x:+.1%}" if pd.notna(x) else "-")
        elif c == "Turnover":
            df[c] = df[c].map(lambda x: f"{x:.1f}x" if pd.notna(x) else "-")
        else:
            df[c] = df[c].map(lambda x: f"{x:.2f}" if pd.notna(x) else "-")
    return df
