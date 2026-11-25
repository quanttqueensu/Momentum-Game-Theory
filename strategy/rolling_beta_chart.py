"""
rolling_beta_chart.py  --  rolling realized beta of the book vs SPY, full run.

Realized beta = slope of the book's monthly returns (build_strategy, the same
series backtest.py uses) on SPY's, over a trailing WINDOW-month window. The
full-run beta is drawn as a reference line; SPY drawdowns deeper than
DD_SHADE are shaded so the drop in beta around sell-offs is visible.
Writes rolling_beta.png next to this file.
"""
import os
import warnings
import numpy as np
import pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import strategy_lib as S

warnings.filterwarnings("ignore")
WINDOW = 36          # months in each rolling regression
DD_SHADE = 0.15      # shade SPY drawdowns deeper than this
HERE = os.path.dirname(os.path.abspath(__file__))

# ---- deck look (same as beta_chart.py) -------------------------------------
INK, BODY, BLUE, ORANGE, PAPER, GRID = "#14213D", "#4A5568", "#2457C5", "#C8601C", "#F7F6F2", "#D5D2C8"
SHADE = "#8A94A6"
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Inter", "Helvetica Neue", "Arial", "DejaVu Sans"],
    "axes.edgecolor": GRID, "axes.labelcolor": BODY,
    "xtick.color": BODY, "ytick.color": BODY,
})

# ---- realized beta ---------------------------------------------------------
DI = S.get_data()
r, _ = S.build_strategy(DI=DI)
spy = DI["monthly"]["SPY"]
df = pd.concat([r.rename("r"), spy.reindex(r.index).rename("b")], axis=1).dropna()
# drop the month still in progress (its "return" is only a few days long)
df = df[df.index <= DI["close"].index.max()]


def slope(x):
    return np.polyfit(x["b"], x["r"], 1)[0]


full = slope(df)
roll = pd.Series({df.index[i]: slope(df.iloc[i - WINDOW + 1:i + 1])
                  for i in range(WINDOW - 1, len(df))})

# SPY drawdown episodes (monthly closes)
px = (1 + df["b"]).cumprod()
dd = px / px.cummax() - 1
episodes, start = [], None
for t, v in dd.items():
    if v < 0 and start is None:
        start = t
    if v >= 0 and start is not None:
        if dd.loc[start:t].min() <= -DD_SHADE:
            episodes.append((start, t))
        start = None
if start is not None and dd.loc[start:].min() <= -DD_SHADE:
    episodes.append((start, dd.index[-1]))

print(f"full run {df.index[0]:%Y-%m}..{df.index[-1]:%Y-%m}: realized beta {full:.2f}")
print(f"rolling {WINDOW}m -> now {roll.iloc[-1]:.2f} | min {roll.min():.2f} "
      f"({roll.idxmin():%Y-%m}) | max {roll.max():.2f} ({roll.idxmax():%Y-%m})")
print("shaded SPY drawdowns:", ", ".join(f"{a:%Y-%m}..{b:%Y-%m}" for a, b in episodes))

# ---- chart -----------------------------------------------------------------
fig, ax = plt.subplots(figsize=(11.2, 6.0), dpi=220)
fig.set_facecolor(PAPER); ax.set_facecolor(PAPER)

for a, b in episodes:
    ax.axvspan(a, b, color=SHADE, alpha=0.16, lw=0)
ax.text(0.01, 0.98, f"Shaded: SPY down more than {DD_SHADE:.0%} from its peak",
        color=BODY, fontsize=12, va="top", ha="left", transform=ax.transAxes)

# reference lines, labelled in the empty margin right of the data
ax.hlines(1.0, roll.index[0], roll.index[-1], color=BODY, ls=(0, (2, 3)), lw=1.6)
ax.annotate("SPY = 1.0", (roll.index[-1], 1.0), xytext=(12, 0), textcoords="offset points",
            va="center", color=BODY, fontsize=13)
ax.hlines(full, roll.index[0], roll.index[-1], color=ORANGE, ls=(0, (6, 4)), lw=2.2)
ax.annotate(f"Full-run\naverage {full:.2f}", (roll.index[-1], full), xytext=(12, 0),
            textcoords="offset points", va="center", color=ORANGE, fontsize=15,
            fontweight="bold")

ax.plot(roll.index, roll.values, color=BLUE, lw=3)
ax.scatter(roll.index[-1], roll.iloc[-1], s=110, color=INK, zorder=5,
           edgecolor=PAPER, linewidth=2)
ax.annotate(f"Last 3 yrs\n{roll.iloc[-1]:.2f}", (roll.index[-1], roll.iloc[-1]),
            xytext=(12, 0), textcoords="offset points", va="center",
            fontsize=15, fontweight="bold", color=INK)

lo = min(0, np.floor(roll.min() * 4) / 4)
top = max(1.25, np.ceil((roll.max() + 0.05) * 4) / 4)
ax.set_ylim(lo, top)
ax.set_xlim(roll.index[0], roll.index[-1] + pd.DateOffset(months=42))   # room for label
ax.set_yticks(np.arange(lo, top + 1e-9, 0.25))
ax.yaxis.set_major_formatter(lambda v, _: f"{v:.2f}")
ax.xaxis.set_major_locator(mdates.YearLocator(4))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax.tick_params(labelsize=14, length=0, pad=8)
ax.grid(axis="y", color=GRID, lw=1)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.set_ylabel(f"Realized beta vs SPY ({WINDOW}-month rolling)", fontsize=15, labelpad=10)

plt.tight_layout()
out = os.path.join(HERE, "rolling_beta.png")
plt.savefig(out, facecolor=PAPER)
print(f"saved {out}")
