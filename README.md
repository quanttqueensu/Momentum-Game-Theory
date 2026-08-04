# Momentum-Game-Theory

Game Theory Momentum strategy: a self-contained two-engine ETF rotation book, **65% style rotation / 35% sector rotation via a congestion-game equilibrium**

**Setup:** `pip3 install -r requirements.txt` (Python 3.14).

Everything lives in [`strategy/`](strategy/):

- `strategy/README.md`, how it works, the results, and how to frame it
  (technical/model documentation, incl. limitations and governance)
- `python3 strategy/signals.py --refresh`, the monthly rebalance sheet
- `python3 strategy/backtest.py`, the full 2001→present backtest
- [`strategy/live/`](strategy/live/), the IBKR paper-trading execution bridge;
  `strategy/live/README.md` is the onboarding doc for running the monthly
  rebalance end to end
