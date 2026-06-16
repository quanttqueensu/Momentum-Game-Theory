
import os
import glob
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")          # headless: save PNG without opening a GUI window
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

# ── Config ──────────────────────────────────────────────────────────────────
RESIDUALS_PATH  = "residuals.parquet"
PRICES_PATH     = "SP500/data/prices_daily.parquet"
MEMBERSHIP_GLOB = "SP500/S&P 500 Historical Components & Changes*.csv"

SCORE_WINDOW    = 12     # months in 13-2 lookback (t-13 to t-2)
N_LONG          = 50     # top-decile stocks to go long
N_SHORT         = 50     # bottom-decile stocks to short
MAX_ABS_RET     = 1.0    # NaN any monthly return beyond +/-100% (bad prints)

# ── In-sample window ─────────────────────────────────────────────────────────
# Start in 2012 to avoid the 2007-2011 period where ~27% of S&P 500 members
# have no yfinance data (GFC casualties + M&A targets with lost ticker history).
# That missing data distorts the short book in exactly the crash years.
# IS_END stays 2018-12 — expand both dates once all layers are complete.
IS_START = "2012-01-01"
IS_END   = "2018-12-31"

# ── 1. Load data ─────────────────────────────────────────────────────────────
residuals = pd.read_parquet(RESIDUALS_PATH)
residuals.index = pd.to_datetime(residuals.index)

prices = pd.read_parquet(PRICES_PATH)
prices["date"] = pd.to_datetime(prices["date"], unit="ms")
close = prices.pivot(index="date", columns="ticker", values="close").sort_index()
monthly_close  = close.resample("ME").last()
monthly_ret    = monthly_close.pct_change(fill_method=None)

# bad-print guard: NaN any monthly move beyond +/-100% so corrupt prints from
# delisted/illiquid names can't compound the backtest to infinity. This mirrors
# the guard residualization.py already applied before building residuals.parquet.
bad = monthly_ret.abs() > MAX_ABS_RET
n_bad = int(bad.sum().sum())
monthly_ret = monthly_ret.mask(bad)
print(f"[guard] NaN'd {n_bad} monthly returns beyond +/-{MAX_ABS_RET:.0%}")

print(f"Residuals: {residuals.shape}  |  {residuals.index.min().date()} → {residuals.index.max().date()}")
print(f"Monthly returns: {monthly_ret.shape}  |  {monthly_ret.index.min().date()} → {monthly_ret.index.max().date()}")

# ── 1b. Point-in-time S&P 500 membership (for the raw baseline's scoring) ─────
# residuals.parquet is already membership-masked, so the residual signal only
# ranks true members. To keep the raw 12-1 baseline apples-to-apples, we build a
# member-masked copy of monthly_ret and score the baseline off that.
def load_membership():
    files = glob.glob(MEMBERSHIP_GLOB)
    if not files:
        raise FileNotFoundError(f"No membership CSV matching {MEMBERSHIP_GLOB}")
    newest = max(files, key=os.path.getmtime)
    print(f"[membership] loading: {os.path.basename(newest)}")
    m = pd.read_csv(newest)
    m["date"] = pd.to_datetime(m["date"])
    m = m.sort_values("date").reset_index(drop=True)
    # normalise ticker format to match price columns: '.' -> '-' (BRK.B -> BRK-B)
    m["members"] = m["tickers"].apply(
        lambda s: {t.replace(".", "-").strip() for t in str(s).split(",")})
    return m[["date", "members"]]

def members_asof(membership, when):
    prior = membership[membership["date"] <= when]
    return prior.iloc[-1]["members"] if not prior.empty else set()

membership = load_membership()

monthly_ret_member = monthly_ret.copy()
for t in monthly_ret_member.index:
    members = members_asof(membership, t)
    non_members = [c for c in monthly_ret_member.columns if c not in members]
    monthly_ret_member.loc[t, non_members] = np.nan
kept = int(monthly_ret_member.notna().sum().sum())
print(f"[membership] member-masked return cells kept: {kept:,}")

# ── 2. Residual momentum scores (13-2 lookback, skip most recent month) ──────
# shift(1) skips t-1 (the most recent month); rolling(12) then covers t-13 to t-2
mom_sum = residuals.shift(1).rolling(SCORE_WINDOW).sum()
mom_std = residuals.shift(1).rolling(SCORE_WINDOW).std()
res_scores = mom_sum / mom_std   # standardised residual momentum score

# ── 3. Raw 12-1 momentum scores (baseline) ───────────────────────────────────
# Same skip-month convention; cumulative raw return over the same window.
# Scored off the member-masked returns so it ranks the same universe the
# residual signal does (true point-in-time S&P 500 members only).
# Clipped to the same start date as the residual signal so both strategies
# are evaluated over an identical time period — a fair apples-to-apples comparison.
raw_scores = monthly_ret_member.shift(1).rolling(SCORE_WINDOW).sum()
common_start = res_scores.dropna(how="all").index.min()
raw_scores = raw_scores.loc[common_start:]

