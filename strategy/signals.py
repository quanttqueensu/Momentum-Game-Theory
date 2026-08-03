"""
signals.py  --  the monthly rebalance sheet. Run AFTER the month-end close:

    python3 signals.py --refresh

Prints the target book for next month: each engine's picks, the throttle
scale, and the final weights to trade at the NEXT trading day's close.
"""
import sys
import pandas as pd
import strategy_lib as S

refresh = "--refresh" in sys.argv
DI = S.get_data(refresh=refresh)

ps = S.style_weight_path(DI)
p6 = S.sector_weight_path(DI, ps)
t  = S.latest_formation(DI, ps, p6)   # refuses stub months / NaN hurdles

print(f"\nSignal date (month-end): {t.date()}   "
      f"(data through {DI['close'].index.max().date()})")
if not refresh:
    print("  !! cached prices -- run with --refresh after the month-end close")

w_style, w_sect = ps[t], p6[t]
print(f"\nSTYLE engine (65%):   {', '.join(f'{k} {v:.0%}' for k, v in w_style.items())}")
print(f"SECTOR engine (35%):  {', '.join(f'{k} {v:.0%}' for k, v in w_sect.items())}")

tgt_raw = S.combine_paths([(ps, S.W_STYLE), (p6, S.W_SECTOR)])[t]
tgt = S.throttle_target(DI, tgt_raw, t, S.BOOK_VT)
scale = (tgt[[c for c in tgt.index if c in S.RISK_TICKERS]].sum()
         / max(tgt_raw[[c for c in tgt_raw.index if c in S.RISK_TICKERS]].sum(), 1e-9))
if bool(DI["uptrend"].get(t, True)):
    print("\nThrottle: OFF (SPY above its 126d MA -- never throttled in uptrends)")
elif scale > 0.999:
    print("\nThrottle: ARMED (SPY below its 126d MA) -- book vol <= 12%, no trim needed")
else:
    print(f"\nThrottle: ACTIVE -- risk scaled to {scale:.0%}")
print(f"Defensive pick this month: {S.pick_defensive(DI, t)}")

print("\nFINAL TARGET BOOK (trade at next trading day's close):")
for k, v in tgt.sort_values(ascending=False).items():
    print(f"  {k:<5} {v:6.1%}")
print(f"  {'':<5} {tgt.sum():6.1%}  total")
