"""Load the cached price panel and split tradeable universe from benchmarks."""

from pathlib import Path

import pandas as pd

BENCHMARKS = ["SPY", "QQQ"]
DATA = Path(__file__).parent / "data" / "prices.parquet"


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (tradeable adjusted close, benchmark adjusted close)."""
    px = pd.read_parquet(DATA)
    px.index = pd.to_datetime(px.index)
    bench = px[BENCHMARKS]
    tradeable = px.drop(columns=BENCHMARKS)
    return tradeable, bench
