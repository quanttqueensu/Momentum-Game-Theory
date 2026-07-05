# ETF Rotation: Momentum + Congestion Game + Risk Overlay

Built from scratch (no code shared with the rest of this repo). Data: yfinance
adjusted close, cached in `data/prices.parquet` (regenerate with
`python3 probe_universe.py`). Run everything with `python3 run.py`
(or `python3 run.py momentum game` for chosen variants).

## Universe (37 tradeable ETFs + 2 benchmarks)

- **Sectors:** XLK XLF XLE XLV XLY XLP XLI XLB XLU XLRE XLC (1998; XLRE 2015, XLC 2018)
- **Factors:** MTUM QUAL VLUE USMV SIZE SPLV SPHB (2011–2013)
- **US size/style:** IWM IWF IWD MDY (1996–2000)
- **Country/region:** EWJ EWG EWU EWC EWA EWZ EWY EWT EWH EWS EWW EEM VGK FXI INDA (1996–2012)
- **Benchmarks only (not tradeable):** SPY, QQQ

Unequal inception is handled by point-in-time eligibility: an ETF joins the
pool only once it has full lookback history (~13 months) at a rebalance date.
No survivorship or look-ahead from late listings. Backtest starts when ≥15
ETFs are eligible (first rebalance 2000-01-31, returns from 2000-02-01).

## Architecture (each layer independently switchable in `config.py`)

1. **Momentum** (`signals.py`) — cross-sectional blend: mean of z-scored 3m,
   6m, 12-1m total returns; hold top 6 equal-weight; absolute filter sends a
   slot to cash when raw blended momentum ≤ 0. Monthly rebalance, executed at
   the next day's close (no look-ahead).
2. **Game theory** (`game.py`) — capital-competition congestion game over the
   top-12 candidates: allocating to ETF i earns its momentum score but pays a
   congestion tax λ·(ρw)_i for crowding into correlated assets; Nash
   equilibrium via replicator dynamics on the potential function.
   Three modes: `selector` (default — equilibrium picks WHICH 6, equal weight
   sizes them), `sizing` (hold equilibrium weights — documented negative
   result), `crowdfade` (comomentum throttle on the invested fraction).
3. **Risk** (`engine.py`) — (a) vol targeting: exposure = min(18% / trailing
   21d realized vol, 1); (b) drawdown brake with hysteresis: exposure ×0.7
   after a 15% strategy drawdown, restored below 10%. Long-only, no leverage,
   cash earns 0% (conservative — no T-bill credit).
4. **Agent 0** (`signals.random_weights`) — random top-6 from the same
   eligible pool, same costs and risk layer, 100 seeds.

Costs: 5 bps one-way on all turnover. Sharpe/Sortino use rf = 0.

## Results (net of costs)

| Window | Strategy CAGR | SPY CAGR | Sharpe | SPY Sharpe | MaxDD | SPY MaxDD |
|---|---|---|---|---|---|---|
| 2000–2026 | **9.5%** | 8.5% | **0.67** | 0.52 | **-29%** | -55% |
| 2003–2018 | **10.3%** | 8.9% | **0.73** | 0.56 | **-21%** | -55% |
| 2019–2026 | 13.9% | **17.5%** | 0.87 | **0.92** | **-29%** | -34% |

- Beats 99–100% of Agent 0 random seeds in every window — the signal is real.
- **Honest headline: the trailing-7y window is not beaten**, on return or
  (narrowly) on Sharpe. The gap is the mega-cap concentration premium; closing
  it in-sample would mean tilting into exactly the bet the window rewards
  (fewer names, growth/QQQ proxies, no absolute filter) — that is curve
  fitting, and it degrades every other window.

## Layer attribution (ablation, see `run.py` output)

- **Momentum does most of the work** (+3–5 CAGR pts over equal-weight, +5 pts
  over random, in all windows).
- **Game selector** adds modestly and most where it matters: 2019–2026 Sharpe
  0.80→0.91 pre-risk, rolling-12m-beats-SPY share 29%→45%. Roughly free on
  the long windows. Calibrated on 2003–2018 + full history only, λ=4.
- **Game as sizing** is a documented failure: equilibrium weights concentrate
  (effective N ≈ 1–4) and underperform equal weight at every λ.
- **Vol targeting** is the risk layer's value: fast 21d lookback improves
  full-history Sharpe 0.65→0.70 standalone and halves 2008-style drawdowns.
- **Drawdown brake** is negative-carry insurance: costs ~0.5 CAGR pt and a
  little Sharpe, buys 3–5 pts of max drawdown. Defensible; disable via
  `dd_trigger=9.9` if the premium isn't wanted.
- Known conservative bias: cash at 0% understates 2022–2026 results by
  roughly +0.4 CAGR pt/yr (avg ~15% cash × ~3–5% T-bill yield).
