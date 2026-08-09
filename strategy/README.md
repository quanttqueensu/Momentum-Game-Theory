# The Two-Engine Book

A rule-based, tactical ETF rotation strategy: liquid equity/Treasury/cash
ETFs only, rebalanced monthly.

## 1. Purpose and Scope

This document describes a rule-based ETF rotation model that generates a
monthly rebalance. It runs on two engines and one safety control, all specified
exactly in Section 4.

The rest of the document covers why the approach should work (Section 3), the
precise rules (Section 4), the data and execution assumptions behind the backtest
(Section 5), how it's actually performed (Section 6), where its limits are
(Sections 7–8), how to run it each month (Section 9), where the code lives
(Section 10), and what's still open before go-live (Section 11).


## 2. Executive Summary

The book splits into two sleeves:

- **65%, style engine.** Picks the single strongest of seven broad equity
  exposures (US large-cap, Nasdaq, US small-cap, developed international,
  emerging markets, US large-cap growth, US large-cap value) by momentum.
- **35%, sector engine.** Picks four of eleven US sector ETFs, using a rule
  that taxes crowded, overlapping bets so the sleeve doesn't end up holding
  four versions of the same trade. The tax is book-aware: a sector correlated
  with whatever the 65% style engine is already holding gets taxed too, so
  the two sleeves can't quietly stack the same bet.

Both sleeves step out of equities into bonds or cash once their holdings stop
trending, and step back in on a faster signal than they stepped out on.

From 2001 to today, net of trading costs, the book returned +13.6%/yr against
SPY's +9.1%/yr, with a worst drawdown of −18.6% on month-end marks (−22.2% on
daily marks) against SPY's −50.8%. Sharpe is 0.92 against SPY's 0.53 and
60/40's 0.55.

The book is deliberately **not** a maximum-Sharpe portfolio. It is tuned to
participate in bull markets at a beta of 0.63, accepting a deeper drawdown than
a minimum-risk version would, because a strategy that lags a rising market for
long enough gets abandoned before its crash protection is ever needed. Section
6.3 documents that tradeoff and the settings that move it.

## 3. Why the Model Should Work

Two well-documented market facts underpin the rules.

**Momentum persists.** An asset that's done well over the past 3–12 months
tends to keep doing well over the next month, one of the oldest and most
replicated results in empirical finance. The effect is strongest across whole
asset classes and sectors and has weakened for individual large-cap stocks,
which is why this model rotates markets and sectors rather than picking single
names.

**Crashes are slow.** The 2000–02 and 2008 bear markets didn't happen in a
day, they ground down over many months. A slow trend filter, like checking
whether an index sits below its ~11-month average, can get you out of a
falling market early enough to avoid most of the damage.

The tradeoff is that a slow signal also gets you back in late, giving back
some of the recovery. Every rule in this model is a version of that tradeoff
in one form or another.

Signals are checked monthly rather than weekly, on purpose. Faster "quick
exit" rules were tested and came out 2–3%/yr worse with deeper drawdowns, the
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
   │              IWF IWD           │  by momentum MINUS crowding tax │
   │  by 3/6/12m composite momentum │  bear filter: SPY < 231d MA ->  │
   │  held while 12m OR 6m return   │  bonds/cash; back at 63d MA     │
   │  beats T-bills, else bonds/cash│                                 │
   └────────────────────────────────┴─────────────────────────────────┘
        VOLATILITY THROTTLE: OFF by default (BOOK_VT = 0.0)
      machinery retained and documented in 4.3; 0.15 re-arms it
