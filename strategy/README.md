# The Two-Engine Book — the club strategy, explained from scratch

A monthly ETF rotation strategy: **65% of capital picks the single
strongest equity market, 35% picks four US sectors by a game-theoretic
rule — strongest momentum, taxed for crowding — and both halves
automatically step aside into bonds or cash when their holdings stop
trending.** One rebalance a month, 5–8 liquid ETFs, ~15 minutes of work.

Over 2001→today (net of costs): **+12.6%/yr vs SPY's +9.0%, with a −19%
worst drawdown vs SPY's −51%.**

---

## Part 1 — The idea (why this should work at all)

Two well-documented market facts power everything:

**1. Momentum.** Assets that have done well over the past 3–12 months tend
to keep doing well over the next month. This is one of the oldest and most
replicated findings in finance. It works best *across* broad asset classes
and sectors — which is why this strategy rotates whole markets and sectors,
never individual stocks (where the effect has famously stopped working for
large caps).

**2. Crashes are slow enough to step aside from.** Bear markets like
2000–02 and 2008 didn't happen in a day; they ground down for months. A slow
trend signal (like "is the index below its ~11-month average?") exits early
enough to skip most of the damage. The price: the same signal re-enters
late, so you give back some of the recovery. Every rule in this strategy is
a negotiation between those two facts.

Everything is **monthly**. Faster weekly "quick exit" rules backtest
~2–3%/yr worse *and* with deeper drawdowns — they sell dips and buy back
higher. Slow is a feature.

## Part 2 — The machine

```
                      THE BOOK (100% of capital)
   ┌────────────────────────────────┬─────────────────────────────────┐
   │       65%  STYLE ENGINE        │       35%  SECTOR ENGINE        │
   │  best 1 of SPY QQQ IWM EFA EEM │  best 4 of 11 iShares sectors   │
   │  by 3/6/12m composite momentum │  by momentum MINUS crowding tax │
   │  held while 12m OR 6m return   │  bear filter: SPY < 231d MA ->  │
   │  beats T-bills, else bonds/cash│  bonds/cash; back at 126d MA    │
   └────────────────────────────────┴─────────────────────────────────┘
              ONE CRASH-ONLY 12% VOLATILITY THROTTLE
   (only while SPY < 126d MA: if the book runs hot, trim to bonds/cash)
```

### Engine 1 — the style engine (65% of capital)

Menu: five broad equity ETFs — **SPY** (US large), **QQQ** (Nasdaq-100),
**IWM** (US small), **EFA** (developed international), **EEM** (emerging).

Each month-end:

1. **Score** each on momentum: its 3-month, 6-month and 12-month returns
   (each skipping the most recent month), standardized and averaged. Using
   three horizons instead of one makes the score much harder to game by one
   lucky quarter.
2. **Pick the top scorer** — all 65% goes into that one ETF. Concentration
   is deliberate: with broad indices (not single stocks), the best one tends
   to stay the best for months, and diversifying across all five just
   waters the signal down.
3. **Incumbency buffer:** if we already hold something, we keep it as long
   as it ranks top-2. This kills most of the flip-flopping (and its costs).
4. **The T-bill hurdle (the crash exit):** the pick is only allowed if its
   trailing 12-month OR 6-month total return beats what T-bills paid over
   the same window. If equities can't beat cash, we don't own them. The
   "OR 6-month" part is the *fast re-entry*: after a crash, the 6-month
   number turns positive long before the 12-month one, getting us back in
   near the bottom rather than a year later.
5. **When nothing qualifies:** the 65% goes to **IEF** (7–10yr Treasuries)
   — but only if IEF itself beats the T-bill hurdle; otherwise plain T-bill
   cash. That second check is what kept the strategy out of bonds in 2022,
   when bonds crashed alongside stocks.

### Engine 2 — the sector engine (35% of capital)

Menu: the 11 iShares US sector ETFs (tech IYW, financials IYF, healthcare
IYH, energy IYE, consumer disc. IYC, telecom IYZ, staples IYK, utilities
IDU, materials IYM, industrials IYJ, real estate IYR).

Each month-end:

1. **Score** all 11 with the same composite momentum.
2. **Tax the crowded ones (the game-theory layer):** the sectors then play
   a *congestion game* for the sleeve's capital. Allocating to a sector
   earns its momentum score but pays a penalty that grows with how much
   capital already sits in sectors correlated with it (past 126 trading
   days). The equilibrium of that game — found by a simple iterative
   dynamic — is the final ranking. Four momentum winners are often the same
   trade in four wrappers (tech, semis-heavy industrials...); the game
   substitutes a genuinely different bet for the fourth wrapper instead of
   stacking it.
