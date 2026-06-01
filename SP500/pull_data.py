

from __future__ import annotations

import datetime as dt
import glob
import os
import time
from pathlib import Path

import pandas as pd
import yfinance as yf
from tqdm import tqdm


# ----------------------------- CONFIG --------------------------------- #

BACKTEST_START = "2002-01-01"   # First rebalance date
BACKTEST_END   = "2024-12-31"   # Last rebalance date
PULL_START     = "2003-01-01"   # 2y buffer for the 12-1 momentum signal
PULL_END       = dt.date.today().strftime("%Y-%m-%d")

CHUNK_SIZE     = 50             # tickers per yf.download() call
MAX_RETRIES    = 3
RETRY_SLEEP    = 5              # seconds between retries

DATA_DIR       = Path("data")
CHUNK_DIR      = DATA_DIR / "_chunks"   # intermediate per-chunk parquets
OUT_FILE       = DATA_DIR / "prices_daily.parquet"
QUALITY_FILE   = DATA_DIR / "pull_quality_report.csv"
BENCHMARK      = "SPY"



def find_membership_csv() -> Path:
    """Find the most recent dated membership CSV in the current folder."""
    candidates = glob.glob("S&P 500 Historical Components & Changes(*).csv")
    if not candidates:
        raise FileNotFoundError(
            "No membership CSV found. Put 'S&P 500 Historical Components & "
            "Changes(MM-DD-YYYY).csv' in this folder first."
        )
    return Path(max(candidates, key=os.path.getmtime))


def build_universe(csv_path: Path) -> list[str]:
    """Union of every ticker appearing in any membership row within the window."""
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"])
    window = df[(df["date"] >= BACKTEST_START) & (df["date"] <= BACKTEST_END)]

    tickers: set[str] = set()
    for s in window["tickers"]:
        tickers.update(t.strip() for t in s.split(",") if t.strip())

    # Yahoo uses dashes, the membership file uses dots: BRK.B -> BRK-B
    normalized = sorted({t.replace(".", "-") for t in tickers})
    return normalized


# ------------------------- DOWNLOAD LOGIC ----------------------------- #

def download_chunk(tickers: list[str]) -> pd.DataFrame:
    """
    Download a chunk and return a long-format dataframe:
        date | ticker | open | high | low | close | volume

    Empty tickers are silently dropped here; we log them later by diffing
    requested vs returned.
    """
    print(f"  fetching tickers: {tickers}")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw = yf.download(
                tickers=tickers,
                start=PULL_START,
                end=PULL_END,
                interval="1d",
                auto_adjust=True,    # adjust for splits AND dividends
                group_by="ticker",
                threads=True,
                progress=False,
                actions=False,
            )
            break
        except Exception as e:
            if attempt == MAX_RETRIES:
                raise
            print(f"  chunk failed (attempt {attempt}): {e}; retrying...")
            time.sleep(RETRY_SLEEP)

    if raw.empty:
        return pd.DataFrame(columns=["date", "ticker", "open", "high",
                                     "low", "close", "volume"])

    # yfinance returns a wide multi-index frame when given multiple tickers.
    # Flatten it to long format.
    frames = []
    if len(tickers) == 1:
        # Single-ticker pulls have a flat column index
        df = raw.reset_index().assign(ticker=tickers[0])
        frames.append(df)
    else:
        for t in tickers:
            if t not in raw.columns.get_level_values(0):
                continue
            sub = raw[t].dropna(how="all").reset_index()
            if sub.empty:
                continue
            sub["ticker"] = t
            frames.append(sub)

    if not frames:
        return pd.DataFrame(columns=["date", "ticker", "open", "high",
                                     "low", "close", "volume"])

    out = pd.concat(frames, ignore_index=True)
    out.columns = [c.lower() if isinstance(c, str) else c for c in out.columns]
    out = out.rename(columns={"date": "date"})
    out = out[["date", "ticker", "open", "high", "low", "close", "volume"]]
    return out.dropna(subset=["close"])


def chunked(seq: list, n: int):
    """Yield successive n-sized chunks from seq."""
    for i in range(0, len(seq), n):
        yield seq[i:i + n]



def main():
    DATA_DIR.mkdir(exist_ok=True)
    CHUNK_DIR.mkdir(exist_ok=True)

    csv_path = find_membership_csv()
    print(f"Membership file:    {csv_path.name}")

    universe = build_universe(csv_path)
    universe_with_bench = sorted(set(universe + [BENCHMARK]))
    print(f"Universe size:      {len(universe)} tickers (+1 benchmark)")
    print(f"Pull range:         {PULL_START} -> {PULL_END}")
    print(f"Chunk size:         {CHUNK_SIZE}")
    print()

    # ---- Download in chunks, save each chunk to disk for resumability ----
    chunks = list(chunked(universe_with_bench, CHUNK_SIZE))
    requested_all: set[str] = set()
    received_all: set[str] = set()

    for i, chunk in enumerate(tqdm(chunks, desc="Pulling chunks")):
        chunk_file = CHUNK_DIR / f"chunk_{i:04d}.parquet"
        requested_all.update(chunk)

        print(f"Chunk {i+1}/{len(chunks)}: {chunk}")
        if chunk_file.exists():
            # Resume: skip already-downloaded chunks
            existing = pd.read_parquet(chunk_file)
            received_all.update(existing["ticker"].unique())
            continue

        df = download_chunk(chunk)
        if not df.empty:
            df.to_parquet(chunk_file, index=False)
            received_all.update(df["ticker"].unique())
        else:
            # Save an empty marker so we don't retry forever
            pd.DataFrame(columns=["date", "ticker", "open", "high",
                                  "low", "close", "volume"]
                         ).to_parquet(chunk_file, index=False)

    # ---- Merge all chunks into the final file ----
    print("\nMerging chunks...")
    chunk_files = sorted(CHUNK_DIR.glob("chunk_*.parquet"))
    parts = [pd.read_parquet(f) for f in chunk_files]
    final = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    final = final.sort_values(["ticker", "date"]).reset_index(drop=True)
    final.to_parquet(OUT_FILE, index=False)
    print(f"Wrote: {OUT_FILE}  ({len(final):,} rows, "
          f"{final['ticker'].nunique()} tickers)")

    # ---- Data-quality report ----
    missing = sorted(requested_all - received_all)
    # Partial = received but with <50% of expected trading days
    expected_days = len(pd.bdate_range(PULL_START, PULL_END))
    counts = final.groupby("ticker").size()
    partial = sorted(counts[counts < 0.5 * expected_days].index)

    report = pd.DataFrame({
        "ticker": list(requested_all),
    })
    report["status"] = report["ticker"].apply(
        lambda t: "missing" if t in missing
        else ("partial" if t in partial else "ok")
    )
    report["row_count"] = report["ticker"].map(counts).fillna(0).astype(int)
    report = report.sort_values(["status", "ticker"])
    report.to_csv(QUALITY_FILE, index=False)

    print(f"Wrote: {QUALITY_FILE}")
    print()
    print("=" * 50)
    print("Pull quality summary:")
    print(report["status"].value_counts().to_string())
    print("=" * 50)
    if missing:
        print(f"\nFirst 20 missing tickers (likely delisted): "
              f"{missing[:20]}")


if __name__ == "__main__":
    main()