```

### 4.1 Style Engine (65% of capital)

**Universe:** SPY (US large-cap), QQQ (Nasdaq-100), IWM (US small-cap), EFA
(developed international), EEM (emerging markets), IWF (Russell 1000 growth),
IWD (Russell 1000 value).

IWF and IWD give the sleeve the axis its name implies and it previously
lacked. The original five spanned *size* and *geography* but had no
*growth/value* dimension, so a growth-led or value-led tape could only be
expressed indirectly through QQQ. They were added as a **pair** deliberately:
adding the growth leg alone would be a disguised bet on technology, and in
testing it is the **value** leg that carries the in-sample improvement (Section
6.3). Each is held roughly 8% of months, so they rotate into the book without
dominating it.

At the close of each month:

1. **Score each ETF** on 3-, 6-, and 12-month total return (skipping the most
   recent month), standardize each, and average into one composite score.
   Blending three horizons makes the score harder to distort with one lucky
   quarter than a single window would.
2. **Take the top scorer.** All 65% goes into a single ETF. Broad indices,
   unlike single stocks, tend to stay in the lead for months at a time, so
   concentrating in the top pick is deliberate, spreading across all five
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
   65% into IEF (7–10yr Treasuries), but only if IEF itself clears the same
   hurdle. If IEF fails too, sit in plain T-bill cash instead. That second
   check is what kept the engine out of bonds in 2022, when bond prices fell
   alongside stocks.

### 4.2 Sector Engine (35% of capital)

**Universe:** the eleven iShares Dow Jones US sector ETFs, IYW (technology),
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
   of this game, a short iterative calculation, produces the final
   ranking.

   The tax also charges for capital the sector engine doesn't control: the
   65% sitting in whatever the style engine picked that month. A sector
   correlated with that pick is taxed as if it were correlated with a
   twelfth, fixed player holding 65% of the book, so a sector can't earn a
   top-four slot just by looking different from its ten sector peers while
   secretly doubling up on the style sleeve's bet. (Example: emerging
   markets and US technology look unrelated by label but have run ~0.7–0.85
   correlated for two decades, both lean on the same Asian
   semiconductor/hardware names, so a month spent in EEM taxes IYW hard
   even though IYW's own momentum score is the sleeve's strongest.)

   Raw momentum alone tends to put four flavors of the same trade at the top
   (technology and a semiconductor-heavy industrials sector, for example).
   The congestion tax swaps one of those duplicates for a genuinely different
   bet.
3. **Hold the top four, equal-weighted**, with the same anti-churn buffer as
   the style engine, a held sector stays held until it falls out of the
   equilibrium top six. Equal weighting is deliberate: using the game's raw
   equilibrium weights concentrates the sleeve and tested worse. The game's
   job is deciding *which* sectors to hold, not how much capital to give each
   one.
4. **Apply the bear filter.** If SPY closes the month below its 231-day
   average, the whole sleeve moves to the defensive asset (the same
   IEF-then-cash hurdle as the style engine). It only comes back to sector
   picks once SPY closes back above its **63-day** average, a much faster line
   than the one used to exit.

   Exiting slow and re-entering fast roughly halves the sleeve's worst-case
   lag behind SPY after a crash. Using a hurdled refuge instead of
   unconditional bonds is what mattered in 2022, when stocks and bonds sold
   off together.

   The re-entry line is 63 days rather than the 126 used previously. This sits
   on a **flat ridge**: 63, 84, and 105 days all score within noise of each
   other, so it is not a peak-pick. At 42 days the rule starts whipsawing and
   degrades. The faster line slightly improves both return and drawdown
   (in-sample Sharpe 1.09 → 1.11 on its own) because the exit is what provides
   crash protection, while the entry only controls how much of the recovery
   gets missed.

   Note that the throttle's arming line (Section 4.3) is a **separate**
   constant, `THROTTLE_ARM_MA`, even though both were 126 days before. Sharing
   one constant meant speeding up re-entry would have silently re-tuned the
   throttle as a side effect.

### 4.3 Book-Level Throttle — **off by default**

`BOOK_VT = 0.0`. The throttle is disabled in the shipped configuration. The
code is retained, still exercised by the backtest, and re-armed by setting
`BOOK_VT` to a non-zero cap. When armed, at each month-end close:

1. **Check if it's armed.** The throttle only arms while SPY closes the month
   below its `THROTTLE_ARM_MA` (126-day) average; above that line it does
   nothing no matter how much the book has gained.
2. **Measure volatility, if armed**, using the last 21 trading days — a fast
   read, since a volatility number from the prior quarter is stale mid-crash.
   Volatility is computed from the *target book's* asset returns times its
   weights, never from the strategy's own return history.
3. **Trim if it's above the cap.** Scale every risk position down by
   `cap / measured volatility` and move what's freed into that month's
   defensive pick. It never adds leverage and resets fresh every month.

**Why it's off.** The throttle is a risk dial, not an edge: over the full
sample it cost about 1%/yr of return to buy +0.02 of Sharpe. Its failure mode
is structural rather than bad luck. After a crash, SPY stays below its 126-day
average for *months into the recovery*, so the throttle cuts exposure at
precisely the moment the fast-re-entry rules have just bought back in. It cost
**9.7 points in 2020 alone**, and also hurt 2023, 2025 and 2026.

That failure mode was attacked directly before removing the control: arming the
throttle only while the 126-day average is still *falling* (i.e. standing down
once the trend has turned up) was implemented and tested. It does not work —
it gives up the COVID protection *and* fails to recover the return, so it was
rejected rather than shipped.

**What turning it off costs.** Honestly: crash protection, in exchange for
participation.

| Episode (daily marks) | Throttle on (12%) | Throttle off | SPY |
|---|:--:|:--:|:--:|
| COVID, Feb–Mar 2020 | −17% | **−20.5%** | −33.7% |
| GFC, 2007–09 | −20% | **−19.6%** | −55.2% |
| dot-com, 2000–02 | −9% | **−10.1%** | −47.3% |
| 2022 bear | −13% | **−17.8%** | −24.5% |

Setting `BOOK_VT = 0.15` is the documented middle option: it restores most of
the COVID protection (−19%) and costs roughly 2.5%/yr of post-2019 return. The
choice between them is a risk-appetite decision, not a modelling one, which is
exactly why the constant is exposed rather than buried.

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

- AGG, before September 2003
- IEF, before 2002
- EFA, before August 2001
- EEM, before 2003
- IWF and IWD, before June 2001 (both listed 26 May 2000; the 13-month
  history requirement makes them scoreable from mid-2001, so they are simply
  absent from the style sleeve's cross-section for the first months of the
  backtest rather than backfilled)

## 6. Backtest Results

How the model would have performed from 2001 to today, net of trading costs,
under the rules in Section 5.

### 6.1 Risk vs. SPY

| Metric | The Book | SPY | 60/40 |
|---|:--:|:--:|:--:|
| Worst drawdown (monthly) | **−18.6%** | −50.8% | −32.3% |
| Worst drawdown (daily) | **−22.2%** | −55.2% | — |
| Worst 12 months | **−18.5%** | −43.4% | −27.7% |
| Worst single month | **−8.7%** | −16.5% | −10.8% |
| Longest underwater period | **26 months** | 59 months | 46 months |
| Volatility (annualized) | 13.0% | 15.1% | 9.5% |
| Beta to SPY | 0.63 | 1.00 | 0.60 |

The pattern across every crash in the sample is the same: a severe loss for
SPY becomes a survivable one for the book.

| Episode | The Book | SPY |
|---|:--:|:--:|
| dot-com, Sep 2000 – Oct 2002 | −10.1% | −47.3% |
| GFC, Oct 2007 – Mar 2009 | −19.6% | −55.2% |
| COVID, Feb – Mar 2020 | −20.5% | −33.7% |
| 2022 bear | −17.8% | −24.5% |
| 2025 drawdown | −15.4% | −18.8% |

Calendar-year 2008 closed at **−1.0%** against SPY's −36.8%, and 2002 at −6.8%
against −21.6%. The stretch that genuinely stressed the model was 2022, when
bonds fell alongside stocks: the book lost −17.6% against SPY's −18.2%, saved
mostly by the hurdled refuge keeping the sleeves in cash rather than in falling
bonds. COVID is now the weakest episode in relative terms — a direct and
disclosed consequence of switching the throttle off (Section 4.3).

Smaller losses also recover faster, and that compounds: a −51% loss needs
+103% just to get back to even, and SPY spent 4.5 years underwater after the
2007 peak. A −19% loss only needs +23%, and the model's longest underwater
stretch was a bit over two years. That asymmetry, compounded over 25 years, is
why the book ends up ahead of SPY on return (+13.6%/yr vs. +9.1%/yr) while
carrying less risk, at a beta of 0.63.


### 6.2 Return and Risk-Adjusted Performance

Split between the in-sample period used to build the rules (2001–2018) and
everything since (2019–today, genuinely held out during development):

**Sharpe below is a real Sharpe ratio** — excess of the 3-month T-bill, divided
by volatility. Earlier versions of this document reported `ann_ret / ann_vol`
with no cash subtraction, which overstated every figure (the book's and the
benchmarks' alike) by roughly the cash rate. The comparison was always fair;
the absolute levels were not.

| Period | Sharpe | Ann. return | MaxDD | Worst month | t-stat |
|---|:--:|:--:|:--:|:--:|:--:|
| Book, 2001–18 (in-sample) | **+0.92** | **+13.0%** | −18% | −8.7% | +4.27 |
| Book, 2019–today | +0.90 | +15.1% | −19% | −7.5% | +3.06 |
| **Book, full period 2001–today** | **+0.92** | **+13.6%** | **−19%** | −8.7% | +5.26 |
| SPY, full period | +0.53 | +9.1% | −51% | −16.5% | +3.32 |
| 60/40 portfolio, full period | +0.55 | +6.9% | −32% | −10.8% | +3.78 |

Full-period alpha is +7.0%/yr at a beta of 0.63, with annual turnover around
6.9× (down from 7.4×). The full equity curve is in `backtest.png`.

**Two rows deserve care.** First, since 2019 the book's Sharpe is +0.90 and
SPY's is also +0.90 — dead level. The book's entire risk-adjusted edge over
SPY in this sample comes from 2001–2018, which contains two crashes; the
post-2019 sample contains no full-cycle bear market. Second, the 2019+ return
row is *stronger* than the in-sample row, which is the opposite of the usual
pattern and a reason for suspicion rather than confidence: two of the three
changes in Section 6.3 were evaluated against 2019+ data, so that period is no
longer a clean holdout for this configuration. See Section 7.

### 6.3 What Changed, and What It Cost

Three changes were made to increase bull-market participation. Each is reported
with its in-sample effect, not just its headline effect.

Both columns are scored with the corrected Sharpe, so they are comparable.

| | Baseline | Now |
|---|:--:|:--:|
| Ann. return, full | +12.6% | **+13.6%** |
| Sharpe, full | +0.91 | **+0.92** |
| Sharpe, in-sample | +0.97 | +0.92 |
| Volatility | 12.0% | 13.0% |
| Beta to SPY | 0.53 | 0.63 |
| Max drawdown (daily) | −19.7% | −22.2% |
| Turnover | 7.4× | **6.9×** |
| Bull-year wins vs SPY | 4 / 13 | **5 / 13** |
| Bull-year gap, median | −4.2% | **−3.3%** |
| Bull-year gap, mean | −3.3% | **−2.1%** |
| 12m windows lagging SPY >5pts (2019+) | 41% | **32%** |

The headline result is **+1.0%/yr of return at essentially unchanged
full-period Sharpe**, bought with 10 points of beta and 2.5 points of
drawdown. In-sample Sharpe does fall (0.97 → 0.92); that is the honest cost.

1. **Growth/value added to the style sleeve** (Section 4.1). Improves in-sample
   bull years from 3/7 to 4/7. Verified by drop-one testing: IWD (value) alone
   gives 4/7 with a +1.5% median gap, IWF (growth) alone gives 3/7 at −2.3%.
   The gain comes from the value leg, so this is not a disguised tech tilt.
2. **Faster sector re-entry, 126d → 63d** (Section 4.2). Small and robust:
   improves in-sample Sharpe and drawdown simultaneously, on a flat 63–105d
   ridge.
3. **Throttle off** (Section 4.3). The largest single lever and the least
   defensible on evidence: it adds only +0.2%/yr in-sample but +2.5%/yr after
   2019. It is a risk dial, and it is exposed as one constant.

**What was tried and rejected**, because negative results are evidence too:

- **A high-beta "accelerator" sleeve** (QQQ/XLK/IWF/IWO/SMH, trend-gated). Very
  strong on paper — post-2019 return +18.3%/yr — but drop-one testing showed
  the *entire* gain came from SMH (semiconductors). Remove it and post-2019
  return collapses to +11.9%. Rejected as a single-ticker bet wearing a sleeve
  costume.
- **Relaxing the crowding tax in uptrends.** The thesis was that crowding risk
  is a crash risk not worth insuring against in a rising market. It tested
  worse at every setting. The congestion tax earns its keep in all regimes.
- **Arming the throttle only on a falling 126d MA** (Section 4.3).
- **Reweighting toward the style sleeve** (75/25, 85/15). Raises beta and
  return but costs more Sharpe than it returns. `W_STYLE` is exposed if a
  higher-beta configuration is ever wanted: 75/25 delivers beta 0.72 and a
  −23% drawdown.
- **A third, thematic sleeve** (semis, software, biotech, miners, homebuilders,
  cyber, clean energy — 20 industry/thematic ETFs, same momentum + hurdle +
  regime machinery). Rejected on three counts. It is a *weak* sleeve: standalone
  Sharpe 0.69 against the sector sleeve's 1.11. Blended at 20% it added only
  +0.5%/yr while deepening drawdown (−19% → −21%). And the test window can only
  start in 2008, because most thematic ETFs did not exist earlier — while the
  universe itself is **survivorship-biased by construction**, since the
  thematic ETFs available to download today are precisely the ones that did not
  get liquidated (the dead HOLDRS — BBH biotech, HHH internet, SWH software,
  TTH telecom — are simply invisible). The 11 sector ETFs are a stable,
  complete, economically exhaustive partition of the US market; a thematic list
  is a survivor list. A +0.5%/yr edge measured with that bias pointing in its
  favour is not an edge. Notably it *did* pass drop-one testing, so unlike the
  SMH sleeve it was not a single-ticker artifact — just not worth 20 extra
  tickers in live execution.

### 6.4 How to Size It — and Why "Riskier" Is the Wrong Dial

A natural instinct is to make the strategy more aggressive and then hold less
of it. Arithmetic says don't. Holding the book at weight *w* with the
remainder in cash gives total return `rf + w·(book − rf)` and total volatility
`w · book_vol`. **Sharpe is unchanged by construction:**

| Deployed | Cash | Ann. return | Volatility | Max DD | Sharpe |
|:--:|:--:|:--:|:--:|:--:|:--:|
| 100% | 0% | +13.6% | 13.0% | −19% | +0.92 |
| 85% | 15% | +11.9% | 11.1% | −16% | +0.92 |
| 70% | 30% | +10.2% | 9.1% | −13% | +0.92 |
| 55% | 45% | +8.4% | 7.2% | −10% | +0.92 |
| 40% | 60% | +6.6% | 5.2% | −6% | +0.92 |

So a riskier configuration held at a smaller weight only helps if that
configuration has a **higher Sharpe**. Every higher-octane variant tested has a
*lower* one, and therefore loses once sized back to equal total risk:

| Configuration | Standalone | Sized to 13.0% total vol |
|---|:--:|:--:|
| **Shipped 65/35** | +13.6% @ 13.0% vol | **+13.6%** |
| 75/25 | +13.8% @ 13.9% vol | +13.0% |
| 85/15 | +13.8% @ 14.8% vol | +12.3% |
| 100% style sleeve | +14.0% @ 16.4% vol | +11.5% |
| + thematic sleeve 20% | +12.8% @ 13.3% vol | +12.6% |

The shipped 65/35 configuration sits at the Sharpe peak, so it wins at every
level of total risk. **The allocation percentage is the risk dial, not the
strategy's internals** — and it is the free one, because moving it costs no
Sharpe while re-tuning the engines does.

The one thing sizing cannot do is take total risk *above* 13.0% volatility,
since that would require leverage. If more absolute return is genuinely wanted,
the 100%-style-sleeve configuration reaches +14.0%/yr — but at 16.4% vol and a
−30% drawdown, which is +0.4%/yr for +8 points of drawdown. That is a bad
trade, and it is why it was not shipped.

**The ceiling on this objective.** Beating SPY in a bull *year* is far harder
than it looks for any strategy that ever holds cash. A 100%-invested trend
following rule on SPY alone — no sector sleeve, no crowding tax — still wins
only 1–2 of the 6 bull years since 2019, because the trend filter costs 4–6
points at the exits and re-entries. Without leverage, the only way to *reliably*
beat SPY in bull years is to hold assets with beta greater than 1, which is the
concentration risk this book exists to avoid. The realistic goal was narrowing
the gap, and the gap narrowed; it did not close.


## 7. Evaluation Discipline

- **Pre-register the benchmark.** Evaluate against a 60/40 stock/bond blend as
  the primary comparison, not SPY alone. SPY is a 100%-equity, unhedged
  comparison, and this book is still lower-beta (0.63).
- **Pre-register the evaluation horizon.** Judge on a rolling 3-year basis, not
  any single 12-month stretch. Since 2019, trailing-12-month windows lagged SPY
  by more than 5 points 32% of the time (improved from 42%, but still common
  enough that a strict 1-year abandonment rule would pull this model in the
  middle of doing what it was built to do).
- **2019+ is no longer a clean holdout for the current configuration.** The
  original rules were selected on 2001–2018 and checked once against 2019+. The
  three changes in Section 6.3 were not: they were evaluated on both windows,
  which is why Section 6.3 reports the in-sample effect of each change
  separately, and why the throttle decision is flagged as the weakest of the
  three (+0.2%/yr in-sample against +2.5%/yr after 2019).

  Treat the +15.1% post-2019 figure as **an upper bound on expectations, not a
  forecast.** The in-sample row (+13.0%, Sharpe 1.02) is the more honest number
  to plan against, and even it benefits from the full sample having been seen.
  The genuinely clean claim is narrower: the changes were chosen using
  drop-one and flat-ridge robustness tests rather than by maximizing a headline,
  and two candidate designs that scored *better* on the headline (the SMH
  accelerator sleeve, and reweighting to 75/25) were rejected precisely because
  they failed those tests.

## 8. Operating Cadence

Monthly, near the close on the last trading day of the month:

1. `python3 strategy/signals.py --refresh`, prints the target book
   (informational only, no IBKR connection).
2. `python3 strategy/live/execute_rebalance.py --refresh`, dry run against the
   live paper account; prints the exact order ticket.
3. Read the order ticket. If it looks right:
   `python3 strategy/live/execute_rebalance.py --refresh --live`, places
   Market-on-Close orders, after a typed confirmation.
4. `python3 strategy/live/ib_test.py` the next morning, confirms fills and
   updated positions.

Full setup (TWS install, paper account creation, API configuration) and every
safety rail is documented in `strategy/live/README.md`, that's the onboarding
doc for anyone running this month to month.

## 9. Code Map

| File | Role |
|---|---|
| `strategy/strategy_lib.py` | The locked model: data loading, both engines, the game-theory sector selector, the throttle, and the backtest simulator. Nothing else in the repo re-implements this logic, everything imports it. |
| `strategy/backtest.py` | Runs the full 2001-to-today backtest; produces the numbers and chart in Section 6. |
| `strategy/signals.py` | The monthly rebalance sheet, prints target weights, no IBKR connection. |
| `strategy/data/` | Cached price (`prices.parquet`) and T-bill (`tbill_dgs3mo.parquet`) data. |
| `strategy/live/ib_config.py` | IBKR connection settings (host/port/client id). |
| `strategy/live/ib_test.py` | Read-only IBKR connection check, prints account value and positions, places nothing. |
| `strategy/live/execute_rebalance.py` | The execution bridge: turns `strategy_lib`'s target weights into IBKR share orders. Dry-run by default. |
| `strategy/live/README.md` | Full onboarding for the execution side: TWS setup, paper account creation, everyday commands. |
| `requirements.txt` (repo root) | Python dependencies (`pip3 install -r requirements.txt`). |

**GitHub:** https://github.com/quanttqueensu/Momentum-Game-Theory



## References

- Jegadeesh, N., & Titman, S. (1993). "Returns to Buying Winners and Selling
  Losers: Implications for Stock Market Efficiency." *Journal of Finance*, the original cross-sectional momentum result; the basis for scoring assets
  on 3-, 6-, and 12-month trailing returns (Sections 4.1–4.2).
- Moskowitz, T., Ooi, Y. H., & Pedersen, L. H. (2012). "Time Series Momentum."
  *Journal of Financial Economics*, momentum measured against an asset's own
  history, not just its peers; the basis for the T-bill hurdle in Section 4.1.
- Faber, M. (2007). "A Quantitative Approach to Tactical Asset Allocation."
  *Journal of Wealth Management*, trend-following via a long moving average
  (hold above, exit below) as a crash-avoidance overlay; the basis for the
  231-day/63-day regime filter in Section 4.2.
- Rosenthal, R. W. (1973). "A Class of Games Possessing Pure-Strategy Nash
  Equilibria." *International Journal of Game Theory*, the congestion-game
  formulation (players competing for shared capacity, equilibrium found by
  iterating best responses) underlying the sector engine's crowding tax in
  Section 4.2.
