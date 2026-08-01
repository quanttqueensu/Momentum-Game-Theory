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
| Document date | 2026-07-25 |
| Model owner | Hugh Hayes (strategy lead) |
| Approval status | [fill in — pending committee review] |

Fill in the blank field before you present this document to the committee.

---

## 1. Purpose and Scope

This document describes a rule-based model. The model picks ETFs for the
club's portfolio once a month. The model has two engines and one safety
control. Section 4 gives the exact rules.

This document tells you:

- why the model should work (Section 3),
- what the model does, step by step (Section 4),
- what data the model uses (Section 5),
- how the model performed in tests (Section 6),
- what limits the model has (Section 7 and Section 8),
- how to run the model each month (Section 9),
- what files hold the model (Section 10),
- what is still open before go-live (Section 11).

The model is not a guarantee. Do not present it as one. Section 7 lists
the limits you must disclose before you pitch this model to the
committee.

## 2. Executive Summary

The model splits the club's capital into two sleeves.

- 65% of capital goes to the **style engine**. This engine picks the
  single strongest equity market from a list of five.
- 35% of capital goes to the **sector engine**. This engine picks four US
  sectors from a list of eleven, using a rule that taxes crowded picks.

Both engines step out of equities and into bonds or cash when their
holdings stop trending. A single throttle also trims the whole book when
volatility is high during a market downturn.

From 2001 to today, net of trading costs, the model returned +12.6% per
year. SPY (the S&P 500 index) returned +9.0% per year over the same
period. The model's worst drawdown was −19%. SPY's worst drawdown was
−51%.

## 3. Conceptual Soundness — Why the Model Should Work

The model rests on two market facts. Both facts are well documented in
academic finance research.

**Fact 1 — Momentum.** An asset that has done well over the past 3 to 12
months tends to keep doing well over the next month. This effect is one
of the oldest and most replicated findings in finance.

The momentum effect is strongest across broad asset classes and sectors.
It has weakened for individual large-cap stocks. For this reason, the
model rotates whole markets and sectors. The model does not pick
individual stocks.

**Fact 2 — Crashes are slow.** Bear markets, such as 2000–2002 and 2008,
did not happen in a single day. They ground down over many months. A
slow trend signal — for example, "is the index below its ~11-month
average?" — can exit a falling market early enough to avoid most of the
damage.

A slow signal has a cost. It also re-enters a recovering market late.
This means the model gives back some of the recovery gain. Every rule in
this model balances these two facts against each other.

The model checks its signals once a month, not once a week. Faster,
weekly "quick exit" rules were tested. They performed 2–3% per year
worse and produced deeper drawdowns, because they sold dips and bought
back in at higher prices. The monthly frequency is a deliberate design
choice, not a shortcut.

## 4. Model Specification

This section states the exact rules of the model. Follow the rules in
the order given. Each engine runs independently. The throttle then
applies to the combined book.

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

**Universe.** The style engine chooses from five broad equity ETFs:

- SPY — US large-cap
- QQQ — Nasdaq-100
- IWM — US small-cap
- EFA — developed international markets
- EEM — emerging markets

**Procedure.** Run these steps at the close of every month.

1. **Score each ETF.** Calculate each ETF's 3-month, 6-month, and
   12-month total return. Skip the most recent month in each
   calculation. Standardize the three numbers and average them into one
   composite score. Three horizons make the score harder to distort with
   one lucky quarter than a single horizon would.
2. **Select the top scorer.** Assign all 65% of capital to the ETF with
   the highest composite score. The engine holds one ETF at a time.
   Broad indices, unlike single stocks, tend to stay in the lead for
   months, so concentration in the top pick is deliberate. Spreading
   capital across all five ETFs would dilute the signal.
3. **Apply the incumbency buffer.** If the engine already holds an ETF,
   keep holding it as long as it ranks in the top two. This rule removes
   most position flips and their trading costs.
4. **Apply the T-bill hurdle.** Before you buy the top pick, check its
   trailing return against T-bills over the same window. Buy the pick
   only if its trailing 12-month return OR its trailing 6-month return
   beats the T-bill return for that window. If equities cannot beat
   cash, the engine does not hold equities.

   The 6-month check is the **fast re-entry rule**. After a crash, the
   6-month return turns positive months before the 12-month return does.
   The fast re-entry rule lets the engine buy back in near the market
   bottom, rather than a year later.