print(f"\nBoth strategies start from: {common_start.date()}")
print(f"Score panel (residual): {res_scores.notna().sum().sum():,} valid observations")
print(f"Score panel (raw 12-1): {raw_scores.notna().sum().sum():,} valid observations")

# ── 4. Portfolio construction ─────────────────────────────────────────────────
def build_weights(score_row, n_long=N_LONG, n_short=N_SHORT):
    """Dollar-neutral long/short weights from a cross-sectional score row."""
    valid = score_row.dropna()
    if len(valid) < n_long + n_short:
        return None
    ranked = valid.rank(ascending=True)   # 1 = worst, N = best
    n      = len(ranked)
    longs  = ranked[ranked > n - n_long].index
    shorts = ranked[ranked <= n_short].index
    w = pd.Series(0.0, index=valid.index)
    w[longs]  = +0.5 / len(longs)
    w[shorts] = -0.5 / len(shorts)
    return w   # sums to ~0 (dollar-neutral)

# ── 5. Backtest engine ────────────────────────────────────────────────────────
def run_backtest(scores, label, holdings_csv=None):
    """
    For each month t in scores, form the portfolio and measure the return
    over the following month (t → t+1). Optionally log every month's
    long/short book to a CSV.
    """
    dates    = sorted(set(scores.index) & set(monthly_ret.index))
    result   = []
    holdings = []   # one row per (rebalance_date, ticker, side, weight)

    for i, t in enumerate(dates[:-1]):
        t_next = dates[i + 1]
        w = build_weights(scores.loc[t])
        if w is None:
            continue

        # record the book formed at month-end t (held through t_next)
        for tic, wt in w[w != 0].items():
            holdings.append({
                "rebalance_date": t.date(),
                "side"          : "LONG" if wt > 0 else "SHORT",
                "ticker"        : tic,
                "weight"        : round(wt, 5),
            })

        # forward returns: stocks need a price at both t and t+1
        fwd = monthly_ret.loc[t_next]
        common = w.index.intersection(fwd.dropna().index)
        if common.empty:
            continue

        w_adj  = w[common]
        port_r = (w_adj * fwd[common]).sum()

        result.append({
            "date"   : t_next,
            "return" : port_r,
            "n_long" : (w_adj > 0).sum(),
            "n_short": (w_adj < 0).sum(),
        })

    df = pd.DataFrame(result).set_index("date")
    print(f"\n[{label}] periods traded: {len(df)} | "
          f"avg long legs: {df['n_long'].mean():.0f} | "
          f"avg short legs: {df['n_short'].mean():.0f}")

    hold_df = pd.DataFrame(holdings)
    if holdings_csv:
        hold_df.to_csv(holdings_csv, index=False)
        print(f"[{label}] holdings log → {holdings_csv}  ({len(hold_df):,} position-rows)")
    return df["return"], hold_df


def print_latest_book(hold_df, label):
    """Print the most recent month's long/short book to the terminal."""
    last = hold_df["rebalance_date"].max()
    book = hold_df[hold_df["rebalance_date"] == last]
    longs  = sorted(book.loc[book["side"] == "LONG",  "ticker"])
    shorts = sorted(book.loc[book["side"] == "SHORT", "ticker"])
    print(f"\n──── {label}: book formed {last} ────")
    print(f"LONG  ({len(longs)}): {', '.join(longs)}")
    print(f"SHORT ({len(shorts)}): {', '.join(shorts)}")


res_returns, res_holdings = run_backtest(
    res_scores, "Residual Momentum", holdings_csv="holdings_residual.csv")
raw_returns, raw_holdings = run_backtest(
    raw_scores, "Raw 12-1 Momentum", holdings_csv="holdings_raw.csv")

print_latest_book(res_holdings, "Residual Momentum")

# ── 6. Performance metrics ────────────────────────────────────────────────────
def compute_metrics(returns, label):
    r       = returns.dropna()
    n       = len(r)
    ann_ret = (1 + r).prod() ** (12 / n) - 1
    ann_vol = r.std() * np.sqrt(12)
    sharpe  = ann_ret / ann_vol
    eq      = (1 + r).cumprod()
    max_dd  = (eq / eq.cummax() - 1).min()
    print(f"  {label:<25}  Ann.Ret={ann_ret:+.1%}  Vol={ann_vol:.1%}  "
          f"Sharpe={sharpe:.2f}  MaxDD={max_dd:.1%}  N={n}mo")
    return {"ann_ret": ann_ret, "ann_vol": ann_vol, "sharpe": sharpe, "max_dd": max_dd}

