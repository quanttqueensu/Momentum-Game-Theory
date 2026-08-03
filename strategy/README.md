# Model Documentation — The Two-Engine Book

## Document Control

| Field | Value |
|---|---|
| Model name | The Two-Engine Book |
| Model type | Rule-based tactical asset allocation (ETF rotation) |
| Asset scope | Liquid, exchange-traded ETFs only (equity, Treasury, cash) |
| Intended use | Generate the club's monthly rebalance orders |
| Intended users | Club investment committee; club portfolio manager |
| Rebalance frequency | Monthly |
| Document date | 2026-08-03 |
| Model owner | Hugh Hayes (strategy lead) |
| Approval status | [fill in — pending committee review] |

(Approval status still needs filling in before this goes in front of the committee.)

---

## 1. Purpose and Scope

This document describes a rule-based ETF rotation model that generates the club's
monthly rebalance. It runs on two engines and one safety control, all specified
exactly in Section 4.

The rest of the document covers why the approach should work (Section 3), the
precise rules (Section 4), the data and execution assumptions behind the backtest
(Section 5), how it's actually performed (Section 6), where its limits are
(Sections 7–8), how to run it each month (Section 9), where the code lives
(Section 10), and what's still open before go-live (Section 11).

One thing worth being upfront about: this is a set of systematic rules, not a
guarantee. Section 7 covers the limits that should be disclosed before this gets
pitched to the committee.

## 2. Executive Summary

The book splits into two sleeves:

- **65% — style engine.** Picks the single strongest of five broad equity
  markets (US large-cap, Nasdaq, US small-cap, developed international,
  emerging markets) by momentum.
- **35% — sector engine.** Picks four of eleven US sector ETFs, using a rule
  that taxes crowded, overlapping bets so the sleeve doesn't end up holding
  four versions of the same trade.

Both sleeves step out of equities into bonds or cash once their holdings stop
trending, and a single volatility throttle trims the whole book on the way
down during an actual crash — not during ordinary swings.

From 2001 to today, net of trading costs, the book returned +12.6%/yr against
SPY's +9.0%/yr, with a worst drawdown of −19% against SPY's −51%. That's the
headline result, and so far it's held up in both the in-sample and
out-of-sample windows.

## 3. Why the Model Should Work

Two well-documented market facts underpin the rules.

**Momentum persists.** An asset that's done well over the past 3–12 months
tends to keep doing well over the next month, one of the oldest and most
replicated results in empirical finance. The effect is strongest across whole
asset classes and sectors and has weakened for individual large-cap stocks,
which is why this model rotates markets and sectors rather than picking single
names.

**Crashes are slow.** The 2000–02 and 2008 bear markets didn't happen in a
day — they ground down over many months. A slow trend filter, like checking
whether an index sits below its ~11-month average, can get you out of a
falling market early enough to avoid most of the damage.

The tradeoff is that a slow signal also gets you back in late, giving back
some of the recovery. Every rule in this model is a version of that tradeoff
in one form or another.

Signals are checked monthly rather than weekly, on purpose. Faster "quick
exit" rules were tested and came out 2–3%/yr worse with deeper drawdowns — the
faster read kept selling dips and re-buying at higher prices. Monthly is a
deliberate choice, not a shortcut.

## 4. Model Specification

This section is the exact rulebook. Each engine runs independently; the
throttle then applies to the combined book.

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

### 4.1 Style Engine (65% of capital)

**Universe:** SPY (US large-cap), QQQ (Nasdaq-100), IWM (US small-cap), EFA
(developed international), EEM (emerging markets).

At the close of each month:

1. **Score each ETF** on 3-, 6-, and 12-month total return (skipping the most
   recent month), standardize each, and average into one composite score.
   Blending three horizons makes the score harder to distort with one lucky
   quarter than a single window would.
