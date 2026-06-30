"""
backtest_country.py — Cross-country ETF momentum with regime filter (Strategy v4).

Signal  : 12-1 price momentum on 28 iShares single-country ETFs.
Filter  : SPY 200-day MA regime gate — zero exposure when global market is in
          downtrend, prevents riding momentum into crash environments.
Book    : Long-only — equal-weight the country ETFs with positive 12-1 trend.
          When regime gate is OFF → 100% cash (0% invested).

Academic base:
  - Cross-country absolute momentum: Moskowitz, Ooi, Pedersen (2012)
    "Time Series Momentum" — country equity IR ~0.5–0.7.
  - Regime filter: Faber (2007) "A Quantitative Approach to Tactical
    Asset Allocation" — MA-based timing reduces max drawdown by 50%+.

Also shown: cross-sectional L/S (the academic factor — worse than abs mom here)
and equal-weight all countries.

Cost: 10bps roundtrip per ETF trade.
"""

import os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import yfinance as yf
import warnings
warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import strategy_core as sc

os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
CACHE = os.path.join(HERE, "data", "country_etf_prices.parquet")

# ── Universe: iShares single-country ETFs ────────────────────────────────────
UNIVERSE = [
    "EWA",   # Australia
    "EWO",   # Austria
    "EWK",   # Belgium
    "EWZ",   # Brazil
    "EWC",   # Canada
    "ECH",   # Chile
    "EIDO",  # Indonesia
    "EWQ",   # France
    "EWG",   # Germany
    "EWH",   # Hong Kong
    "INDA",  # India
    "EWI",   # Italy
    "EWJ",   # Japan
    "EWM",   # Malaysia
    "EWW",   # Mexico
    "EWN",   # Netherlands
    "ENZL",  # New Zealand
    "EPOL",  # Poland
    "EWS",   # Singapore
    "EZA",   # South Africa
    "EWY",   # South Korea
    "EWP",   # Spain
    "EWD",   # Sweden
    "EWL",   # Switzerland
    "EWT",   # Taiwan
    "THD",   # Thailand
    "TUR",   # Turkey
    "EWU",   # United Kingdom
]
BENCHMARKS  = ["SPY", "EFA", "EEM"]
ALL_TICKERS = UNIVERSE + BENCHMARKS

# ── Dates ─────────────────────────────────────────────────────────────────────
IS_START,  IS_END  = "2005-01-01", "2018-12-31"
OOS_START, OOS_END = "2019-01-01", "2026-12-31"
ALL_START, ALL_END = "2005-01-01", "2026-12-31"
PRICE_START = "2003-01-01"   # 2yr warmup for 13-month rolling window

LONG_K   = 5    # for cross-sectional L/S comparison
SHORT_K  = 5
COST_BPS = 10

DEV_MODE = False   # OOS revealed: no further tuning permitted after this

PERIODS = [("IS", IS_START, IS_END)] if DEV_MODE else [
    ("IS", IS_START, IS_END), ("OOS", OOS_START, OOS_END), ("ALL", ALL_START, ALL_END)]


# ── Download / cache ──────────────────────────────────────────────────────────
def load_prices() -> pd.DataFrame:
    if os.path.exists(CACHE):
        print("[data] loading cached prices …")
        df = pd.read_parquet(CACHE)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df
    print(f"[data] downloading {len(ALL_TICKERS)} ETF prices …")
    raw = yf.download(ALL_TICKERS, start=PRICE_START, auto_adjust=True, progress=True)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs("Close", axis=1, level=0)
    else:
        close = raw["Close"] if "Close" in raw.columns else raw
    close.index = pd.to_datetime(close.index).tz_localize(None)
    close.to_parquet(CACHE)
    print(f"[data] saved → {CACHE}")
    return close


print("[data] loading prices …")
close_daily = load_prices()

monthly_close = close_daily.resample("ME").last()
monthly_all   = monthly_close.pct_change(fill_method=None)

