"""
backtest_sector_oos.py  --  Strategy v4 OUT-OF-SAMPLE reveal.

DO NOT run this until you have finished iterating on backtest_sector.py.
This file is identical to backtest_sector.py except DEV_MODE = False,
which reveals the locked 2019-2026 out-of-sample period.

Run once, record the numbers, do not tune further after seeing them.
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

CACHE = os.path.join(HERE, "data", "sector_prices.parquet")

# -- Universe: iShares US sector ETFs ------------------------------------------
SECTORS = {
    "IYW":  "Technology",
    "IYF":  "Financials",
    "IYH":  "Healthcare",
    "IYE":  "Energy",
    "IYC":  "Cons. Disc.",
    "IYZ":  "Comm. Svcs",
    "IYK":  "Cons. Staples",
    "IDU":  "Utilities",
    "IYM":  "Materials",
    "IYJ":  "Industrials",
    "IYR":  "Real Estate",
}
UNIVERSE    = list(SECTORS.keys())
BENCHMARKS  = ["SPY", "AGG", "QQQ"]
ALL_TICKERS = list(dict.fromkeys(UNIVERSE + BENCHMARKS))

IS_START,  IS_END  = "2001-01-01", "2018-12-31"
OOS_START, OOS_END = "2019-01-01", "2026-12-31"
ALL_START, ALL_END = "2001-01-01", "2026-12-31"
PRICE_START = "1999-06-01"

COST_BPS    = 10
TOP_K       = 4     # sectors entered each month
BUFFER_EXIT = 6     # rank buffer: an incumbent is held until it drops out of the top-6
REGIME_MA   = 231   # ~11-month SPY trend filter (slower than 200d -> fewer whipsaws)
DEV_MODE = False   # OOS revealed


# -- Data ----------------------------------------------------------------------
def load_prices():
    if os.path.exists(CACHE):
        print("[data] loading cached prices ...")
        df = pd.read_parquet(CACHE)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df
    print(f"[data] downloading {len(ALL_TICKERS)} tickers ...")
    raw = yf.download(ALL_TICKERS, start=PRICE_START, auto_adjust=True, progress=True)
    close = (raw.xs("Close", axis=1, level=0)
             if isinstance(raw.columns, pd.MultiIndex) else raw["Close"])
    close.index = pd.to_datetime(close.index).tz_localize(None)
    close.to_parquet(CACHE)
    return close

print("[data] loading prices ...")
close_daily   = load_prices()
monthly_close = close_daily.resample("ME").last()
monthly_all   = monthly_close.pct_change(fill_method=None)

univ_cols = [t for t in UNIVERSE  if t in monthly_all.columns]
monthly   = monthly_all[univ_cols]
bm_cols   = {t: monthly_all[t] for t in BENCHMARKS if t in monthly_all.columns}
print(f"[data] {len(univ_cols)} sectors | "
      f"{monthly.index.min().date()} - {monthly.index.max().date()}")


# -- Signals -------------------------------------------------------------------
def mom_signal(rets, skip=1, window=12):
    return (1 + rets.shift(skip)).rolling(window).apply(np.prod, raw=True) - 1

def cs_z(panel):
    return panel.sub(panel.mean(axis=1), axis=0).div(
        panel.std(axis=1).replace(0, np.nan), axis=0)

scores_12_1 = mom_signal(monthly, 1, 12)
scores_6_1  = mom_signal(monthly, 1, 6)
scores_3_1  = mom_signal(monthly, 1, 3)
scores_comp = (cs_z(scores_3_1) + cs_z(scores_6_1) + cs_z(scores_12_1)) / 3


# -- Regime filter -------------------------------------------------------------
spy_daily = close_daily["SPY"].dropna()
regime    = (spy_daily > spy_daily.rolling(REGIME_MA).mean()).resample("ME").last()
regime    = regime.reindex(monthly.index).fillna(True).map({True: 1.0, False: 0.0})
agg_ret   = bm_cols.get("AGG", pd.Series(dtype=float))
print(f"[regime] above {REGIME_MA}d MA: {regime.mean():.0%} | "
      f"gate OFF: {int((regime == 0).sum())} months")


# -- Uniqueness weighting (game-theory layer) ----------------------------------
def uniqueness_weights(held, monthly_rets, t, corr_window=12):
    """
    Nash-equilibrium diversification weights.
    Each sector weighted by 1 - avg_corr_with_co_held_sectors, normalised to sum=1.
    """
    if len(held) == 1:
        return pd.Series(1.0, index=held)
    hist = monthly_rets.loc[:t].iloc[-(corr_window + 1):][held].dropna(axis=1, how="any")
    if hist.shape[1] < 2 or hist.shape[0] < 3:
        return pd.Series(1.0 / len(held), index=held)
    avail = hist.columns.tolist()
    C = hist.corr()
    uniq = pd.Series({s: max(1.0 - C.loc[s, [x for x in avail if x != s]].mean(), 1e-6)
                      for s in avail})
    for s in held:
        if s not in uniq:
            uniq[s] = uniq.mean() if len(uniq) else 1.0
    total = uniq[held].sum()
    return uniq[held] / total if total > 0 else pd.Series(1.0 / len(held), index=held)


# -- Book builder --------------------------------------------------------------
def build_book(scores, fwd_rets, regime_s, monthly_rets, agg_r, cost_bps=COST_BPS):
    reg    = regime_s.reindex(scores.index).fillna(1.0)
    dates  = sorted(set(scores.index) & set(fwd_rets.index))
    prev_w   = pd.Series(dtype=float)
    cur_held = set()                       # incumbents, for rank buffering
    records  = []

    for i, t in enumerate(dates[:-1]):
        next_t = dates[i + 1]

        if reg.loc[t] == 0.0:
            w     = pd.Series({"AGG": 1.0})
            all_n = w.index.union(prev_w.index)
            turn  = (w.reindex(all_n, fill_value=0) - prev_w.reindex(all_n, fill_value=0)).abs().sum()
            gross = float(agg_r.get(next_t, 0.0))
            net   = gross - turn * cost_bps / 10_000
            records.append({"date": t, "gross": gross, "net": net,
                            "turnover": turn, "n_held": 0, "exposure": 0.0})
            prev_w, cur_held = w, set()    # rotated fully to bonds -- no equity incumbents
            continue

        row = scores.loc[t].dropna()
        if len(row) < TOP_K:
            continue
        ranked = row.rank(ascending=False)             # 1 = strongest
        entry  = set(ranked[ranked <= TOP_K].index)    # this month's top-K
        hold   = set(ranked[ranked <= BUFFER_EXIT].index)
        held   = list((cur_held & hold) | entry)       # keep incumbents still inside the buffer band
        w      = uniqueness_weights(held, monthly_rets, t)

        all_n  = w.index.union(prev_w.index)
        turn   = (w.reindex(all_n, fill_value=0) - prev_w.reindex(all_n, fill_value=0)).abs().sum()
        fwd    = fwd_rets.loc[next_t]
        common = w.index.intersection(fwd.dropna().index)
        gross  = (w[common] * fwd[common]).sum() if len(common) else 0.0
        net    = gross - turn * cost_bps / 10_000

        records.append({"date": t, "gross": gross, "net": net,
                        "turnover": turn, "n_held": len(held), "exposure": 1.0})
        prev_w, cur_held = w, set(held)

    return pd.DataFrame(records).set_index("date")


# -- Run -----------------------------------------------------------------------
print("[run] building v4 strategy ...")
v4 = build_book(scores_comp, monthly, regime, monthly, agg_ret)

spy_m = bm_cols.get("SPY", pd.Series(dtype=float))
agg_m = bm_cols.get("AGG", pd.Series(dtype=float))
bal   = (0.6 * spy_m + 0.4 * agg_m).dropna()


# -- Report --------------------------------------------------------------------
def row(label, r, indent=False):
    cells = []
    for _, a, b in [("IS", IS_START, IS_END), ("OOS", OOS_START, OOS_END), ("ALL", ALL_START, ALL_END)]:
        m  = sc.in_sample_mask(r.index, a, b)
        mt = sc.metrics(r, m)
        cells.append(
            f"{mt['sharpe']:>+6.2f}{mt['ann_ret']:>+7.1%}{mt['max_dd']:>+7.0%}{mt['tstat']:>+6.2f}")
    pad = "    " if indent else ""
    print(f"  {pad}{label:<54}" + " | ".join(cells))

sep = 144
print("\n" + "=" * sep)
print("STRATEGY v4 -- OOS REVEAL  (do not tune after running this)")
print("=" * sep)
hdr = "Sharpe  Ret    DD  tstat"
print(f"  {'':54}{'IN-SAMPLE 01-18':<27} | {'OOS 19-26':<27} | {'FULL 01-26':<27}")
print(f"  {'':54}{hdr:<27} | {hdr:<27} | {hdr:<27}")
print("  " + "-" * (sep - 2))
row("v4: sector rotation + regime->AGG + uniqueness", v4["net"])
print("  " + "-" * (sep - 2))
row("60/40 SPY/AGG", bal)
for bm, s in bm_cols.items():
    row(f"  {bm} buy-and-hold", s, indent=True)
print("=" * sep)

mask_is  = sc.in_sample_mask(v4["net"].index, IS_START, IS_END)
mask_oos = sc.in_sample_mask(v4["net"].index, OOS_START, OOS_END)
print(f"\n  IS  avg turnover : {v4['turnover'][mask_is].mean():.1%}")
print(f"  OOS avg turnover : {v4['turnover'][mask_oos].mean():.1%}")
print(f"  IS  avg exposure : {v4['exposure'][mask_is].mean():.2f}x")
print(f"  OOS avg exposure : {v4['exposure'][mask_oos].mean():.2f}x")

print(f"\nALPHA / BETA / IR  v4 full stack:")
for period_label, mask in [("IS", mask_is), ("OOS", mask_oos)]:
    print(f"  [{period_label}]")
    for bm_name, bm in bm_cols.items():
        r = sc.alpha_beta_ir(v4["net"], bm, mask=mask)
        print(f"    vs {bm_name:4s}: alpha={r['alpha_ann']:+.1%}  "
              f"beta={r['beta']:+.2f}  IR={r['ir']:+.2f}  hit={r['hit']:.0%}")


# -- Sector weight tracking ----------------------------------------------------
def sector_weights_ts(scores, monthly_rets, regime_s, top_k):
    reg = regime_s.reindex(scores.index).fillna(1.0)
    out = []
    cur_held = set()
    for t in scores.index:
        if reg.loc[t] == 0.0:
            out.append(pd.Series(0.0, index=univ_cols, name=t)); cur_held = set(); continue
        row_ = scores.loc[t].dropna()
        if len(row_) < top_k:
            out.append(pd.Series(0.0, index=univ_cols, name=t)); continue
        ranked = row_.rank(ascending=False)
        entry  = set(ranked[ranked <= top_k].index)
        hold   = set(ranked[ranked <= BUFFER_EXIT].index)
        held   = list((cur_held & hold) | entry)
        w = uniqueness_weights(held, monthly_rets, t)
        s = pd.Series(0.0, index=univ_cols)
        s.update(w)
        out.append(s.rename(t))
        cur_held = set(held)
    return pd.DataFrame(out)

print("[chart] computing sector weights ...")
sw = sector_weights_ts(scores_comp, monthly, regime, TOP_K)


# -- Chart ---------------------------------------------------------------------
fig, axes = plt.subplots(3, 1, figsize=(14, 14))
ax1, ax2, ax3 = axes

for label, r, c, lw in [
    ("v4  Sector Rotation + Uniqueness + Regime->AGG", v4["net"], "#1f77b4", 2.5),
    ("60/40 SPY/AGG", bal, "#ff7f0e", 1.6),
    ("SPY", bm_cols.get("SPY", pd.Series(dtype=float)), "#d62728", 1.4),
]:
    if isinstance(r, pd.Series) and r.empty: continue
    m  = sc.in_sample_mask(r.index, ALL_START, ALL_END)
    rm = r[m].fillna(0)
    if rm.empty: continue
    eq = (1 + rm).cumprod()
    s  = sc.metrics(r, m)["sharpe"]
    ax1.plot(eq, label=f"{label}  (Sharpe {s:+.2f})", color=c, lw=lw)

regime_m = regime.reindex(monthly.index).fillna(1.0)
mc = sc.in_sample_mask(regime_m.index, ALL_START, ALL_END)
for od in regime_m[mc][regime_m[mc] == 0].index:
    ax1.axvline(od, color="red", alpha=0.08, lw=1)
ax1.axvline(pd.Timestamp(OOS_START), color="black", lw=1.2, ls="--", alpha=0.8)
ax1.axhline(1, color="black", lw=0.6, ls=":")
ax1.set_title("Strategy v4 OOS Reveal: Sector Rotation + Uniqueness Weighting  (net 10bps)", fontsize=12)
ax1.set_ylabel("Growth of $1")
ax1.legend(loc="upper left", fontsize=9)
ax1.grid(alpha=0.3)
ax1.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"${x:.2f}"))

def rolling_sharpe(r, w=36):
    rm = r.dropna()
    return (rm.rolling(w).mean() * 12) / (rm.rolling(w).std() * np.sqrt(12))

for label, r, c in [
    ("v4", v4["net"], "#1f77b4"),
    ("SPY", bm_cols.get("SPY", pd.Series(dtype=float)), "#d62728"),
    ("60/40", bal, "#ff7f0e"),
]:
    if isinstance(r, pd.Series) and r.empty: continue
    m = sc.in_sample_mask(r.index, ALL_START, ALL_END)
    ax2.plot(rolling_sharpe(r[m]), label=label, color=c)
ax2.axhline(0, color="black", lw=0.8, ls="--")
ax2.axvline(pd.Timestamp(OOS_START), color="black", lw=1.2, ls="--", alpha=0.8)
ax2.set_title("Rolling 36-month Sharpe", fontsize=10)
ax2.set_ylabel("Sharpe"); ax2.legend(fontsize=9); ax2.grid(alpha=0.3)

sw_m = sw[sc.in_sample_mask(sw.index, ALL_START, ALL_END)]
colors_sec = plt.cm.tab20(np.linspace(0, 1, len(univ_cols)))
labels_sec = [SECTORS.get(t, t) for t in univ_cols]
ax3.stackplot(sw_m.index, sw_m[univ_cols].T.values,
              labels=labels_sec, colors=colors_sec, alpha=0.85)
ax3.axvline(pd.Timestamp(OOS_START), color="black", lw=1.2, ls="--", alpha=0.8)
ax3.set_title("Sector Allocation Over Time (uniqueness-weighted top-4)", fontsize=10)
ax3.set_ylabel("Portfolio Weight")
ax3.legend(loc="upper left", fontsize=7, ncol=4)
ax3.grid(alpha=0.2)

plt.tight_layout()
out = os.path.join(HERE, "backtest_sector_oos.png")
plt.savefig(out, dpi=150)
print(f"\nSaved -> {out}")