2. **Take the top scorer.** All 65% goes into a single ETF. Broad indices,
   unlike single stocks, tend to stay in the lead for months at a time, so
   concentrating in the top pick is deliberate — spreading across all five
   would just dilute the signal.
3. **Apply the incumbency buffer.** An ETF already held stays held as long as
   it's still ranked in the top two. This removes most of the position flips
   (and their costs) that a strict "always hold #1" rule would generate.
4. **Check the T-bill hurdle.** Before buying the top pick, its trailing
   12-month OR 6-month return has to beat T-bills over the same window. If
   equities can't clear cash, the engine doesn't hold equities.

   The 6-month leg is the **fast re-entry rule**. After a crash, the 6-month
   return turns positive months before the 12-month number does, which lets
   the engine buy back in near the bottom instead of a year later.
5. **Fall back if nothing qualifies.** If no ETF clears the hurdle, move the
   65% into IEF (7–10yr Treasuries) — but only if IEF itself clears the same
   hurdle. If IEF fails too, sit in plain T-bill cash instead. That second
   check is what kept the engine out of bonds in 2022, when bond prices fell
   alongside stocks.

### 4.2 Sector Engine (35% of capital)

**Universe:** the eleven iShares Dow Jones US sector ETFs — IYW (technology),
IYF (financials), IYH (healthcare), IYE (energy), IYC (consumer
discretionary), IYZ (telecom), IYK (consumer staples), IDU (utilities), IYM
(materials), IYJ (industrials), IYR (real estate).

At the close of each month:

1. **Score all eleven** the same way as the style engine (Section 4.1, step
   1).
2. **Tax the crowded ones.** This is the model's game-theory layer: treat the
   eleven sectors as players competing for the sleeve's capital in a
   congestion game. Each sector earns its momentum score but pays a penalty
   that grows with how much capital is already sitting in sectors correlated
   with it, measured over the trailing 126 days. Solving for the equilibrium
   of this game — a short iterative calculation — produces the final
   ranking.

   Raw momentum alone tends to put four flavors of the same trade at the top
   (technology and a semiconductor-heavy industrials sector, for example).
   The congestion tax swaps one of those duplicates for a genuinely different
   bet.
3. **Hold the top four, equal-weighted**, with the same anti-churn buffer as
   the style engine — a held sector stays held until it falls out of the
   equilibrium top six. Equal weighting is deliberate: using the game's raw
   equilibrium weights concentrates the sleeve and tested worse. The game's
   job is deciding *which* sectors to hold, not how much capital to give each
   one.
4. **Apply the bear filter.** If SPY closes the month below its 231-day
   average, the whole sleeve moves to the defensive asset (the same
   IEF-then-cash hurdle as the style engine). It only comes back to sector
   picks once SPY closes back above its 126-day average — a faster line than
   the one used to exit.

   Exiting slow and re-entering fast costs about 1.7%/yr but roughly halves
   the sleeve's worst-case lag behind SPY after a crash. Using a hurdled
   refuge instead of unconditional bonds is what mattered in 2022, when
   stocks and bonds sold off together.

### 4.3 Book-Level Throttle

A safety control on the combined book, active only during a genuine crash. At
the close of each month:

1. **Check if it's armed.** The throttle only arms while SPY closes the month
   below its 126-day average — above that line, it does nothing no matter how
   much the book has gained. Volatility spikes in two situations: during a
   crash, and during the first violent year of a recovery. Only the first is
   dangerous, and an always-on throttle would cut exposure right after the
   re-entry rules had just bought back in — exactly how a model ends up
   trailing a rebound year.
2. **Measure volatility, if armed**, using the last 21 trading days — a fast,
   one-month read, since a volatility number from the prior quarter is stale
   mid-crash.
3. **Trim if it's above 12% annualized.** Scale every risk position down by
   `12% / measured volatility`, and move what's freed into that month's
   defensive pick. The throttle never adds leverage and resets fresh every
   month.