univ_cols = [t for t in UNIVERSE    if t in monthly_all.columns]
monthly   = monthly_all[univ_cols]
bm_cols   = {t: monthly_all[t] for t in BENCHMARKS if t in monthly_all.columns}

n_valid = monthly.notna().sum(axis=1)
print(f"[data] {len(univ_cols)} ETFs | "
      f"{monthly.index.min().date()} – {monthly.index.max().date()} | "
      f"valid/month: min={n_valid.min()}  med={n_valid.median():.0f}  max={n_valid.max()}")


# ── SPY 200-day regime filter ─────────────────────────────────────────────────
spy_daily = close_daily["SPY"].dropna()
spy_above_ma = (spy_daily > spy_daily.rolling(200).mean())
regime = spy_above_ma.resample("ME").last().reindex(monthly.index).fillna(True)
regime = regime.map({True: 1.0, False: 0.0})
print(f"[regime] SPY above 200-day MA: {regime.mean():.0%} of months | "
      f"gate OFF: {int((regime == 0).sum())} months total")


# ── 12-1 momentum signal ──────────────────────────────────────────────────────
raw_scores = (1 + monthly.shift(1)).rolling(12).apply(np.prod, raw=True) - 1


# ── PRIMARY STRATEGY: Absolute momentum + regime filter ──────────────────────
def build_abs_mom_regime(scores: pd.DataFrame, fwd_rets: pd.DataFrame,
                         regime_s: pd.Series, cost_bps: int):
    """Hold equal-weight ETFs with positive 12-1 trend when SPY in uptrend.
    Go to cash (0% invested) when SPY below 200-day MA."""
    dates   = sorted(set(scores.index) & set(fwd_rets.index))
    prev_w  = pd.Series(dtype=float)
    records = []

    for i, t in enumerate(dates[:-1]):
        gate = regime_s.get(t, 1.0)
        next_t = dates[i + 1]

        if gate == 0.0:
            # cash — pay zero turnover cost (we're in cash)
            turn = prev_w.abs().sum()  # cost of exiting to cash
            records.append({"date": t, "gross": 0.0,
                            "net": -turn * (cost_bps / 10_000),
                            "turnover": turn, "n_held": 0, "in_market": False})
            prev_w = pd.Series(dtype=float)
            continue

        row = scores.loc[t].dropna()
        pos = row[row > 0].index.tolist()

        if not pos:
            # all trends negative → also go to cash
            turn = prev_w.abs().sum()
            records.append({"date": t, "gross": 0.0,
                            "net": -turn * (cost_bps / 10_000),
                            "turnover": turn, "n_held": 0, "in_market": False})
            prev_w = pd.Series(dtype=float)
            continue

        w = pd.Series(1.0 / len(pos), index=pos)
        all_names = w.index.union(prev_w.index)
        turn = (w.reindex(all_names, fill_value=0) -
                prev_w.reindex(all_names, fill_value=0)).abs().sum()

        fwd    = fwd_rets.loc[next_t]
        common = w.index.intersection(fwd.dropna().index)
        gross  = (w[common] * fwd[common]).sum() if len(common) > 0 else 0.0
        net    = gross - turn * (cost_bps / 10_000)

        records.append({"date": t, "gross": gross, "net": net, "turnover": turn,
                        "n_held": len(pos), "in_market": True})
        prev_w = w

    df = pd.DataFrame(records).set_index("date")
    return df["gross"], df["net"], df["turnover"], df["n_held"]


