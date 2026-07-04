# Strategy 11 — Two-Engine Throttle Book

**65% Strategy 8 (style engine) + 35% Strategy 6 (sector engine), run as ONE
integrated monthly book, with a single book-level 15% volatility target ("the
throttle") replacing all sleeve-level vol targets.**

This is Strategy 10's aggressive successor, built for a mandate of roughly
"70% aggressive / 30% balanced": clearly beat SPY over the cycle, keep the
drawdown around a third of SPY's, stay tradeable by a university club in one
monthly session.

---

## How the strategy works

### The big idea

Strategy 10 answered "how do I never blow up" — 50% of capital sat in a
9-slot safety core (S7) that mostly earns bond-like returns. Strategy 11
answers the follow-up: **what if the safety came from a risk dial instead of
a capital allocation?** Drop the core entirely, hold only the two return
engines, and bolt a single throttle on the whole book:

```
                    STRATEGY 11  (100% of capital)
        ┌──────────────────────────────┬──────────────────────────────┐
        │      65%  STYLE ENGINE       │      35%  SECTOR ENGINE      │
        │      S8 "GEM-X"              │      S6 Sector Rotation      │
        │      best 1 of 5 equity      │      best 4 of 11 US         │
        │      styles, all-in          │      sectors, uniqueness wtd │
        └──────────────────────────────┴──────────────────────────────┘
                                   │
                     ONE BOOK-LEVEL 15% VOL THROTTLE
              if trailing vol of the combined holdings > 15%,
              trim risk pro-rata into hurdled IEF / T-bill cash
```

Both engines' **signal logic is frozen** — exactly the locked S8 and S6
configs, nothing re-tuned. Three things changed, all at book level:

2. **One throttle instead of three sleeve vol targets.** At each monthly
   rebalance, the combined target book's realised vol is estimated (current
   weights × trailing 63 days of *asset* returns — never the strategy's own
   history). If it exceeds 15% annualised, all risk positions are trimmed
   pro-rata and the freed capital joins that month's defensive pick (IEF if
   it beats the 12-month T-bill, else T-bill cash). Never levered.
3. **One integrated account, netted orders.** If both engines want the same
   ETF it's one position; sleeve trades that offset each other never hit the
   market. (This alone was worth ~+0.2%/yr vs running the sleeves separately.)

### A month in the life (~15 minutes, same as S10)

On the last trading day of the month, after the close:

1. Pull month-end prices for the ~20 ETFs + the FRED 3-month T-bill yield.
2. S8: composite momentum (3/6/12m, z-scored) over SPY/QQQ/IWM/EFA/EEM →
   top-1 with top-2 incumbency buffer → 12m T-bill hurdle, else IEF → cash.
3. S6: same composite over 11 iShares sectors → top-4 (top-6 buffer) →
   uniqueness weights; SPY < 231d MA → the sleeve goes to AGG.
4. Combine 65/35, estimate book vol on the trailing 63 days; if > 15%, trim
   risk pro-rata into the defensive pick.
5. Next trading day: place the difference orders (typically 5–8 ETFs held).

### Why it's built this way — and what was tried and REFUTED

The design came out of a ~260-config in-sample-only iteration
(2001–2018; every script in `iteration/`). The refuted ideas are as load-
bearing as the accepted ones:

- **Weekly exit valves are dead.** "Slow in, fast out" sounds great: check
  held positions weekly, cut anything below its 210d MA / 12m hurdle at the
  next close. Every variant — trend, hurdle, both, crash-only (below MA *and*
  >15% off the 52w high) — lost ~2–3%/yr **and worsened drawdown** (hundreds
  of whipsaw trips; weekly-horizon exits systematically sell the dip and
  rebuy higher at month-end). Tested five ways, refuted five ways.
- **Concentrated cross-asset momentum (top-3/4 of 9 assets) adds drawdown,
  not return.** The 9-slot design (S7) is the only good cross-asset shape.
- **Wider engine universes are worse.** Adding MDY/IWF/IWD or going
  top-1-of-everything degrades the locked S8; its 5-style menu is the sweet
  spot (real dispersion, all survivors).
- **Defensive-sleeve upgrades (momentum-picked bonds, S6 risk-off to
  IEF/cash) are noise on IS** — kept frozen.
- **Book-level vol targeting is the one mechanism that adds Sharpe without
  giving up return** — and it isn't new alchemy, it's S7's own vol-target
  mechanic promoted to book level (mechanism reuse, not invention).