3. **Hold the equilibrium top 4, equal-weighted** (an incumbent stays until
   it falls out of the equilibrium top 6 — same anti-churn logic as
   engine 1). Equal weight is deliberate: using the raw equilibrium
   *weights* concentrates the sleeve and backtests worse; the game's value
   is in choosing *which* sectors, not how much of each.
4. **The bear filter:** if SPY closes the month below its 231-day moving
   average, the whole sleeve retreats to the **same hurdled defensive as
   engine 1** — IEF if it beats the T-bill hurdle, otherwise cash — and
   comes back once SPY recrosses its **126-day** average, not the 231-day.
   Exit slow, re-enter fast: waiting for the slower 231-day recross costs
   ~1.7%/yr and doubles the worst-case lag behind SPY after a crash. Making
   the refuge hurdled (instead of unconditional bonds) matters in
   stock+bond bears like 2022, when the old bond refuge fell too.

### The throttle (the book-level safety valve, crash-only)

The throttle exists for crashes, so it only runs when the tape says a crash
is possible: **while SPY closes the month below its 126-day moving
average.** Above that line the book is never trimmed, no matter how hot it
runs. The reason is that volatility is high in two very different worlds —
during crashes, and during the violent first year of a recovery — and only
one of them is dangerous. An unconditional vol cap trims the recovery
exactly when the re-entry rules have just bought back in; that is how a
strategy ends up 15 points behind a rebound year.

When armed (SPY below the 126d line), we ask: *"had I held exactly this
portfolio for the last 21 trading days, what was its volatility?"* (A fast
one-month read: in a crash, last quarter's volatility is stale news.) If the
answer is above **12% annualized**, every risk position is trimmed
proportionally — `scale = 12% / measured vol` — and the freed capital joins
that month's defensive pick (IEF or cash). It never levers up, and it
resets fresh every month. The 12% cap is the club's **risk dial**
(backtests at 10% and 15% move return and drawdown smoothly, no cliffs),
and the 126-day line is the same one the sector engine re-enters on — not a
new parameter.

### Honesty rules baked into the backtest

Signals use only month-end data; trades execute at the *next* day's close;
every trade pays 10 bps; cash earns the real FRED T-bill rate; ETFs aren't
scored before they had 13 months of live history. No look-ahead anywhere.

## Part 3 — How much safer than SPY? (the actual numbers)

Same period (2001→today), same monthly data, strategy net of costs:

| | **This book** | **SPY** |
|---|:--:|:--:|
| Worst drawdown (monthly) | **−19.1%** | −50.8% |
| Worst drawdown (daily) | **−20.2%** | ~−55% |
| Worst 12 months | **−19.1%** | −43.4% |
| Worst single month | **−8.8%** | −16.5% |
| Longest underwater | **25 months** | 52 months |
| Volatility | 12.2% | 15.1% |
| Beta to SPY | 0.55 | 1.00 |

What that means in practice:

- **The catastrophes are cut to survivable size.** 2008: SPY peak-to-trough
  **−50.8%**, this book **−19.1%** (its worst episode; calendar 2008 closed
  at just −0.3%). Dot-com bear (2001–02): SPY −28.0%, book −7.3%. COVID
  (Feb–Mar 2020): SPY −19.4%, book −6.8%. 2022: SPY −18.2%, book −16.1%
  (the hardest environment — bonds fell too; the hurdled refuges kept the
  sleeves in cash instead of falling bonds).
- **The recovery math is the whole game.** A −51% loss needs +103% to get
  back to even — SPY spent 4½ years underwater after 2007. A −19% loss
  needs +24% — this book's longest underwater stretch was just over 2
  years. That asymmetry, compounded over 25 years, is *why* it ends up
  ahead of SPY (+12.6% vs +9.0%/yr) while carrying much less risk.
- **Roughly "40% of SPY's worst case"** is the honest one-liner: beta 0.55,
  worst-case numbers well under half of SPY's at every horizon.

The one safety caveat to say out loud: −20.2% is the worst *daily* reading
(March 2020) — deeper than the monthly table suggests. Pre-register that
number with the committee so nobody is surprised mid-crash.

## Part 4 — Track record (net 10 bps, monthly)