# ── COMPARISON: Cross-sectional L/S ──────────────────────────────────────────
def build_ls_book(scores, fwd_rets, long_k, short_k, cost_bps):
    dates  = sorted(set(scores.index) & set(fwd_rets.index))
    prev_w = pd.Series(dtype=float)
    records = []
    for i, t in enumerate(dates[:-1]):
        row = scores.loc[t].dropna()
        if len(row) < long_k + short_k + 2: continue
        longs  = set(row.nlargest(long_k).index)
        shorts = set(row.nsmallest(short_k).index)
        longs -= shorts
        if not longs or not shorts: continue
        w = pd.concat([pd.Series(+0.5/len(longs),  index=list(longs)),
                       pd.Series(-0.5/len(shorts), index=list(shorts))])
        all_n = w.index.union(prev_w.index)
        turn  = (w.reindex(all_n, fill_value=0) -
                 prev_w.reindex(all_n, fill_value=0)).abs().sum()
        fwd    = fwd_rets.loc[dates[i+1]]
        common = w.index.intersection(fwd.dropna().index)
        if not len(common): continue
        gross = (w[common] * fwd[common]).sum()
        records.append({"date": t, "gross": gross,
                        "net": gross - turn*(cost_bps/10_000), "turnover": turn})
        prev_w = w
    df = pd.DataFrame(records).set_index("date")
    return df["gross"], df["net"], df["turnover"]


print("[build] constructing portfolios …")
gross_abs, net_abs, turn_abs, n_held = build_abs_mom_regime(
    raw_scores, monthly, regime, COST_BPS)
gross_ls, net_ls, turn_ls = build_ls_book(
    raw_scores, monthly, LONG_K, SHORT_K, COST_BPS)

ew_all = monthly.mean(axis=1)


# ── Report ────────────────────────────────────────────────────────────────────
def row(label, r, indent=False):
    cells = []
    for nm, a, b in PERIODS:
        m  = sc.in_sample_mask(r.index, a, b)
        mt = sc.metrics(r, m)
        cells.append(
            f"{mt['sharpe']:>+6.2f}{mt['ann_ret']:>+7.1%}{mt['max_dd']:>+6.0%}{mt['tstat']:>+6.2f}")
    pad = "    " if indent else ""
    print(f"  {pad}{label:<44}" + " │ ".join(cells))


sep = 48 + 27 * len(PERIODS)
print("\n" + "=" * sep)
print("STRATEGY v4 — CROSS-COUNTRY ETF MOMENTUM + REGIME FILTER  (net 10bps)")
if DEV_MODE:
    print("[DEV_MODE] in-sample 2005-2018 only.  OOS 2019-2026 locked.")
print("=" * sep)
TITLES = {"IS": "IN-SAMPLE 05-18", "OOS": "OOS 19-26", "ALL": "FULL 05-26"}
hdr    = "Sharpe  Ret   DD  tstat"
print(f"  {'':44}" + " │ ".join(f"{TITLES[nm]:<24}" for nm, _, _ in PERIODS))
print(f"  {'':44}" + " │ ".join(f"{hdr:<24}" for _ in PERIODS))
print("  " + "-" * (sep - 2))
row("★ Abs mom 12-1 + regime filter  NET 10bps",  net_abs)
row("  (gross)",                                   gross_abs, indent=True)
row("L/S CS top-5 bottom-5  NET 10bps",            net_ls)
print("  " + "-" * (sep - 2))
row("Equal-weight all 28 countries",               ew_all)
for bm, s in bm_cols.items():
    row(f"  {bm} buy-and-hold", s, indent=True)
print("=" * sep)

# turnover / exposure stats
mask_is = sc.in_sample_mask(net_abs.index, IS_START, IS_END)
print(f"\n  Avg monthly turnover  : {turn_abs[mask_is].mean():.1%}")
print(f"  Avg countries held    : {n_held[mask_is].mean():.1f} (when invested)")
pct_invested = (n_held[mask_is] > 0).mean()
print(f"  % months invested     : {pct_invested:.0%}  "
      f"({int((n_held[mask_is]>0).sum())}/{mask_is.sum()} IS months)")

# Alpha / IR
print(f"\nALPHA / BETA / IR  (in-sample 2005-2018):")
for bm_name, bm in bm_cols.items():
    r_abs = sc.alpha_beta_ir(net_abs, bm, mask=mask_is)
    print(f"  Abs+regime vs {bm_name:4s}:  alpha={r_abs['alpha_ann']:+.1%}  "
          f"beta={r_abs['beta']:+.2f}  IR={r_abs['ir']:+.2f}  "
          f"hit={r_abs['hit']:.0%}  n={r_abs['n']}")


