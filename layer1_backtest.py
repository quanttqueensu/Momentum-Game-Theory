
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
raw_scores = monthly_ret_member.shift(1).rolling(SCORE_WINDOW).sum()

print(f"\nScore panel (residual): {res_scores.notna().sum().sum():,} valid observations")
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
def run_backtest(scores, label):
    """
    For each month t in scores, form the portfolio and measure the return
    over the following month (t → t+1).
    """
    dates  = sorted(set(scores.index) & set(monthly_ret.index))
    result = []

    for i, t in enumerate(dates[:-1]):
        t_next = dates[i + 1]
        w = build_weights(scores.loc[t])
        if w is None:
            continue

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
    return df["return"]


res_returns = run_backtest(res_scores, "Residual Momentum")
raw_returns = run_backtest(raw_scores, "Raw 12-1 Momentum")

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

print("\n" + "="*70)
print("LAYER 1 PERFORMANCE SUMMARY")
print("="*70)
m_res = compute_metrics(res_returns, "Residual Momentum")
m_raw = compute_metrics(raw_returns, "Raw 12-1 Momentum")

# ── 7. Equity curves ──────────────────────────────────────────────────────────
fig, axes = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={"height_ratios": [3, 1]})

ax1 = axes[0]
common_idx = res_returns.index.intersection(raw_returns.index)

eq_res = (1 + res_returns).cumprod()
eq_raw = (1 + raw_returns).cumprod()

ax1.plot(eq_res, label=f"Residual Momentum  (Sharpe {m_res['sharpe']:.2f})", lw=1.8, color="#1f77b4")
ax1.plot(eq_raw, label=f"Raw 12-1 Momentum  (Sharpe {m_raw['sharpe']:.2f})", lw=1.4, color="#ff7f0e", linestyle="--")
ax1.axhline(1, color="black", lw=0.6, linestyle=":")
ax1.set_title("Layer 1 Backtest — Residual vs Raw 12-1 Momentum (Dollar-Neutral L/S)", fontsize=13)
ax1.set_ylabel("Equity ($1 start)")
ax1.legend(loc="upper left", fontsize=10)
ax1.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"${x:.2f}"))
ax1.grid(alpha=0.3)

# Drawdown panel
dd_res = (eq_res / eq_res.cummax() - 1) * 100
dd_raw = (eq_raw / eq_raw.cummax() - 1) * 100
ax2 = axes[1]
ax2.fill_between(dd_res.index, dd_res, 0, alpha=0.35, color="#1f77b4", label="Residual")
ax2.fill_between(dd_raw.index, dd_raw, 0, alpha=0.25, color="#ff7f0e", label="Raw 12-1")
ax2.set_ylabel("Drawdown (%)")
ax2.set_xlabel("Date")
ax2.legend(loc="lower left", fontsize=9)
ax2.grid(alpha=0.3)

plt.tight_layout()
plt.savefig("layer1_backtest.png", dpi=150)
print("\nSaved → layer1_backtest.png")
