# Strategy 6 — iShares Sector Rotation + Uniqueness Weighting

Rotates capital across the 11 iShares US sector ETFs using momentum signals, with two game-theory overlays that reduce crowding risk.

---

## Universe

11 iShares US sector ETFs covering the full S&P 500:
IYW (Tech), IYF (Financials), IYH (Healthcare), IYE (Energy), IYC (Cons. Disc.), IYZ (Comm. Svcs), IYK (Cons. Staples), IDU (Utilities), IYM (Materials), IYJ (Industrials), IYR (Real Estate).

---

## How It Works

### Momentum Signal
Each month, every sector is scored using composite momentum across three lookback windows:
- 3-month return (skip 1)
- 6-month return (skip 1)
- 12-month return (skip 1)

Each window is cross-sectionally z-scored before averaging, so no single lookback dominates. The top 4 sectors by composite score are held.

### Layer 1 — Uniqueness Weighting (Game Theory)
Classic sector rotation is a coordination game: when all managers pile into the same top sectors, positions become correlated and drawdowns compound together.

The fix: weight each held sector by how **uncorrelated** it is with the other held sectors:

```
uniqueness_i = 1 - mean correlation with co-held sectors
```

Weights are then normalised to sum to 1. This is the Nash equilibrium of a diversification game — capital flows toward sectors that contribute independent information. A trending sector that moves like everything else gets less weight; a trending sector that moves differently gets more.

### Layer 2 — Correlation Burst Gate (Game Theory)
When the average pairwise correlation across all 4 held sectors exceeds **0.80**, the whole book is scaled down to **60% exposure**. This is a crowding safeguard: if all held positions are moving in near-perfect lockstep, the portfolio is fragile and exposure is trimmed automatically.

### Regime Filter
SPY is compared to its 200-day moving average each month:
- **Above 200d MA** → normal operation, hold top-4 sectors
- **Below 200d MA** → risk-off; rotate into AGG (US bonds) instead of going to cash

Holding bonds during downturns earns carry rather than sitting idle.

---

## Variants (built for comparison)

| Variant | Description |
|---------|-------------|
| v1 | Top-4 composite, equal-weight, no regime filter |
| v2 | + SPY regime filter → cash when risk-off |
| v3 | + SPY regime filter → AGG (bonds, not cash) |
| v4 | + Uniqueness weighting — **full stack** |
| v5 | + Correlation burst gate (tested; hurts OOS by cutting exposure during sustained trends) |
| v6 | Equal-weight all 11 sectors (naive benchmark) |

**v4 is the recommended strategy.** v5 adds the corr gate but was found to hurt out-of-sample by reducing exposure during strong trending markets.

---

## Key Parameters

| Parameter | Value |
|-----------|-------|
| Sectors held | Top 4 |
| Lookback windows | 3-1, 6-1, 12-1 months |
| Correlation window | 12 months |
| Corr burst threshold | 0.80 |
| Burst gate exposure | 60% |
| Regime MA | 200-day SPY |
| Transaction cost | 10 bps per side |

---

## Academic Basis
- Sector momentum: Moskowitz & Grinblatt (1999)
- Trend / regime filter: Faber (2007)
- Nash equilibrium diversification weighting
