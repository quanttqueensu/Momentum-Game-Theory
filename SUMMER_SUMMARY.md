# Summer Progress Summary — Momentum Game Theory

**Hugh Hayes · QUANTT**
**Period:** May 24 – August 2026


## TL;DR

Over the summer this project went through six distinct strategy designs,
rejected three of them on hard evidence (not gut feel), and converged on a
systematic ETF rotation strategy — "The Two-Engine Book" — that beats a 60/40
benchmark on both return and risk over a 25-year backtest (2001–today) and is
now live on an Interactive Brokers paper trading account, with the first
orders transmitted in early August 2026.

## 1. What Was Built
The final strategy (full detail in `strategy/README.md`) trades a fixed
universe of 20 liquid ETFs across two independent engines — a 65% sleeve
rotating between 7 broad equity exposures, and a 35% sleeve rotating between 11
US sectors using a game-theoretic selection rule — plus one book-level
volatility control, retained in code but disabled by default. On top of
the research code, a full execution pipeline was built this summer connecting
the strategy's monthly output to a real broker account (Interactive Brokers,
via the `ib_async` API) so it can actually place orders, not just backtest.

## 2. Proof of Multiple Strategies Tested

This wasn't one idea built once. Each stage below was actually implemented,
backtested, and evaluated before being kept or rejected — the commit history
on GitHub (Section 5) timestamps all of it.

| Stage | Design | Outcome |
|---|---|---|
| 1 (late May) | Single-stock S&P 500 dollar-neutral long/short, factor-residual momentum (Fama-French adjusted), correlation-based crowding gate | **Rejected** — net Sharpe ≈ 0.1 after costs, statistically indistinguishable from zero. Individual large-cap stock momentum has been dead as a tradeable signal since roughly 2009. |
| 2 (mid-June) | Long-only multifactor version of the same S&P 500 universe | Real improvement over Stage 1, but still trailed the S&P 500 index itself — an active strategy losing to its own benchmark isn't a strategy. |
| 3 (late June) | Broadened to ETF-level rotation — country, sector, and multi-asset universes; six distinct designs built and compared in the same week | Three kept for further work, three dropped. (From the commit log, in Hugh's own words at the time: *"Tried 6 different ones, left with 3 variations, initial strat didn't work, strat 3 kind of, strat 6 works very well."*) |
| 4 (late June–July) | Cross-asset and equity "dual momentum" designs — hold an asset only if it beats a cash/T-bill hurdle, not just its peers | Identified the T-bill hurdle as the single biggest driver of the whole approach's edge — it's what keeps the strategy out of falling markets. |
| 5 (July) | Multi-sleeve blended books; added a game-theoretic sector selector — a congestion-game Nash equilibrium (replicator dynamics) that taxes crowded, overlapping sector bets | The game-theory layer produced a measurable, repeatable improvement in exactly the regime it was designed for (concentrated mega-cap-driven markets). |
| 6 (July, final) | Consolidated everything into one strategy: 65% style rotation / 35% sector rotation with the game-theoretic selector + a crash-only volatility throttle | **Adopted — this is what's trading live today.** |

Every stage was evaluated on a disciplined split: rules were built and tuned
on 2001–2018 data only, then checked against 2019–today data that was
genuinely held out — and checked only once per major design decision, not
iterated against, to avoid the classic trap of overfitting to your own
out-of-sample window by peeking at it repeatedly. This discipline, and its
limits, are disclosed in full in `strategy/README.md` Section 7.

## 3. Backtest Results (Adopted Design)

Net of 10bps trading costs, next-close execution, real T-bill cash returns:

| Period | Sharpe | Ann. return | Max drawdown | t-stat |
|---|:--:|:--:|:--:|:--:|
| In-sample, 2001–2018 | +0.92 | +13.0% | −18% | +4.27 |
| 2019–today | +0.90 | +15.1% | −19% | +3.06 |
| **Full period, 2001–today** | **+0.92** | **+13.6%** | **−19%** | **+5.26** |
| SPY, full period | +0.53 | +9.1% | −51% | +3.32 |
| 60/40 portfolio, full period | +0.55 | +6.9% | −32% | +3.78 |

Sharpe figures are excess of the 3-month T-bill. An earlier version of this
table divided total return by volatility with no cash subtraction, which
inflated every row — the book's and the benchmarks' alike — by roughly the
cash rate. The comparison was always fair; the levels were not.

The strategy does **not** claim to beat SPY on raw return in every stretch —
it beats SPY on risk-adjusted return and on drawdown, and it's designed to
sometimes lag SPY in strong bull years by giving up some upside in exchange
for a much shallower worst case (−19% vs. SPY's −51% in the sample period).
That trade-off, and exactly how often it shows up, is spelled out honestly in
`strategy/README.md` Sections 6–7 — worth reading before the 1-on-1, since
it's likely to come up.

**Update, 9 Aug 2026 — bull-market participation pass.** The book was
deliberately re-tuned to give up some risk-adjusted safety for upside: a
growth/value axis added to the style sleeve, faster sector re-entry (126d →
63d), and the volatility throttle switched off. Net effect is +1.1%/yr of
return at *identical* full-period Sharpe, with beta rising 0.53 → 0.63 and max
drawdown 19.7% → 22.2%. Bull-year wins against SPY improved from 4/13 to 5/13
and the mean bull-year gap from −3.3% to −2.1%. Two better-scoring candidates
were **rejected** for failing robustness tests — full write-up, including the
rejected designs and the in-sample cost of each accepted change, in
`strategy/README.md` Section 6.3.

## 4. Real History — Live Paper Trading

Backtests are cheap to produce and easy to overstate; the real proof is a
live account taking real (if simulated) fills. This summer that pipeline got
built end to end:

- An Interactive Brokers paper trading account, connected via TWS (Trader
  Workstation) over the `ib_async` API — the strategy's target weights are
  turned into actual share orders, sized off live account value.
- Safety rails: dry-run by default, a paper-account guard that refuses to
  trade a non-paper account, a fat-finger guard that aborts any single order
  over 90% of account value, and a typed confirmation before anything
  transmits.
- A currency-aware sizing fix (the paper account is CAD-denominated, every
  ETF traded prices in USD) so order sizes are computed correctly.
- **First live paper orders transmitted in early August 2026.**

**[Insert here: TWS screenshot or account statement showing the transmitted
order(s) and resulting positions — pull this from TWS directly, or run
`python3 strategy/live/ib_test.py` while TWS is open and paste its output.
This is the single most convincing piece of evidence for the "real history"
ask — worth capturing now and then again every month between now and the
committee meeting so there's a growing, dated track record to show, not just
one data point.]**

## 5. Development Timeline

Dated commit history from the project's GitHub repository
(https://github.com/quanttqueensu/Momentum-Game-Theory) — independently
verifiable, not self-reported:

| Date | Milestone |
|---|---|
| 2026-05-24 | Project started |
| 2026-05-31 | Data pipeline built |
| 2026-06-07 | Factor residualization (idiosyncratic returns) implemented |
| 2026-06-15 | First working strategy layer + backtest split |
| 2026-06-29 | Six candidate designs built and compared; three carried forward |
| 2026-07-04 – 07-05 | Final strategy locked; game-theoretic (replicator dynamics) sector selector added |
| 2026-07-27 | IBKR paper trading integration built |
| 2026-08-01 – 08-02 | Live paper trading orders placed |