The 12% cap is the club's risk dial — backtests at 10% and 15% show smooth
changes in return and drawdown either way, with no sharp breaks. The 126-day
line is the same one the sector engine already uses for re-entry (Section
4.2, step 4), so the throttle isn't introducing a new parameter of its own.

## 5. Data and Execution Assumptions

The Section 6 backtest follows rules designed to keep the model from using
information it wouldn't have had in real time:

- Signals are computed on month-end data only.
- Trades execute at the next trading day's close, not the signal day's price.
- Every trade costs 10 basis points (0.10%).
- Cash returns use the actual FRED T-bill rate for each period.
- An ETF isn't scored until it has 13 months of live trading history.

Price data is adjusted daily closes; T-bill data comes from FRED. Both are
cached in `data/`.

A few ETFs have short histories, and before their first trade date they're
scored at the T-bill rate rather than backfilled or invented:

- AGG — before September 2003
- IEF — before 2002
- EFA — before August 2001
- EEM — before 2003

## 6. Backtest Results

How the model would have performed from 2001 to today, net of trading costs,
under the rules in Section 5.

### 6.1 Risk vs. SPY

| Metric | The Book | SPY |
|---|:--:|:--:|
| Worst drawdown (monthly) | **−19.1%** | −50.8% |
| Worst drawdown (daily) | **−20.2%** | ~−55% |
| Worst 12 months | **−19.1%** | −43.4% |
| Worst single month | **−8.8%** | −16.5% |
| Longest underwater period | **25 months** | 52 months |
| Volatility (annualized) | 12.2% | 15.1% |
| Beta to SPY | 0.55 | 1.00 |

The pattern across every crash in the sample is the same: a severe loss for
SPY becomes a survivable one for the book. SPY lost −50.8% peak-to-trough in
2008; the model's worst episode ever was −19.1%, and calendar-year 2008
actually closed at −0.3%. In the dot-com bear, SPY lost −28.0% against the
model's −7.3%. During COVID (Feb–Mar 2020), SPY lost −19.4% against −6.8%.
The one stretch that genuinely stressed the model was 2022, when bonds fell
alongside stocks — SPY lost −18.2% and the model lost −16.1%, saved mostly by
the hurdled refuge keeping the sleeves in cash instead of falling bonds.

Smaller losses also recover faster, and that compounds: a −51% loss needs
+103% just to get back to even, and SPY spent 4.5 years underwater after the
2007 peak. A −19% loss only needs +24%, and the model's longest underwater
stretch was a bit over two years. That asymmetry, compounded over 25 years,
is the whole reason the book ends up ahead of SPY on return (+12.6%/yr vs.
+9.0%/yr) while carrying meaningfully less risk — at a beta of 0.55, its
worst-case numbers run at roughly 40% of SPY's across the board.

One caveat worth stating plainly before this goes to the committee: −20.2% is
the worst *daily* reading (March 2020), deeper than the monthly table above
suggests. Better to flag that now than have it surface for the first time
during a live crash.

### 6.2 Return and Risk-Adjusted Performance

Split between the in-sample period used to build the rules (2001–2018) and
everything since (2019–today, genuinely held out during development):

| Period | Sharpe | Ann. return | MaxDD | Worst month | t-stat |
|---|:--:|:--:|:--:|:--:|:--:|
| Book, 2001–18 (in-sample) | **+1.08** | **+12.8%** | −19% | −8.8% | +4.49 |
| Book, 2019–today (out-of-sample) | +0.93 | +12.0% | −16% | −7.7% | +2.60 |
| **Book, full period 2001–today** | **+1.03** | **+12.6%** | **−19%** | −8.8% | +5.17 |
| SPY, full period | +0.59 | +9.0% | −51% | −16.5% | +3.27 |
| 60/40 portfolio, full period | +0.71 | +6.8% | −32% | −10.8% | +3.74 |

