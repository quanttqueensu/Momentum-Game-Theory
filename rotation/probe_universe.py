"""Probe yfinance data availability for the candidate ETF universe.

Downloads adjusted close for all candidates, reports first/last date and row
count per ticker, and caches the price panel for the backtest to reuse.
"""

from pathlib import Path

import pandas as pd
import yfinance as yf

CANDIDATES = {
    # Sector SPDRs
    "XLK": "Tech sector", "XLF": "Financials", "XLE": "Energy", "XLV": "Health care",
    "XLY": "Consumer disc.", "XLP": "Consumer staples", "XLI": "Industrials",
    "XLB": "Materials", "XLU": "Utilities", "XLRE": "Real estate", "XLC": "Comm. services",
    # Factor / style
    "MTUM": "Momentum factor", "QUAL": "Quality factor", "VLUE": "Value factor",
    "USMV": "Min volatility", "SIZE": "Size factor", "SPLV": "Low vol", "SPHB": "High beta",
    # US size / style
    "IWM": "Russell 2000", "IWF": "Russell 1000 growth", "IWD": "Russell 1000 value",
    "MDY": "S&P MidCap 400",
    # Global / country
    "EWJ": "Japan", "EWG": "Germany", "EWU": "UK", "EWC": "Canada", "EWA": "Australia",
    "EWZ": "Brazil", "EWY": "South Korea", "EWT": "Taiwan", "EWH": "Hong Kong",
    "EWS": "Singapore", "EWW": "Mexico", "EEM": "Emerging markets", "VGK": "Europe",
    "FXI": "China large cap", "INDA": "India",
    # Benchmarks (not tradeable in the strategy)
    "SPY": "BENCHMARK S&P 500", "QQQ": "BENCHMARK Nasdaq 100",
}

OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)


def main() -> None:
    tickers = list(CANDIDATES)
    px = yf.download(tickers, start="1996-01-01", auto_adjust=True, progress=False)["Close"]
    px = px[tickers]  # original order

    report = pd.DataFrame({
        "name": pd.Series(CANDIDATES),
        "first_date": px.apply(lambda s: s.first_valid_index()),
        "last_date": px.apply(lambda s: s.last_valid_index()),
        "rows": px.count(),
    })
    report["first_date"] = report["first_date"].dt.date
    report["last_date"] = report["last_date"].dt.date
    print(report.sort_values("first_date").to_string())

    missing = report[report["rows"] == 0]
    if not missing.empty:
        print("\nNO DATA:", ", ".join(missing.index))

    px.to_parquet(OUT / "prices.parquet")
    print(f"\nCached {px.shape[0]} rows x {px.shape[1]} tickers -> {OUT / 'prices.parquet'}")


if __name__ == "__main__":
    main()
