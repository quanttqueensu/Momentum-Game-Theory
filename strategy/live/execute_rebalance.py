"""
execute_rebalance.py -- the bridge from the strategy's monthly signal to real
IBKR orders. This is the piece that was missing; signals.py already decides
WHAT to hold, this decides the share-level orders and hands them to IBKR.

WHAT IT DOES, in order:
  1. Runs the locked strategy (strategy_lib) to get this month's target WEIGHTS
     -- exactly the book signals.py prints. Data comes from yfinance/FRED as
     always; IBKR is NOT the signal source.
  2. Connects to the IBKR connector app (TWS/Gateway) on this machine.
  3. Reads your account value + current positions from IBKR.
  4. Turns target weights into target SHARE counts (sized off the latest close),
     and computes the delta vs. what you already hold.
  5. DRY RUN (default): prints the exact orders and stops. Places nothing.
     --live: places Market-on-Close (MOC) orders for the deltas, after a
     paper-account check and a typed confirmation.

USAGE
    python3 execute_rebalance.py                # dry run on CACHED data
    python3 execute_rebalance.py --refresh      # dry run on FRESH data (do this on rebalance day)
    python3 execute_rebalance.py --refresh --live   # actually place the MOC orders

MOC orders fill in the closing auction, matching the backtest's "trade at the
next day's close". IBKR must receive them before ~15:50 ET; the script warns
you if you're past the cutoff.
"""
import argparse
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# strategy_lib lives one folder up (strategy/). Add it to the path so the locked
# model code is imported, never copied.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import strategy_lib as S                                      # noqa: E402
from ib_async import IB, Stock, Order                         # noqa: E402
from ib_config import HOST, PORT, CLIENT_ID, REQUIRE_PAPER_ACCOUNT  # noqa: E402

MOC_CUTOFF = (15, 50)          # ET hour, minute -- IBKR stops accepting MOC after this
SINGLE_NAME_ABORT = 0.90       # refuse a live order bigger than 90% of NLV (fat-finger guard)

# Size the book off slightly less than net liquidation so the account never has
# to borrow to fill its own orders.
#
# Why this is needed at all: targeting 100% of NLV means target cash is exactly
# zero, so ANY overshoot borrows. Two things overshoot. Whole-share rounding is
# worth a few hundred dollars. Worse, shares are sized off the last close but
# MOC fills at the NEXT close, so an overnight gap changes what the order
# actually costs -- and no buffer can be proven sufficient against that, because
# the fill price is unknowable when the order is sent. 0.5% of a ~750k book is
# ~3,750 USD of headroom, which covers rounding and a normal overnight move.
#
# The cost of holding it back is trivial: 0.5% uninvested against a ~13.6%/yr
# book is under 0.07%/yr, versus ~1.6%/yr for financing the book with a loan.
CASH_BUFFER_PCT = 0.5


# ---- 1. the strategy's target book (same math as signals.py) -----------------------
def compute_target(refresh):
    DI = S.get_data(refresh=refresh)
    ps = S.style_weight_path(DI)
    p6 = S.sector_weight_path(DI, ps)
    t = S.latest_formation(DI, ps, p6)   # refuses stub months / NaN hurdles
    tgt_raw = S.combine_paths([(ps, S.W_STYLE), (p6, S.W_SECTOR)])[t]
    tgt = S.throttle_target(DI, tgt_raw, t, S.BOOK_VT)
    prices = DI["close"].ffill().iloc[-1]           # latest close per ticker, for sizing
    data_through = DI["close"].index.max().date()
    return t, tgt, prices, data_through


def moc_time_warning():
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return f"  NOTE: it is {now:%A} -- US market is closed; MOC orders queue but won't fill today."
    cutoff = now.replace(hour=MOC_CUTOFF[0], minute=MOC_CUTOFF[1], second=0, microsecond=0)
    if now < now.replace(hour=9, minute=30, second=0, microsecond=0):
        return f"  NOTE: it is {now:%H:%M} ET -- before the open. MOC orders will queue for today's close."
    if now > cutoff:
        return (f"  WARNING: it is {now:%H:%M} ET -- past the ~{MOC_CUTOFF[0]}:{MOC_CUTOFF[1]:02d} ET "
                "MOC cutoff. IBKR will likely REJECT these MOC orders. Wait for tomorrow.")
    return f"  Time check OK: {now:%H:%M} ET, before the {MOC_CUTOFF[0]}:{MOC_CUTOFF[1]:02d} ET MOC cutoff."


