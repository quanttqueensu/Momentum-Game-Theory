# The Two-Engine Book — the club strategy, explained from scratch

A monthly ETF rotation strategy: **65% of capital picks the single
strongest equity market, 35% picks the four strongest US sectors, and both
halves automatically step aside into bonds or cash when their holdings stop
trending.** One rebalance a month, 5–8 liquid ETFs, ~15 minutes of work.

Over 2001→today (net of costs): **+10.6%/yr vs SPY's +9.0%, with a −16%
worst drawdown vs SPY's −51%.**

---

## Part 1 — The idea (why this should work at all)

Two well-documented market facts power everything:

**1. Momentum.** Assets that have done well over the past 3–12 months tend
to keep doing well over the next month. This is one of the oldest and most
replicated findings in finance. It works best *across* broad asset classes
and sectors (which is where we use it) — and it has famously stopped working
for picking individual large-cap stocks (which we tested and refuted in this
project, three separate times).

**2. Crashes are slow enough to step aside from.** Bear markets like
2000–02 and 2008 didn't happen in a day; they ground down for months. A slow
trend signal (like "is the index below its ~11-month average?") exits early
enough to skip most of the damage. The price: the same signal re-enters
late, so you give back some of the recovery. Every rule in this strategy is
a negotiation between those two facts.

Everything is **monthly**. We tested weekly "quick exit" rules five
different ways: every one of them lost ~2–3%/yr *and* made drawdowns worse
(they sell dips and buy back higher). Slow is a feature.

## Part 2 — The machine

