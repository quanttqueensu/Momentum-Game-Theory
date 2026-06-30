# Strategy 6 — iShares Sector Rotation + Uniqueness Weighting

Rotates capital across the 11 iShares US sector ETFs using momentum, with a
game-theory weighting overlay and a trend-based regime filter. Long-only,
monthly rebalance.

---

## Universe

11 iShares US sector ETFs covering the full S&P 500:
IYW (Tech), IYF (Financials), IYH (Healthcare), IYE (Energy), IYC (Cons. Disc.),
IYZ (Comm. Svcs), IYK (Cons. Staples), IDU (Utilities), IYM (Materials),
IYJ (Industrials), IYR (Real Estate).

---

## How It Works

Each month the book is rebuilt from scratch in four steps: score → select →
weight → regime. Signals use only data available at month-end (no look-ahead),
and the resulting book is held for the following month.

### Momentum Signal
Every sector is scored using composite momentum across three lookback windows:
- 3-month return (skip the most recent month)
- 6-month return (skip the most recent month)
- 12-month return (skip the most recent month)

Each window is cross-sectionally z-scored before averaging, so no single
lookback dominates. Sectors are ranked by this composite score.

### Layer 1 — Rank Buffer (membership hysteresis)
A sector **enters** the book when it ranks in the **top 4**, and is **held until
it drops out of the top 6**. Without this, a sector hovering around 4th/5th place
gets bought and sold on noise every month. The buffer only churns membership when
a holding genuinely falls out of contention, which cuts turnover (and the
trading costs / taxes that come with it) without changing what the strategy is
trying to own.

### Layer 2 — Uniqueness Weighting (Game Theory)
Classic sector rotation is a coordination game: when everyone piles into the same
top sectors, positions become correlated and drawdowns compound together.

The fix: weight each held sector by how **uncorrelated** it is with the other
held sectors, over a trailing 12-month window:

```
uniqueness_i = 1 - mean correlation with co-held sectors
```

Weights are then normalised to sum to 1. This is the Nash equilibrium of a
diversification game — capital flows toward sectors carrying independent
information. A trending sector that moves like everything else gets less weight;
a trending sector that moves differently gets more.

### Layer 3 — Regime Filter
SPY is compared to its **~11-month (231-day) moving average** each month:
- **Above the MA** → normal operation, hold the sector book
- **Below the MA** → risk-off; rotate the entire book into AGG (US bonds)

Holding bonds during downturns earns carry rather than sitting idle. The
~11-month trend is deliberately slower than the common 200-day filter so the
strategy flips in and out of bonds on genuine trend breaks rather than on
short-term noise.

---

## Monthly Rebalancing — how the weights move

The book is **recomputed every month**, so even a sector you keep does not hold a
fixed weight:

1. **Membership** is decided by the rank buffer (Layer 1). A kept sector stays in
   only while it remains inside the top 6.
2. **Weights** are then recalculated from scratch by the uniqueness rule (Layer 2)
   using the *current* held set and the *latest* trailing correlations.

So a sector you carry from one month to the next will still have its weight
nudged each month — because the set of co-held sectors and their correlations
shift over time. The buffer adds inertia to *which* ETFs are held; it does **not**
freeze *how much* of each is held. Each month's small re-weighting of kept names,
plus any entries/exits, is what the turnover figure measures.

---

## Key Parameters

| Parameter | Value |
|-----------|-------|
| Sectors entered | Top 4 by composite score |
| Rank buffer exit | Top 6 |
| Lookback windows | 3-1, 6-1, 12-1 months |
| Correlation window | 12 months |
| Regime MA | 231-day SPY (~11 months) |
| Risk-off asset | AGG (US bonds) |
| Rebalance | Monthly |
| Transaction cost | 10 bps per side |

---

## Files
- `backtest_sector.py` — in-sample backtest (`DEV_MODE = True`); iterate here.
- `backtest_sector_oos.py` — out-of-sample reveal (`DEV_MODE = False`); run once.

---

## Academic Basis
- Sector momentum: Moskowitz & Grinblatt (1999)
- Trend / regime filter: Faber (2007)
- Nash equilibrium diversification weighting

> A correlation-burst exposure gate was also tested (scaling the book down when
> all held sectors move in lockstep) but was **not adopted** — it cut exposure
> during sustained trends and hurt out-of-sample.