def cash_by_currency(ib, acct):
    """Per-currency cash balances (mirrors the helper in convert_cad_to_usd.py).

    accountSummary()'s TotalCashValue is the NETTED figure across currencies, so
    a big positive CAD balance sitting next to a big negative USD balance shows
    up as a small, healthy-looking number. The per-currency breakdown is the only
    way to see a margin loan, and it lives under IBKR's '$LEDGER-CashBalance'
    tags -- note the '$LEDGER-' prefix; the bare 'CashBalance' tag returns
    nothing for this field."""
    out = {}
    for v in ib.accountValues(acct):
        if v.tag == "$LEDGER-CashBalance" and v.currency and v.currency != "BASE":
            out[v.currency] = float(v.value)
    return out


def fx_base_to_usd(base_ccy):
    """USD per 1 unit of the account's base currency (1.0 if already USD).
    The ETFs price in USD but a CAD account reports its value in CAD, so we
    convert the account value to USD before sizing. Rate from yfinance, same
    source the strategy already uses."""
    if base_ccy == "USD":
        return 1.0
    import yfinance as yf
    raw = yf.download(f"USD{base_ccy}=X", period="5d", progress=False, auto_adjust=True)
    close = raw.xs("Close", axis=1, level=0) if hasattr(raw.columns, "levels") else raw["Close"]
    ccy_per_usd = float(close.squeeze().dropna().iloc[-1])   # e.g. USDCAD ~ 1.37 CAD per USD
    return 1.0 / ccy_per_usd                                 # -> USD per CAD ~ 0.73