```
                      THE BOOK (100% of capital)
   ┌────────────────────────────────┬─────────────────────────────────┐
   │       65%  STYLE ENGINE        │       35%  SECTOR ENGINE        │
   │  best 1 of SPY QQQ IWM EFA EEM │  best 4 of 11 iShares sectors   │
   │  by 3/6/12m composite momentum │  same score, anti-crowding wts  │
   │  held while 12m OR 6m return   │  bear filter: SPY < 231d MA ->  │
   │  beats T-bills, else bonds/cash│  all to AGG; back at 126d MA    │
   └────────────────────────────────┴─────────────────────────────────┘
                 ONE BOOK-LEVEL 15% VOLATILITY THROTTLE
      (if the combined book gets too hot, trim into bonds/cash)
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
2. **Hold the top 4** (an incumbent stays until it falls out of the top 6 —
   same anti-churn logic as engine 1).
3. **Anti-crowding weights:** among the four, more weight goes to the
   sector *least correlated* with the other three over the past year. Four
   momentum winners are often the same trade in four wrappers (tech,
   semis-heavy industrials...); this spreads the actual bets.
4. **The bear filter:** if SPY closes the month below its 231-day moving
   average, the whole sleeve retreats to **AGG** (aggregate bonds) — and
   comes back once SPY recrosses its **126-day** average, not the 231-day.
   Exit slow, re-enter fast: the asymmetric version tested +1.7%/yr better
   than the symmetric one, with half the worst-case lag behind SPY.

### The throttle (the book-level safety valve)

After combining the engines 65/35, we ask: *"had I held exactly this
portfolio for the last 63 trading days, what was its volatility?"* If the
answer is above **15% annualized**, every risk position is trimmed
proportionally — `scale = 15% / measured vol` — and the freed capital joins
that month's defensive pick (IEF or cash). It never levers up, and it
resets fresh every month. Volatility clusters, so "the recent past was
violent" is a decent proxy for "next month is dangerous." The 15% is also
the club's **risk dial**: backtests at 12% and 18% move return and drawdown
smoothly, no cliffs.

### Honesty rules baked into the backtest

Signals use only month-end data; trades execute at the *next* day's close;
every trade pays 10 bps; cash earns the real FRED T-bill rate; ETFs aren't
scored before they had 13 months of live history. No look-ahead anywhere.

## Part 3 — How much safer than SPY? (the actual numbers)

Same period (2001→today), same monthly data, strategy net of costs:

| | **This book** | **SPY** |
|---|:--:|:--:|
| Worst drawdown (monthly) | **−15.7%** | −50.8% |
| Worst drawdown (daily) | **−22.8%** | ~−55% |
| Worst 12 months | **−13.7%** | −43.4% |
| Worst single month | **−8.2%** | −16.5% |
| Longest underwater | **23 months** | 52 months |
| Volatility | 11.3% | 14.9% |
| Beta to SPY | 0.54 | 1.00 |

What that means in practice:

- **The catastrophes just don't happen.** 2008: SPY peak-to-trough
  **−50.8%**, this book **−7.0%**. Dot-com bear (2001–02): SPY −20.9%, book
  −7.1%. COVID (Feb–Mar 2020): SPY −19.4%, book −8.3%. 2022: SPY −18.2%,
  book −13.7% (its worst crash — bonds fell too, so there was nowhere good
  to hide; the cash hurdle limited the damage).
- **The recovery math is the whole game.** A −51% loss needs +103% to get
  back to even — SPY spent 4½ years underwater after 2007. A −16% loss
  needs +19% — this book's longest underwater stretch was under 2 years.
  That asymmetry, compounded over 25 years, is *why* the tortoise ends up
  ahead of SPY (+10.6% vs +9.0%/yr) despite trailing it in most bull years.
- **Roughly "half of SPY's risk"** is the honest one-liner: beta 0.54,
  worst-case numbers a third to a half of SPY's at every horizon.

The one safety caveat to say out loud: −22.8% is the worst *daily* reading
(March 2020) — deeper than the monthly table suggests. Pre-register that
number with the committee so nobody is surprised mid-crash.

## Part 4 — Track record (net 10 bps, monthly)

| | Sharpe | Ann. ret | MaxDD | worst month | t-stat |
|---|:--:|:--:|:--:|:--:|:--:|
| **Book, 2001–18 (in-sample)** | **+1.01** | **+11.0%** | −14% | −8.2% | +4.22 |
| Book, 2019→now | +0.79 | +9.6% | −14% | −7.4% | +2.26 |
| **Book, full 2001→now** | **+0.94** | **+10.6%** | **−16%** | −8.2% | +4.74 |
| SPY full | +0.59 | +9.0% | −51% | −16.5% | +3.27 |
| 60/40 full | +0.71 | +6.8% | −32% | −10.8% | +3.74 |

Alpha +5.1%/yr at beta 0.54. Turnover ~7.4×/yr. Chart: `backtest.png`.

## Part 5 — What living with it feels like (frame this honestly)

**Benchmark it against 60/40 — which it beats in nearly every window — and
against SPY only over full cycles (3+ years).** Year by year vs SPY, three
patterns repeat (13 bull years since 2001, SPY > +15%):

- **Normal bull year: double digits, ~5–7 points behind SPY** (median gap
  −6.1). 2013: +27.4% vs +32.3%. 2024: +20.8% vs +24.9%. Occasionally it
  wins one outright (2006).
- **The year after a crash: 10–19 points behind.** 2009: +12.1% vs +26.4%;
  2019: +12.1% vs +31.2%. The filters that dodged the crash re-enter early
  but not instantly. These are the years the committee will want to fire
  it — that is the strategy working as designed.
- **Bear and sideways years: this is where it wins.** 2008: +35.9 points
  ahead of SPY. 2002: +13.9 ahead. 2022: +4.4 ahead. 2004/05/07: +10–15
  ahead.

It never missed a bull market entirely (worst bull-year absolute return
≈ +6–12%), and it has never had a losing year while SPY was up big. But in
2019–26, a nearly unbroken mega-cap bull, over half of rolling 12-month
windows lagged SPY by >5 points. **If the club will judge it annually
against SPY, do not run it. Get the 60/40 benchmark and a 3-year review
horizon agreed in writing first.**

## Part 6 — Running it (the monthly ritual)

1. Last trading day of the month, after the close:
   `python3 signals.py --refresh`
2. It prints each engine's picks, the throttle state, and the final target
   weights (typically 5–8 ETFs).
3. Next trading day: place the difference orders. Done until next month.

`python3 backtest.py` reruns the full history and regenerates the chart.

## Part 7 — The fine print (read before pitching)

1. **2019+ is not clean out-of-sample for this exact configuration.** The
   original Strategy 11 had a one-shot out-of-sample test (2019–26) which
   it passed with mild decay (Sharpe 0.98 → 0.78); the fast-re-entry
   upgrades were validated on 2001–18 data only, *after* that reveal. Treat
   recent-period numbers as expectation-setting, not proof. The real test
   is live paper trading.
2. ~300 configurations were examined across this strategy's lineage. The
   defences against cherry-picking: every parameter sits on a flat ridge
   (neighbours all work), every mechanism was validated separately before
   being combined, and every refuted idea is documented (git history).
3. Prices are fresh yfinance adjusted closes + the FRED 3-month T-bill,
   cached in `data/`. Early-history gaps (AGG pre-2003, IEF pre-2002, EFA
   pre-08/2001, EEM pre-2003) earn the T-bill rate — no backfill, no
   fictional returns.
4. Costs are modeled at 10 bps per traded leg; at a triple-cost stress
   (30 bps) the full-period Sharpe is still ~0.9.
5. This is an equity strategy (beta ≈ 0.54), not market-neutral. In a
   simultaneous stock+bond crash (2022) it loses double digits; it just
   loses materially less than the alternatives.

## Files

- `strategy_lib.py` — locked config, both engines, throttle, simulator,
  metrics. Self-contained; imports nothing outside this folder.
- `signals.py` — the monthly rebalance sheet (live operation).
- `backtest.py` / `backtest.png` — full backtest, club metrics, calendar
  table, chart.
- `data/` — price + T-bill caches (refreshed with `--refresh`).
