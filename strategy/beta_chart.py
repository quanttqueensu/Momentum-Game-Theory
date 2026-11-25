"""
beta_chart.py  --  beta vs SPY of each month's holdings (last YEARS years).

Beta of a month = sum over holdings of weight * trailing-252-day beta to SPY,
measured at that month's formation date. CASH counts as beta 0, so all-cash
months (e.g. Oct 2022) plot at zero. Writes beta_by_month.png next to this file.
"""
import os
import pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import strategy_lib as S

YEARS = 4
HERE = os.path.dirname(os.path.abspath(__file__))

# ---- deck look ------------------------------------------------------------
INK, BODY, BLUE, ORANGE, PAPER, GRID = "#14213D", "#4A5568", "#2457C5", "#C8601C", "#F7F6F2", "#D5D2C8"
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Inter", "Helvetica Neue", "Arial", "DejaVu Sans"],
    "axes.edgecolor": GRID, "axes.labelcolor": BODY,
    "xtick.color": BODY, "ytick.color": BODY,
})

# ---- beta of each month's holdings vs SPY ---------------------------------
DI = S.get_data()
ps = S.style_weight_path(DI)
p6 = S.sector_weight_path(DI, ps)
t_last = S.latest_formation(DI, ps, p6)
book = S.combine_paths([(ps, S.W_STYLE), (p6, S.W_SECTOR)])
rets = DI["rets"]

beta = {}
for t, w in book.items():
    if t > t_last:
        continue
    d = rets.loc[:t].tail(252)
    var = d["SPY"].var()
    b = 0.0
    for k, wk in w.items():                      # CASH has no prices -> beta 0
        if k in d.columns:
            bk = d[k].cov(d["SPY"]) / var
            if pd.notna(bk):
                b += wk * bk
    beta[t] = b
beta = pd.Series(beta).sort_index()
beta = beta[beta.index >= beta.index[-1] - pd.DateOffset(years=YEARS)]

print(f"last {YEARS}y -> this month {beta.iloc[-1]:.2f} | min {beta.min():.2f} | "
      f"max {beta.max():.2f} | median {beta.median():.2f} | "
      f"months above 0.8: {(beta > 0.8).mean():.0%}")

# ---- chart ----------------------------------------------------------------
fig, ax = plt.subplots(figsize=(11.2, 6.0), dpi=220)
fig.set_facecolor(PAPER); ax.set_facecolor(PAPER)

# extend the last step one month so the final value is visible
x = beta.index.append(pd.DatetimeIndex([beta.index[-1] + pd.offsets.MonthEnd(1)]))
y = list(beta.values) + [beta.iloc[-1]]

ax.fill_between(x, y, 0, step="post", color=BLUE, alpha=0.12, lw=0)
ax.step(x, y, where="post", color=BLUE, lw=3, solid_joinstyle="miter")
# stop the SPY line at the data so it does not run through the end label
ax.hlines(1.0, x[0], x[-1], color=ORANGE, ls=(0, (6, 4)), lw=2.2)
ax.axhline(0.0, color=INK, lw=1.2)

# labels on the chart instead of a legend
ax.text(x[0], 1.03, "SPY = 1.0", color=ORANGE, fontsize=15, fontweight="bold", va="bottom")
ax.scatter(beta.index[-1], beta.iloc[-1], s=110, color=INK, zorder=5,
           edgecolor=PAPER, linewidth=2)
ax.annotate(f"This month\n{beta.iloc[-1]:.2f}", (beta.index[-1], beta.iloc[-1]),
            xytext=(12, -10), textcoords="offset points", va="top",
            fontsize=15, fontweight="bold", color=INK)

# axes
top = max(1.3, beta.max() + 0.15)
ax.set_ylim(min(0, beta.min()) - 0.05, top)
ax.set_xlim(x[0], x[-1] + pd.DateOffset(months=5))   # room for the label
ax.set_yticks([v / 4 for v in range(int(top * 4) + 1)])
ax.yaxis.set_major_formatter(lambda v, _: f"{v:.2f}")
ax.xaxis.set_major_locator(mdates.YearLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax.tick_params(labelsize=14, length=0, pad=8)
ax.grid(axis="y", color=GRID, lw=1)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.set_ylabel("Beta vs SPY", fontsize=15, labelpad=10)

plt.tight_layout()
out = os.path.join(HERE, "beta_by_month.png")
plt.savefig(out, facecolor=PAPER)
print(f"saved {out}")
