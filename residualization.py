
import numpy as np
import pandas as pd
import requests
import zipfile
import io
import glob
import os

PARQUET_PATH    = "SP500/data/prices_daily.parquet"
# look for the membership CSVs in the SP500 top-level folder; allow a
# simple wildcard to match the date in parentheses
MEMBERSHIP_GLOB = "SP500/S&P 500 Historical Components & Changes*.csv"
WINDOW          = 36       # rolling regression window, months
MAX_ABS_RET     = 1.0      # NaN any monthly return beyond +/-100% (bad prints)
WINSOR_Q        = 0.01     # clip residuals each month to [1%, 99%] cross-section

def fetch_ff_zip(zip_name):
    base = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    resp = requests.get(base + zip_name, verify=False, timeout=30)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        csv_name = next(n for n in zf.namelist() if n.upper().endswith(".CSV"))
        raw = zf.read(csv_name).decode("utf-8", errors="replace")

    rows = [l for l in raw.splitlines() if l.strip() and l.strip()[0].isdigit()]
    df = pd.read_csv(io.StringIO("\n".join(rows)), header=None, index_col=0)
    df.index = df.index.astype(str).str.strip()
    df = df[df.index.str.match(r"^\d{6}$")]              # drop annual summary rows
    df.index = pd.to_datetime(df.index, format="%Y%m") + pd.offsets.MonthEnd(0)
    return df.apply(pd.to_numeric, errors="coerce").dropna() / 100


ff = fetch_ff_zip("F-F_Research_Data_Factors_CSV.zip")
ff.columns = ["Mkt-RF", "SMB", "HML", "RF"]
print("Factors:", list(ff.columns),
      "| range:", ff.index.min().date(), "->", ff.index.max().date())

prices = pd.read_parquet(PARQUET_PATH)
prices["date"] = pd.to_datetime(prices["date"], unit="ms")

close = prices.pivot(index="date", columns="ticker", values="close").sort_index()
monthly_ret = close.resample("ME").last().pct_change()

# bad-print guard: a real large-cap never moves beyond +/-100% in a month,
# so treat such values as corrupt data and drop them (NaN, not clip).
bad = monthly_ret.abs() > MAX_ABS_RET
n_bad = int(bad.sum().sum())
monthly_ret = monthly_ret.mask(bad)
print(f"[guard] NaN'd {n_bad} monthly returns beyond +/-{MAX_ABS_RET:.0%}")


idx = monthly_ret.index.intersection(ff.index)
monthly_ret = monthly_ret.loc[idx]
F = ff.loc[idx]

excess_ret = monthly_ret.sub(F["RF"], axis=0)               # R_i - R_f
X_mat = np.column_stack([np.ones(len(F)), F[["Mkt-RF", "SMB", "HML"]].to_numpy()])
dates = excess_ret.index

def rolling_residuals(y_full, X_mat, window=WINDOW):
    n = len(y_full)
    out = np.full(n, np.nan)
    for end in range(window - 1, n):
        sl = slice(end - window + 1, end + 1)
        y, Xw = y_full[sl], X_mat[sl]
        if np.isnan(y).any():            # require a complete 36m window
            continue
        beta, *_ = np.linalg.lstsq(Xw, y, rcond=None)
        out[end] = (y - Xw @ beta)[-1]   # idiosyncratic return at month `end`
    return out

residuals = pd.DataFrame(index=dates, columns=excess_ret.columns, dtype=float)
for tic in excess_ret.columns:
    residuals[tic] = rolling_residuals(excess_ret[tic].to_numpy(), X_mat)

residuals = residuals.dropna(how="all")     # drop unfittable early months
print(f"[regression] raw residual panel: {residuals.shape}")

def load_membership():
    files = glob.glob(MEMBERSHIP_GLOB)
    if not files:
        raise FileNotFoundError(f"No membership CSV matching {MEMBERSHIP_GLOB}")
    newest = max(files, key=os.path.getmtime)
    print(f"[membership] loading: {os.path.basename(newest)}")
    m = pd.read_csv(newest)
    m["date"] = pd.to_datetime(m["date"])
    m = m.sort_values("date").reset_index(drop=True)
    m["members"] = m["tickers"].apply(lambda s: set(str(s).split(",")))
    return m[["date", "members"]]

def members_asof(membership, when):
    prior = membership[membership["date"] <= when]
    return prior.iloc[-1]["members"] if not prior.empty else set()

membership = load_membership()

# normalise ticker formats: Wikipedia uses '.', yfinance/parquet uses '-'
# (e.g. BRK.B vs BRK-B). Normalise membership sets to match price columns.
def norm(t):
    return t.replace(".", "-").strip()

membership["members"] = membership["members"].apply(lambda s: {norm(t) for t in s})

# diagnostic: how well do the universes line up at the most recent date?
latest = membership.iloc[-1]["members"]
price_tickers = set(residuals.columns)
only_mem  = sorted(latest - price_tickers)
only_px   = sorted(price_tickers - latest)
print(f"[membership] latest set: {len(latest)} names | "
      f"in membership not prices: {len(only_mem)} | "
      f"in prices not membership: {len(only_px)}")

# apply the gate, row by row
kept_before = int(residuals.notna().sum().sum())
for t in residuals.index:
    members = members_asof(membership, t)
    non_members = [c for c in residuals.columns if c not in members]
    residuals.loc[t, non_members] = np.nan
kept_after = int(residuals.notna().sum().sum())
print(f"[membership] residuals kept: {kept_before} -> {kept_after} "
      f"({kept_before - kept_after} masked as non-members)")


# ===========================================================================
# 6. Cross-sectional winsorisation (backstop against surviving bad prints)
#    Clip each month's residuals to its [1%, 99%] range so no single name
#    can dominate the decile ranking in Layer 1.
# ===========================================================================
def winsorise_row(row, q=WINSOR_Q):
    lo, hi = row.quantile(q), row.quantile(1 - q)
    return row.clip(lower=lo, upper=hi)

residuals = residuals.apply(winsorise_row, axis=1)



print("\n[Stage 1] final residual panel:", residuals.shape,
      "|", residuals.index.min().date(), "->", residuals.index.max().date())
print("Tickers with >=1 residual:", residuals.notna().any().sum())
print("Median names per month:",
      int(residuals.notna().sum(axis=1).median()))
print(residuals.iloc[-3:, :5].to_string())

residuals.to_parquet("residuals.parquet")
print("\nSaved -> residuals.parquet  (index=month-end, columns=ticker)")

# ===========================================================================
# 8. Diagnostic: which price tickers never appear in ANY membership snapshot?
# ===========================================================================
all_members = set()
for s in membership["members"]:
    all_members |= s

price_tickers = set(residuals.columns)
never_member = sorted(price_tickers - all_members)
print(f"\n[diag] price tickers never in ANY membership snapshot: {len(never_member)}")
print(never_member)

# names-per-month over time
print("\n[diag] names-per-month distribution:")
print(residuals.notna().sum(axis=1).describe())
print("\n[diag] median names per year:")
print(residuals.notna().sum(axis=1).groupby(residuals.index.year).median())