The out-of-sample numbers held up close to the in-sample ones — Sharpe eases
from 1.08 to 0.93, still comfortably ahead of SPY's 0.59 over the same full
period. Full-period alpha comes out to +6.9%/yr at a beta of 0.55, with
annual turnover around 7.3×. The full equity curve is in `backtest.png`.

## 7. Limitations and Known Risks

Things worth saying plainly here, not discovered for the first time in front of
the committee.

**Live track record is very early — Section 6 is a backtest.** The book placed
its first live paper-trading orders in early August 2026 (confirm exact date
against the IBKR trade log / TWS history before this goes to committee). There
has not been enough time for the numbers above to be independently confirmed
by real fills. Treat Section 6 as the model's design case until enough
paper-trading history accumulates to compare against it directly — keep
capturing `ib_test.py` output / TWS statements after each monthly rebalance so
that history builds into an auditable record.

**The 2019-today window is mostly, not perfectly, clean out-of-sample.** The
big structural choices — which ETFs, the two-engine split, momentum as the
signal, hurdle-based defensive logic — were locked before ever checking
post-2018 performance. A handful of smaller mechanisms (the fast re-entry
rule, the crash-only throttle, the sector engine's selection rule) were added
and tuned later, each checked against pre-2019 data first and then confirmed
once, not iterated, against 2019+. That's a real distinction from a strategy
finalized once and never touched again, and it's disclosed here rather than
glossed over.

**The book lags SPY in most bull years, sometimes badly.** Since 2019 it has
beaten SPY in only 1 of 6 calendar years SPY was up >15%, and its worst
trailing-12-month gap versus SPY over that period was −22.8% (calendar 2019,
where the book made +11.9% against SPY's +31.2%). Across the full 2001-today
history the median bull-year gap is −4.2%, worst −19.4% (2019), best +12.0%
(2020). This is structural, not a bug: anything that limits crash losses also
gives up some rally participation. A committee judging this strictly on
trailing 12 months against SPY alone will see it "fail" in some years even
when it's behaving exactly as designed — see Section 8.

**Daily drawdown runs deeper than the monthly numbers suggest.** The
monthly-close table in Section 6.1 shows a worst drawdown of −19.1%; measured
on daily NAV the worst point was −20.2% (March 2020). Anyone stress-testing
against the monthly return series alone will underestimate the worst
mark-to-market moment.

**Costs and fills are modeled, not yet observed.** The backtest assumes 10bps
one-way costs and next-close fills, which should be realistic for the ETFs
traded here (all large, liquid index products) but hasn't been confirmed by
live fills yet.

**Currency.** The paper account (and likely any eventual funded account) is
CAD-denominated while every ETF traded prices in USD. The execution bridge
converts account value to USD before sizing (`strategy/live/execute_rebalance.py`)
— one more live data dependency (a live USD/CAD rate) that the backtest itself
doesn't have to deal with.

**Narrow universe, no leverage.** Sixteen tickers total (5 style ETFs, 11
sector ETFs, 2 defensive). A shock that breaks correlations across all of them
at once (e.g. a disorderly Treasury-market move) has no specific defense here
beyond the T-bill hurdle already described in Section 4.

**Single decision-maker.** The model, the code, and the execution bridge were
all built and are currently operated by one person. There is no second
reviewer on the monthly signal or on live order placement yet.

## 8. Recommended Governance Before Go-Live

- **Pre-register the benchmark.** Evaluate against a 60/40 stock/bond blend as
  the primary comparison, not SPY alone — SPY is a 100%-equity, unhedged
  comparison, and this book is deliberately lower-beta (0.55).
- **Pre-register the evaluation horizon.** Judge on a rolling 3-year basis, not
  any single 12-month stretch. Since 2019, trailing-12-month windows lagged
  SPY by more than 5 points 42% of the time even though the model is beating
  its own design-stage expectations over the full period — a strict 1-year
  abandonment rule would pull this exact model in the middle of doing what it
  was built to do.
- **Second reviewer.** Before this moves off paper, have someone other than the
  strategy lead sanity-check the monthly `signals.py` output against the rules
  in Section 4 before live orders go out.
- **Formal sign-off.** The "Approval status" field in Document Control (top of
  this document) should be filled in by the committee, not left blank.

## 9. Operating Cadence

Monthly, near the close on the last trading day of the month:

1. `python3 strategy/signals.py --refresh` — prints the target book
   (informational only, no IBKR connection).
2. `python3 strategy/live/execute_rebalance.py --refresh` — dry run against the
   live paper account; prints the exact order ticket.
3. Read the order ticket. If it looks right:
   `python3 strategy/live/execute_rebalance.py --refresh --live` — places
   Market-on-Close orders, after a typed confirmation.
4. `python3 strategy/live/ib_test.py` the next morning — confirms fills and
   updated positions.

Full setup (TWS install, paper account creation, API configuration) and every
safety rail is documented in `strategy/live/README.md` — that's the onboarding
doc for anyone running this month to month.

## 10. Code Map

| File | Role |
|---|---|
| `strategy/strategy_lib.py` | The locked model: data loading, both engines, the game-theory sector selector, the throttle, and the backtest simulator. Nothing else in the repo re-implements this logic — everything imports it. |
| `strategy/backtest.py` | Runs the full 2001-to-today backtest; produces the numbers and chart in Section 6. |
| `strategy/signals.py` | The monthly rebalance sheet — prints target weights, no IBKR connection. |
| `strategy/data/` | Cached price (`prices.parquet`) and T-bill (`tbill_dgs3mo.parquet`) data. |
| `strategy/live/ib_config.py` | IBKR connection settings (host/port/client id). |
| `strategy/live/ib_test.py` | Read-only IBKR connection check — prints account value and positions, places nothing. |
| `strategy/live/execute_rebalance.py` | The execution bridge: turns `strategy_lib`'s target weights into IBKR share orders. Dry-run by default. |
| `strategy/live/README.md` | Full onboarding for the execution side: TWS setup, paper account creation, everyday commands. |
| `requirements.txt` (repo root) | Python dependencies (`pip3 install -r requirements.txt`). |

**GitHub:** https://github.com/quanttqueensu/Momentum-Game-Theory

## 11. Open Items Before Go-Live

- [ ] Committee approval / sign-off (Document Control, top of this document).
- [ ] Accumulate enough live paper-trading history to report a real (not
      backtested) track record.
- [ ] Second reviewer for the monthly signal, before this moves off paper.
- [ ] Scheduling: the rebalance is currently run by hand; a monthly
      cron/launchd job is a later step once it's trusted.
- [ ] Fractional-share / live-price sizing: currently whole shares sized off
      the prior close — fine at current account size, worth revisiting if the
      account grows materially.

## References

- Jegadeesh, N., & Titman, S. (1993). "Returns to Buying Winners and Selling
  Losers: Implications for Stock Market Efficiency." *Journal of Finance* —
  the original cross-sectional momentum result; the basis for scoring assets
  on 3-, 6-, and 12-month trailing returns (Sections 4.1–4.2).
- Moskowitz, T., Ooi, Y. H., & Pedersen, L. H. (2012). "Time Series Momentum."
  *Journal of Financial Economics* — momentum measured against an asset's own
  history, not just its peers; the basis for the T-bill hurdle in Section 4.1.
- Faber, M. (2007). "A Quantitative Approach to Tactical Asset Allocation."
  *Journal of Wealth Management* — trend-following via a long moving average
  (hold above, exit below) as a crash-avoidance overlay; the basis for the
  231-day/126-day regime filter in Section 4.2.
- Rosenthal, R. W. (1973). "A Class of Games Possessing Pure-Strategy Nash
  Equilibria." *International Journal of Game Theory* — the congestion-game
  formulation (players competing for shared capacity, equilibrium found by
  iterating best responses) underlying the sector engine's crowding tax in
  Section 4.2.