| | Sharpe | Ann. ret | MaxDD | worst month | t-stat |
|---|:--:|:--:|:--:|:--:|:--:|
| **Book, 2001–18 (in-sample)** | **+1.08** | **+12.8%** | −19% | −8.8% | +4.49 |
| Book, 2019→now | +0.93 | +12.0% | −16% | −7.7% | +2.60 |
| **Book, full 2001→now** | **+1.03** | **+12.6%** | **−19%** | −8.8% | +5.17 |
| SPY full | +0.59 | +9.0% | −51% | −16.5% | +3.27 |
| 60/40 full | +0.71 | +6.8% | −32% | −10.8% | +3.74 |

Alpha +6.9%/yr at beta 0.55. Turnover ~7.3×/yr. Chart: `backtest.png`.

## Part 5 — What living with it feels like (frame this honestly)

**Benchmark it against 60/40 — which it beats in nearly every window — and
against SPY only over full cycles (3+ years).** Year by year vs SPY, three
patterns repeat (13 bull years since 2001, SPY > +15%):

- **Normal bull year: double digits, a few points behind SPY** (median gap
  −4.2 across the 13 bull years). 2013: +27.6% vs +32.3%. 2024: +20.4% vs
  +24.9%. And it wins some outright — 2003 (+39.4% vs +28.2%), 2006, 2009
  (+29.1% vs +26.4%), 2020 (+30.4% vs +18.3%) — because riding the violent
  early months of a recovery at full size is exactly what the crash-only
  throttle is built to allow.
- **The year after a false alarm: 13–19 points behind.** When the prior
  year ended in a scare that reversed (December 2018, the 2022 bear, the
  2025 spring dip), the book starts the rebound year de-risked and pays for
  it: 2019: +11.9% vs +31.2%; 2023: +13.4% vs +26.2%; 2025: +4.1% vs
  +17.7%. These are the years the committee will want to fire it — that is
  the strategy working as designed.
- **Bear and sideways years: this is where it wins.** 2008: +36.5 points
  ahead of SPY. 2002: +14.3 ahead. 2022: +2.1 ahead. 2004/05/07: +5–16
  ahead.

It has never had a losing year while SPY was up big (worst bull-year
absolute return: +4.1% in 2025). But in 2019–26, a nearly unbroken mega-cap
bull, 42% of rolling 12-month windows lagged SPY by >5 points. **If the
club will judge it annually against SPY, do not run it. Get the 60/40
benchmark and a 3-year review horizon agreed in writing first.**

## Part 6 — Running it (the monthly ritual)

1. Last trading day of the month, after the close:
   `python3 signals.py --refresh`
2. It prints each engine's picks, the throttle state, and the final target
   weights (typically 5–8 ETFs).
3. Next trading day: place the difference orders. Done until next month.

`python3 backtest.py` reruns the full history and regenerates the chart.

## Part 7 — The fine print (read before pitching)

1. **2019+ is not clean out-of-sample.** The core two-engine book passed a
   one-shot out-of-sample test on 2019–26 with mild decay (Sharpe 0.98 →
   0.78), but the fast-re-entry rules, the crash-only throttle and the
   sector engine's congestion-game selection were each finalized on 2001–18
   data *after* that reveal (then checked once against 2019+, unchanged
   thereafter — the game selection's single check: 2019+ Sharpe 0.78 →
   0.86 vs the prior weighting; the hurdled sector refuge + 21d vol
   window's single check: 0.86 → 0.93). Treat recent-period numbers as
   expectation-setting, not proof. The real test is live paper trading.
2. Hundreds of configurations were examined during development. The
   defences against cherry-picking: every parameter sits on a flat ridge
   (neighbours all work), and every mechanism was validated separately
   before being combined.
3. Prices are fresh yfinance adjusted closes + the FRED 3-month T-bill,
   cached in `data/`. Early-history gaps (AGG pre-2003, IEF pre-2002, EFA
   pre-08/2001, EEM pre-2003) earn the T-bill rate — no backfill, no
   fictional returns.
4. Costs are modeled at 10 bps per traded leg; at a triple-cost stress
   (30 bps) the full-period Sharpe is still ~0.90.
5. This is an equity strategy (beta ≈ 0.55), not market-neutral. In a
   simultaneous stock+bond crash (2022) it loses double digits; it just
   loses less than the alternatives.

## Files

- `strategy_lib.py` — locked config, both engines, throttle, simulator,
  metrics. Self-contained; imports nothing outside this folder.
- `signals.py` — the monthly rebalance sheet (live operation).
- `backtest.py` / `backtest.png` — full backtest, club metrics, calendar
  table, chart.
- `data/` — price + T-bill caches (refreshed with `--refresh`).