# ── Chart ─────────────────────────────────────────────────────────────────────
C_START, C_END = (IS_START, IS_END) if DEV_MODE else (ALL_START, ALL_END)
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 10))

plot_series = [
    ("★ Abs mom 12-1 + regime  (net 10bps)", net_abs, "#1f77b4", 2.4),
    ("L/S CS top-5 (net 10bps)",             net_ls,  "#aec7e8", 1.4),
    ("Equal-weight all countries",           ew_all,  "#9467bd", 1.2),
    ("EFA (MSCI EAFE)",   bm_cols.get("EFA", pd.Series(dtype=float)), "#2ca02c", 1.6),
    ("EEM (MSCI EM)",     bm_cols.get("EEM", pd.Series(dtype=float)), "#8c564b", 1.2),
    ("SPY (S&P 500)",     bm_cols.get("SPY", pd.Series(dtype=float)), "#d62728", 1.4),
]

for label, r, c, lw in plot_series:
    if isinstance(r, pd.Series) and r.empty: continue
    m  = sc.in_sample_mask(r.index, C_START, C_END)
    rm = r[m].fillna(0)
    if rm.empty: continue
    eq = (1 + rm).cumprod()
    s  = sc.metrics(r, m)["sharpe"]
    ax1.plot(eq, label=f"{label}  (Sharpe {s:+.2f})", color=c, lw=lw)

# Shade regime-off periods
regime_m = regime.reindex(monthly.index).fillna(1.0)
m_chart  = sc.in_sample_mask(regime_m.index, C_START, C_END)
off_dates = regime_m[m_chart][regime_m[m_chart] == 0].index
if len(off_dates):
    ax1.axvspan(off_dates.min(), off_dates.max(), color="red", alpha=0.06,
                label="Regime gate OFF (SPY < 200MA)")

ax1.axhline(1, color="black", lw=0.6, ls=":")
suffix = "  [IN-SAMPLE ONLY]" if DEV_MODE else ""
ax1.set_title(f"Strategy v4: Country ETF Absolute Momentum + Regime Filter — net 10bps{suffix}",
              fontsize=12)
ax1.set_ylabel("Growth of $1")
ax1.legend(loc="upper left", fontsize=9)
ax1.grid(alpha=0.3)
ax1.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"${x:.2f}"))

# Rolling 36-month Sharpe
def rolling_sharpe(r, window=36):
    rm = r.dropna()
    return (rm.rolling(window).mean() * 12) / (rm.rolling(window).std() * np.sqrt(12))

for label, r, c in [
    ("Abs+regime", net_abs, "#1f77b4"),
    ("EFA",        bm_cols.get("EFA", pd.Series(dtype=float)), "#2ca02c"),
    ("SPY",        bm_cols.get("SPY", pd.Series(dtype=float)), "#d62728"),
]:
    if isinstance(r, pd.Series) and r.empty: continue
    m  = sc.in_sample_mask(r.index, C_START, C_END)
    rs = rolling_sharpe(r[m])
    ax2.plot(rs, label=label, color=c)

ax2.axhline(0, color="black", lw=0.8, ls="--")
ax2.set_title("Rolling 36-month Sharpe", fontsize=10)
ax2.set_ylabel("Sharpe")
ax2.legend(loc="upper left", fontsize=9)
ax2.grid(alpha=0.3)

if not DEV_MODE:
    for ax in [ax1, ax2]:
        ax.axvline(pd.Timestamp(OOS_START), color="black", lw=1.0, ls="--")
        ax.axvspan(pd.Timestamp(ALL_START), pd.Timestamp(OOS_START),
                   color="gray", alpha=0.07)

plt.tight_layout()
out = os.path.join(HERE, "backtest_country.png")
plt.savefig(out, dpi=150)
print(f"\nSaved → {out}")