- **The ridge is flat.** Blend 55/45→75/25: Sharpe 0.97–0.99. Throttle
  0.12→0.18: return +9.6%→+10.8% against DD −12%→−17%, monotonic, no cliffs.
  65/35 and 15% are round numbers on that ridge, not an optimum. The throttle
  IS the club's risk dial: a more conservative committee sets 12%, a more
  aggressive one 17%, and the backtest moves smoothly with it.

---

## Results (net 10 bps, monthly)

| | Sharpe | Ann. ret | MaxDD | t-stat | worst month |
|---|:--:|:--:|:--:|:--:|:--:|
| **S11 IS** 01–18 | +0.98 | +10.5% | −13% | +4.13 | −8.2% |
| **S11 OOS** 19–26 | +0.78 | +9.3% | −17% | +2.22 | −7.0% |
| **S11 FULL** 01–26 | **+0.92** | **+10.1%** | **−17%** | **+4.65** | −8.2% |
| S10 full (ref) | +1.00 | +8.9% | −13% | +5.06 | −8.5% |
| SPY full | +0.59 | +9.0% | −51% | +3.27 | −16.5% |
| 60/40 full | +0.71 | +6.8% | −32% | +3.74 | |

**Beats SPY's full-cycle return (+10.1% vs +9.0%) at a third of its drawdown
(−17% vs −51%), alpha +5.1%/yr at beta 0.50.** Versus S10 it trades ~0.08
Sharpe for +1.2%/yr of return — the intended 70%-aggressive move along the
frontier. Subperiods both work (IS halves: Sharpe +1.16 / +0.83); costs
tripled to 30bps still leaves Sharpe +0.86; annual turnover ~6.4× (sum of
both traded legs, ≈27%/month one-way).

## Honest disclosures

1. **Half the OOS is component arithmetic, not fresh evidence.** S8's and
   S6's individual OOS was revealed before this book existed (same caveat as
   S10). The throttle layer and the 65/35 blend, however, were chosen on IS
   only — their OOS behaviour here is genuinely fresh. Discount accordingly.
2. **It lags SPY in bull years — loudly pre-registered.** OOS it lost to SPY
   in 7 of 8 calendar years, winning the period on 2022 alone (−11.5% vs
   −18.2%). Hit rate vs SPY is ~42–45% of months; OOS IR −0.72. If the club
   will fire the strategy after a year of trailing a mega-cap bull, do not
   run it. It wins cycles, not years.
3. **Daily drawdown is deeper than the monthly table**: −17.3% IS, −22.8%
   OOS (March 2020) on a daily NAV basis. That is the number to pre-register
   with the club — a fifth of the book gone at the worst tick — and it sits
   at the edge of the "~70% aggressive" tolerance it was designed for.
4. **IS→OOS Sharpe decay 0.98 → 0.78** — real, moderate, and in line with
   what the momentum-decay literature would predict; not evidence of a
   broken edge, but not to be waved away either.
5. ~260 configurations were examined in-sample during the iteration. The
   defence against selection bias is the flat ridge (every neighbour works),
   mechanism reuse (nothing invented, only re-arranged), frozen components,
   and the single-shot OOS protocol — not innocence.

## Live operation (paper trading)

One account, one monthly rebalance on the last trading day (execute next
open/close):

| Piece | Capital | Positions |
|-------|:--:|-----------|
| S8 GEM-X | 65% × throttle | 1 style ETF (or IEF/cash) |
| S6 sectors | 35% × throttle | 4 sector ETFs (or AGG) |
| Throttle overflow | remainder | IEF or T-bill cash |

Typically 5–8 ETF positions, ~6–10 orders/month on Alpaca paper. Signals are
computable from yfinance closes + the FRED 3-month T-bill in a spreadsheet or
one Python script; the throttle needs only the last 63 days of daily closes
for the held ETFs.

## Files

- `throttle_lib.py` — locked config, weight paths (frozen sleeve logic),
  daily accounting simulator with the book throttle.
- `backtest_throttle.py` — in-sample backtest + verification battery
  (subperiods, sensitivity ridge, cost stress, daily-NAV drawdown).
- `backtest_throttle_oos.py` — the one-shot OOS reveal (run once 2026-07-02).
- `iteration/` — full provenance: the ~260-config IS iteration, including
  every refuted idea (`iterate3.py`/`iterate4.py` are the valve refutations).
- Components: `strategy8_equity_dm/`, `strategy6_sector/` — frozen.