5. **Select the defensive asset, if no pick qualifies.** If no ETF
   passes the T-bill hurdle, assign the 65% to IEF (7–10 year
   Treasuries) — but only if IEF itself passes the T-bill hurdle. If IEF
   fails the hurdle too, hold plain T-bill cash instead. This second
   check kept the engine out of bonds during 2022, when bond prices fell
   alongside stock prices.

### 4.2 Sector Engine (35% of capital)

**Universe.** The sector engine chooses from eleven US sector ETFs
(iShares Dow Jones sector series): IYW (technology), IYF (financials),
IYH (healthcare), IYE (energy), IYC (consumer discretionary), IYZ
(telecom), IYK (consumer staples), IDU (utilities), IYM (materials), IYJ
(industrials), IYR (real estate).

**Procedure.** Run these steps at the close of every month.

1. **Score all eleven sectors.** Use the same composite momentum
   calculation as the style engine (Section 4.1, step 1).
2. **Tax crowded sectors.** This step is the model's game-theory layer.
   Treat the eleven sectors as players in a congestion game for the
   sleeve's capital. A sector earns its momentum score, but pays a
   penalty. The penalty grows with the amount of capital already
   assigned to sectors that correlate with it, measured over the past
   126 trading days. Find the equilibrium of this game with a simple
   iterative calculation. The equilibrium produces the final sector
   ranking.

   Momentum scores alone often rank four versions of the same trade at
   the top — for example, technology and a semiconductor-heavy
   industrials sector. The congestion tax replaces one of those
   duplicate picks with a genuinely different bet.
3. **Hold the top four, equal-weighted.** Assign equal capital to the
   top four sectors in the equilibrium ranking. Keep a held sector until
   it falls out of the equilibrium top six — the same anti-churn rule as
   the style engine's incumbency buffer.

   Equal weighting is deliberate. Using the game's raw equilibrium
   weights concentrates the sleeve and performs worse in testing. The
   game's value is in choosing which sectors to hold, not how much
   capital to assign each one.
4. **Apply the bear filter.** Check SPY's closing price against its
   231-day moving average at the end of each month. If SPY closes below
   that average, move the whole sleeve to the defensive asset — the same
   rule as the style engine's step 5 (IEF if it passes the T-bill
   hurdle, otherwise cash). Return the sleeve to sector picks only after
   SPY closes back above its 126-day moving average — not the 231-day
   average used for the exit.

   Exit on the slow signal; re-enter on the fast signal. Waiting for the
   231-day average to recross costs about 1.7% per year and doubles the
   sleeve's worst-case lag behind SPY after a crash. Using a hurdled
   refuge, instead of unconditional bonds, matters during combined
   stock-and-bond bear markets such as 2022.

### 4.3 Book-Level Throttle

The throttle is a safety control for the combined book. It runs only
during a possible crash. Follow these rules at the close of every month.

1. **Check the arming condition.** The throttle is armed only while SPY
   closes the month below its 126-day moving average. Above that level,
   the throttle does nothing, no matter how much the book has gained.

   Volatility rises in two different situations: during a crash, and
   during the first violent year of a recovery. Only the first situation
   is dangerous. An always-on throttle would cut exposure during a
   recovery, right after the re-entry rules had bought back in — this is
   how a model ends up far behind a rebound year.
2. **Measure volatility, if armed.** Calculate the volatility the
   current portfolio would have shown over the last 21 trading days.
   This is a fast, one-month read. During a crash, a volatility reading
   from the prior quarter is stale.
3. **Trim, if volatility exceeds 12% annualized.** Reduce every risk
   position by the same proportion: `scale = 12% / measured volatility`.
   Move the freed capital into that month's defensive pick (IEF or
   cash). The throttle never adds leverage, and it resets fresh every
   month.

The 12% cap is the club's risk dial. Backtests at 10% and 15% caps show
smooth changes in return and drawdown, with no sharp breaks. The 126-day
line is the same line the sector engine already uses for re-entry
(Section 4.2, step 4) — the throttle does not add a new parameter.

## 5. Data and Execution Assumptions

The backtest in Section 6 follows these rules. The rules exist to
prevent the model from using information it would not have had in real
time.