# clip both return series to in-sample window
is_start = pd.Timestamp(IS_START)
is_end   = pd.Timestamp(IS_END)
res_returns = res_returns[(res_returns.index >= is_start) & (res_returns.index <= is_end)]
raw_returns = raw_returns[(raw_returns.index >= is_start) & (raw_returns.index <= is_end)]

print("\n" + "="*70)
print(f"LAYER 1 PERFORMANCE — IN-SAMPLE  ({IS_START[:7]} → {IS_END[:7]})")
print("="*70)
m_res = compute_metrics(res_returns, "Residual Momentum")
m_raw = compute_metrics(raw_returns, "Raw 12-1 Momentum")

# ── 7. Equity curves ──────────────────────────────────────────────────────────
fig, axes = plt.subplots(3, 1, figsize=(13, 10),
                         gridspec_kw={"height_ratios": [3, 1.2, 1.2]})

eq_res = (1 + res_returns).cumprod()
eq_raw = (1 + raw_returns).cumprod()
dd_res = (eq_res / eq_res.cummax() - 1) * 100
dd_raw = (eq_raw / eq_raw.cummax() - 1) * 100

# key events within the 2012-2018 in-sample window
events = {
    "Taper\ntantrum":    "2013-06-30",
    "China\nflash crash":"2015-08-31",
    "Oil\ncrash":        "2016-01-31",
    "Trump\nelection":   "2016-11-30",
}

def add_events(ax, ypos_frac=0.92):
    ylo, yhi = ax.get_ylim()
    yspan = yhi - ylo
    for label, date in events.items():
        t = pd.Timestamp(date)
        ax.axvline(t, color="gray", lw=0.8, linestyle=":", alpha=0.7)
        ax.text(t, ylo + yspan * ypos_frac, label,
                fontsize=7, ha="center", va="top", color="dimgray",
                bbox=dict(fc="white", ec="none", alpha=0.6, pad=1))

# ── top: equity curves ───────────────────────────────────────────────────────
ax1 = axes[0]
ax1.plot(eq_res, label=f"Residual Momentum  (Sharpe {m_res['sharpe']:.2f})",
         lw=1.8, color="#1f77b4")
ax1.plot(eq_raw, label=f"Raw 12-1 Momentum  (Sharpe {m_raw['sharpe']:.2f})",
         lw=1.4, color="#ff7f0e", linestyle="--")
ax1.axhline(1, color="black", lw=0.6, linestyle=":")
ax1.set_title(f"Layer 1 — In-Sample Backtest ({IS_START[:7]} → {IS_END[:7]})", fontsize=13)
ax1.set_ylabel("Equity ($1 start)")
ax1.legend(loc="upper left", fontsize=10)
ax1.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"${x:.2f}"))
ax1.grid(alpha=0.3)
add_events(ax1)

# ── middle: residual drawdown (its own panel so scale isn't squashed by raw) ─
ax2 = axes[1]
ax2.fill_between(dd_res.index, dd_res, 0, alpha=0.45, color="#1f77b4")
ax2.plot(dd_res, lw=0.8, color="#1f77b4")
# annotate the max drawdown point
worst_date = dd_res.idxmin()
worst_val  = dd_res.min()
ax2.annotate(f"{worst_val:.1f}%\n{worst_date.strftime('%b %Y')}",
             xy=(worst_date, worst_val),
             xytext=(worst_date - pd.DateOffset(months=14), worst_val + 4),
             fontsize=8, color="#1f77b4",
             arrowprops=dict(arrowstyle="->", color="#1f77b4", lw=0.8))
ax2.set_ylabel("Residual DD (%)")
ax2.grid(alpha=0.3)
add_events(ax2, ypos_frac=0.12)

# ── bottom: raw drawdown ──────────────────────────────────────────────────────
ax3 = axes[2]
ax3.fill_between(dd_raw.index, dd_raw, 0, alpha=0.35, color="#ff7f0e")
ax3.plot(dd_raw, lw=0.8, color="#ff7f0e")
worst_date_raw = dd_raw.idxmin()
worst_val_raw  = dd_raw.min()
ax3.annotate(f"{worst_val_raw:.1f}%\n{worst_date_raw.strftime('%b %Y')}",
             xy=(worst_date_raw, worst_val_raw),
             xytext=(worst_date_raw - pd.DateOffset(months=14), worst_val_raw + 5),
             fontsize=8, color="#ff7f0e",
             arrowprops=dict(arrowstyle="->", color="#ff7f0e", lw=0.8))
ax3.set_ylabel("Raw 12-1 DD (%)")
ax3.set_xlabel("Date")
ax3.grid(alpha=0.3)
add_events(ax3, ypos_frac=0.12)

plt.tight_layout()
plt.savefig("layer1_backtest.png", dpi=150)
print("\nSaved → layer1_backtest.png")