# ---- main --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Rebalance the IBKR paper book to the strategy's target.")
    ap.add_argument("--refresh", action="store_true", help="re-download yfinance/FRED before computing (use on rebalance day)")
    ap.add_argument("--live", action="store_true", help="actually place MOC orders (default is dry run)")
    ap.add_argument("--yes", action="store_true", help="skip the typed confirmation in --live mode")
    ap.add_argument("--allow-live-account", action="store_true", help="override the paper-account safety check (DANGER)")
    ap.add_argument("--buffer-pct", type=float, default=CASH_BUFFER_PCT,
                    help=f"%% of account value held back as cash so orders never borrow (default {CASH_BUFFER_PCT})")
    args = ap.parse_args()

    # --- strategy side ---
    t, tgt, prices, data_through = compute_target(args.refresh)
    print(f"\nSignal month-end: {t.date()}   (price data through {data_through})")
    if not args.refresh:
        print("  !! using CACHED prices -- add --refresh on the real rebalance day")

    # target shares from target weights (need NLV first, so connect now)
    ib = IB()
    print(f"\nConnecting to IBKR at {HOST}:{PORT} ...")
    try:
        ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=15)
    except Exception as e:
        print("  CONNECTION FAILED:", repr(e), "\n  Run ib_test.py first and fix setup (see README.md).")
        return

    acct = ib.managedAccounts()[0]
    is_paper = acct.startswith("D")
    print(f"  Account: {acct}  ({'paper' if is_paper else 'NOT PAPER'})")
    if REQUIRE_PAPER_ACCOUNT and not is_paper and not args.allow_live_account:
        print("  ABORT: this is not a paper account and --allow-live-account was not given.")
        ib.disconnect()
        return

    summary_items = ib.accountSummary(acct)
    summary = {v.tag: v.value for v in summary_items}
    base_ccy = next((v.currency for v in summary_items if v.tag == "NetLiquidation"), "USD")
    nlv_base = float(summary.get("NetLiquidation", 0.0))
    cash_base = float(summary.get("TotalCashValue", 0.0))
    if nlv_base <= 0:
        print("  ABORT: could not read a positive account value.")
        ib.disconnect()
        return

    # ETFs price in USD; the account totals are in the base currency. Convert the
    # account value to USD so target weights map to correct USD share counts.
    fx = fx_base_to_usd(base_ccy)          # USD per 1 unit of base currency
    nlv = nlv_base * fx                     # <-- everything downstream sizes off this (USD)
    if base_ccy == "USD":
        print(f"  Net liquidation: ${nlv:,.2f} USD   cash: ${cash_base:,.2f}")
    else:
        print(f"  Net liquidation: {nlv_base:,.2f} {base_ccy}  ->  ${nlv:,.2f} USD"
              f"   (FX {base_ccy}->USD = {fx:.4f})")
        print(f"  Sizing the book off ${nlv:,.2f} USD.")

    # Per-currency cash. This used to be printed only in the USD branch, which is
    # how a 710k USD margin loan sat on the account unnoticed for two weeks: the
    # netted TotalCashValue looked fine and nothing ever showed the two sides.
    cash_ccy = cash_by_currency(ib, acct)
    usd_cash = cash_ccy.get("USD", 0.0)
    if cash_ccy:
        print("  Cash by currency: " +
              "   ".join(f"{c} {v:,.2f}" for c, v in sorted(cash_ccy.items())))
    if usd_cash < 0:
        print(f"\n  !! WARNING: USD cash is {usd_cash:,.2f}. This book is being funded by an")
        print( "     IBKR margin loan rather than by your own cash, which costs the USD/CAD")
        print( "     interest differential (~1.6%/yr when this was last measured) and is not")
        print( "     modelled anywhere in the backtest.")
        print( "     Fix: python3 convert_cad_to_usd.py --live")

    # Hold back a sliver so the orders can be paid for out of cash + sale
    # proceeds rather than out of an IBKR loan (see CASH_BUFFER_PCT).
    nlv_investable = nlv * (1.0 - args.buffer_pct / 100.0)
    if args.buffer_pct:
        print(f"  Sizing target book off ${nlv_investable:,.2f} USD "
              f"({100 - args.buffer_pct:g}% of NLV; {args.buffer_pct:g}% held back as cash)")

    current = {p.contract.symbol: int(p.position) for p in ib.positions(acct)
               if p.contract.secType == "STK"}

    # --- build the order list ---
    target_shares, target_pct = {}, {}
    for tkr, w in tgt.items():
        if tkr == S.CASH:                       # CASH weight = leave uninvested, no order
            continue
        px = float(prices.get(tkr, float("nan")))
        if px != px or px <= 0:                 # NaN or bad price
            print(f"  WARNING: no usable price for {tkr}; skipping it.")
            continue
        target_shares[tkr] = int(round(w * nlv_investable / px))
        target_pct[tkr] = w

    rows, abort_flags = [], []
    for tkr in sorted(set(target_shares) | set(current)):
        tsh = target_shares.get(tkr, 0)
        csh = current.get(tkr, 0)
        delta = tsh - csh
        if delta == 0:
            continue
        px = float(prices.get(tkr, float("nan")))
        notional = abs(delta) * px
        action = "BUY" if delta > 0 else "SELL"
        rows.append((tkr, target_pct.get(tkr, 0.0), csh, tsh, delta, action, notional, px))
        if notional > SINGLE_NAME_ABORT * nlv:
            abort_flags.append(tkr)

    # sells first so cash is freed before buys
    rows.sort(key=lambda r: (r[4] > 0, r[0]))

    # Hard funding backstop. The buffer above should make this unnecessary, but
    # if the buys still exceed what cash + sale proceeds can pay for, scale every
    # buy down proportionally rather than letting IBKR quietly lend the
    # difference. MOC means buys and sells fill in the same auction and settle
    # together, so sale proceeds are available to the purchases.
    buys  = sum(r[6] for r in rows if r[5] == "BUY")
    sells = sum(r[6] for r in rows if r[5] == "SELL")
    # max(0, ...): a pre-existing debit is not spendable cash. Without the clamp
    # an existing loan makes "available" negative, which is not a meaningful
    # amount of money to size against.
    available = max(0.0, usd_cash) + sells
    trim_note = None
    if buys > available:
        factor = max(0.0, available / buys) if buys else 0.0
        trimmed = []
        for tkr, pct, csh, tsh, delta, action, notional, px in rows:
            if action == "BUY":
                delta = int(delta * factor)          # int() floors toward zero
                if delta == 0:
                    continue
                tsh, notional = csh + delta, abs(delta) * px
            trimmed.append((tkr, pct, csh, tsh, delta, action, notional, px))
        trim_note = (f"buys scaled to {factor:.1%} of target "
                     f"(${buys:,.0f} wanted, ${available:,.0f} available) so nothing is borrowed")
        rows = trimmed
        buys = sum(r[6] for r in rows if r[5] == "BUY")

    print("\nTARGET BOOK vs CURRENT  (MOC orders to place):")
    print(f"  {'SYM':<6}{'TGT%':>7}{'HAVE':>8}{'WANT':>8}{'DELTA':>8}  {'SIDE':<5}{'~NOTIONAL':>13}")
    if not rows:
        print("  (all orders cancelled by the funding guard -- see below)" if trim_note
              else "  (already at target -- nothing to trade)")
    for tkr, pct, csh, tsh, delta, action, notional, px in rows:
        print(f"  {tkr:<6}{pct:>6.0%}{csh:>8}{tsh:>8}{delta:>+8}  {action:<5}{notional:>13,.0f}")
    cash_pct = float(tgt.get(S.CASH, 0.0))
    if cash_pct > 1e-6:
        print(f"  (+ {cash_pct:.0%} left in cash by design)")

    # Funding report. Approximate: the real fill prices are not known until the
    # closing auction, so an unusually large overnight gap can still move this.
    projected_usd = usd_cash + sells - buys
    print(f"\n  Funding: USD cash {usd_cash:,.0f} + sells {sells:,.0f} - buys {buys:,.0f}"
          f"  ->  {projected_usd:,.0f}")
    if trim_note:
        print(f"  !! {trim_note}")
    if projected_usd < 0:
        print(f"  !! Still ~{-projected_usd:,.0f} USD short. The shortfall is the existing")
        print( "     margin loan, not these orders. Run convert_cad_to_usd.py --live first.")
    else:
        print("     Fully funded from USD cash and sale proceeds. Nothing borrowed.")

    print("\n" + moc_time_warning())

    if abort_flags:
        print(f"\n  ABORT: order(s) for {abort_flags} exceed {SINGLE_NAME_ABORT:.0%} of NLV -- looks wrong. "
              "Check prices/weights before trading.")
        ib.disconnect()
        return

    if args.live and usd_cash < 0:
        print(f"\n  ABORT: the account is carrying a {-usd_cash:,.2f} USD margin loan. Buying more"
              "\n  would deepen it. Clear it first, then re-run:"
              "\n      python3 convert_cad_to_usd.py --live")
        ib.disconnect()
        return

    if not args.live:
        print("\n  DRY RUN -- no orders placed. Re-run with --live to transmit.")
        ib.disconnect()
        return

    if not rows:
        ib.disconnect()
        return

    # --- live path ---
    if not args.yes:
        reply = input(f"\n  Place {len(rows)} MOC orders on {acct}? Type 'yes' to confirm: ").strip()
        if reply != "yes":
            print("  Cancelled.")
            ib.disconnect()
            return

    print("\n  Placing orders (sells first)...")
    trades = []
    for tkr, pct, csh, tsh, delta, action, notional, px in rows:
        contract = Stock(tkr, "SMART", "USD")
        ib.qualifyContracts(contract)
        order = Order(action=action, totalQuantity=abs(delta),
                      orderType="MOC", tif="DAY", transmit=True)
        trades.append((tkr, ib.placeOrder(contract, order)))
    ib.sleep(2)
    print(f"  {'SYM':<6}{'ORDER STATUS':>16}")
    for tkr, tr in trades:
        print(f"  {tkr:<6}{tr.orderStatus.status:>16}")
    print("\n  Done. Watch fills in TWS at the close. Re-run ib_test.py after the close to confirm positions.")
    ib.disconnect()


if __name__ == "__main__":
    main()