- Signals use only month-end data.
- Trades execute at the next trading day's closing price, not the
  signal day's price.
- Every trade pays a cost of 10 basis points (0.10%).
- Cash returns use the real FRED T-bill rate for each period.
- An ETF is not scored until it has 13 months of live trading history.

Price data comes from adjusted daily closes. T-bill data comes from
FRED. Both are cached in the `data/` folder.

Some ETFs have short histories. Before an ETF's first trade date, its
period is scored at the T-bill rate:

- AGG — before September 2003
- IEF — before 2002
- EFA — before August 2001
- EEM — before 2003

No return is backfilled or invented for these gaps.

## 6. Outcomes Analysis — Backtest Results

This section reports how the model would have performed from 2001 to
today, net of trading costs, using the data rules in Section 5.

### 6.1 Risk Comparison vs. SPY

| Metric | The Book | SPY |
|---|:--:|:--:|
| Worst drawdown (monthly) | **−19.1%** | −50.8% |
| Worst drawdown (daily) | **−20.2%** | ~−55% |
| Worst 12 months | **−19.1%** | −43.4% |
| Worst single month | **−8.8%** | −16.5% |
| Longest underwater period | **25 months** | 52 months |
| Volatility (annualized) | 12.2% | 15.1% |
| Beta to SPY | 0.55 | 1.00 |

Read the table this way:

- **The model cuts crash losses to a survivable size.** In 2008, SPY
  lost −50.8% peak to trough. The model lost −19.1% — its worst episode
  ever. Calendar-year 2008 for the model closed at just −0.3%. In the
  dot-com bear (2001–02), SPY lost −28.0% and the model lost −7.3%.
  During COVID (Feb–Mar 2020), SPY lost −19.4% and the model lost
  −6.8%. In 2022 — the model's hardest environment, because bond prices
  fell alongside stocks — SPY lost −18.2% and the model lost −16.1%. The
  model's hurdled refuges kept its sleeves in cash instead of falling
  bonds that year.
- **Smaller losses recover faster.** A −51% loss needs a +103% gain to
  break even. SPY spent 4.5 years underwater after the 2007 peak. A
  −19% loss needs only a +24% gain to break even. The model's longest
  underwater stretch was just over 2 years. Compounded over 25 years,
  this asymmetry is why the model ends up ahead of SPY on return
  (+12.6% vs. +9.0% per year) while carrying much less risk.
- **One-line summary: roughly 40% of SPY's worst case.** The model's
  beta is 0.55, and its worst-case numbers are well under half of SPY's
  at every horizon in the table.

**Disclose this caveat to the committee before you present the model.**
−20.2% is the worst *daily* reading, from March 2020. It is deeper than
the monthly table above suggests. State this number to the committee in
advance, so no one is surprised by it during a live crash.

### 6.2 Return and Risk-Adjusted Performance

The table below splits the test period into an in-sample period
(2001–2018, used to build the rules) and an out-of-sample period
(2019–today, held out during development).

| Period | Sharpe | Ann. return | MaxDD | Worst month | t-stat |
|---|:--:|:--:|:--:|:--:|:--:|
| Book, 2001–18 (in-sample) | **+1.08** | **+12.8%** | −19% | −8.8% | +4.49 |
| Book, 2019–today (out-of-sample) | +0.93 | +12.0% | −16% | −7.7% | +2.60 |
| **Book, full period 2001–today** | **+1.03** | **+12.6%** | **−19%** | −8.8% | +5.17 |
| SPY, full period | +0.59 | +9.0% | −51% | −16.5% | +3.27 |
| 60/40 portfolio, full period | +0.71 | +6.8% | −32% | −10.8% | +3.74 |

Full-period alpha is +6.9% per year at a beta of 0.55. Annual turnover
is about 7.3×. The chart file `backtest.png` shows the full equity
curve.

**Disclose this pattern to the committee.** The model has never had a
losing year while SPY was up big — its worst bull-year absolute return
was +4.1% in 2025. But 2019–today has been a nearly unbroken mega-cap
bull market. In that period, 42% of rolling 12-month windows showed the
model lagging SPY by more than 5 percentage points.

**Do not run this model under an annual review against SPY.** Get the
60/40 benchmark and a 3-year review horizon agreed with the committee,
in writing, before you go live.

