
import datetime as dt
import glob
import os
import pandas as pd
import io
import requests


WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def load_existing() -> pd.DataFrame:
    files = glob.glob("S&P 500 Historical Components & Changes(*).csv")
    if not files:
        raise FileNotFoundError(
            "No 'S&P 500 Historical Components & Changes(MM-DD-YYYY).csv' "
            "found in current folder."
        )
    newest = max(files, key=os.path.getmtime)
    print(f"Loading: {newest}")
    df = pd.read_csv(newest)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)

def scrape_wiki_changes() -> pd.DataFrame:
    """
    Scrape the 'Selected changes' table from Wikipedia using requests
    (avoids urllib SSL cert issues on macOS).
    """
    headers = {"User-Agent": "Mozilla/5.0 (QUANTT research script)"}
    resp = requests.get(WIKI_URL, headers=headers, timeout=20)
    resp.raise_for_status()

    tables = pd.read_html(io.StringIO(resp.text))

    changes = None
    for t in tables:
        flat = ["|".join(map(str, c)) if isinstance(c, tuple) else str(c)
                for c in t.columns]
        if any("Added" in c for c in flat) and any("Removed" in c for c in flat):
            changes = t
            break
    if changes is None:
        raise RuntimeError("Couldn't find the 'Selected changes' table on Wikipedia.")

    flat_cols = []
    for c in changes.columns:
        if isinstance(c, tuple):
            top, sub = c[0], c[1] if len(c) > 1 else ""
            if "Date" in top:
                flat_cols.append("date")
            elif "Added" in top and "Ticker" in sub:
                flat_cols.append("add_ticker")
            elif "Removed" in top and "Ticker" in sub:
                flat_cols.append("remove_ticker")
            else:
                flat_cols.append(f"{top}_{sub}")
        else:
            flat_cols.append(str(c))
    changes.columns = flat_cols
    changes = changes[["date", "add_ticker", "remove_ticker"]].copy()

    changes["date"] = pd.to_datetime(changes["date"], errors="coerce")
    for col in ("add_ticker", "remove_ticker"):
        changes[col] = (
            changes[col]
            .astype(str)
            .str.strip()
            .replace({"nan": "", "—": "", "-": ""})
        )
    changes = changes.dropna(subset=["date"])
    return changes.sort_values("date").reset_index(drop=True)


def apply_changes(df: pd.DataFrame, changes: pd.DataFrame) -> pd.DataFrame:
    """For each change AFTER the last date in df, append a new row."""
    last_date = df["date"].max()
    today = pd.Timestamp(dt.date.today())
    new_changes = changes[(changes["date"] > last_date) & (changes["date"] <= today)]
    print(f"Existing data ends: {last_date.date()}")
    print(f"Found {len(new_changes)} change(s) between "
          f"{last_date.date()} and {today.date()}")

    if new_changes.empty:
        return df

    # Group by date — multiple add/remove rows can share a date
    rows = []
    current = set(df.iloc[-1]["tickers"].split(","))
    for date, grp in new_changes.groupby("date"):
        adds = {t for t in grp["add_ticker"] if t}
        removes = {t for t in grp["remove_ticker"] if t}
        current = (current | adds) - removes
        rows.append({"date": date, "tickers": ",".join(sorted(current))})
        print(f"  {date.date()}: +{sorted(adds) or '—'}  −{sorted(removes) or '—'}  "
              f"-> {len(current)} tickers")

    return pd.concat([df, pd.DataFrame(rows)], ignore_index=True)


def main():
    df = load_existing()
    changes = scrape_wiki_changes()
    df_out = apply_changes(df, changes)

    today_str = dt.date.today().strftime("%m-%d-%Y")
    out_name = f"S&P 500 Historical Components & Changes({today_str}).csv"
    # Write in the same format as upstream: date column + tickers column, no index
    df_out_to_write = df_out.copy()
    df_out_to_write["date"] = df_out_to_write["date"].dt.strftime("%Y-%m-%d")
    df_out_to_write.to_csv(out_name, index=False)

    print(f"\nWrote: {out_name}")
    print(f"Total rows: {len(df_out_to_write)} "
          f"({df_out['date'].min().date()} -> {df_out['date'].max().date()})")


if __name__ == "__main__":
    main()