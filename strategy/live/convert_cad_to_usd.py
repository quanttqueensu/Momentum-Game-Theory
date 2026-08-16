"""
convert_cad_to_usd.py -- one-off currency conversion, CAD -> USD.

WHY THIS EXISTS
    The account is CAD-denominated but every ETF the strategy trades prices in
    USD. IBKR does NOT auto-convert: buying a USD stock with a CAD balance
    leaves the CAD untouched and opens a USD margin loan instead (a negative USD
    cash balance). You then pay USD debit interest on that loan while earning a
    lower CAD credit rate on the idle CAD -- the interest differential, which is
    the standard cost of a money-market currency hedge.

    Converting the CAD to USD clears the loan, stops the interest, and leaves the
    account holding USD assets funded by USD -- which is the arrangement the
    backtest assumes (it is computed entirely in USD; there is no FX anywhere in
    strategy_lib.py).

    Tradeoff, stated plainly: after converting, the account's USD value is stable
    and its CAD value moves with USDCAD. Before converting it was the other way
    round. You are choosing which currency you are stable in, not removing risk.

WHAT IT DOES NOT DO
    It does not touch a single stock position. A currency conversion swaps one
    asset for another of equal value, so net liquidation should not move beyond
    commission and spread. If it moves materially, something is wrong -- stop.

USAGE
    python3 convert_cad_to_usd.py                  # DRY RUN, prints the trade
    python3 convert_cad_to_usd.py --live           # actually convert ALL the CAD
    python3 convert_cad_to_usd.py --amount-cad 500000 --live   # a specific amount

Same safety model as execute_rebalance.py: dry run by default, paper-account
guard, and a typed confirmation before anything transmits.
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ib_async import IB, Forex, Order                              # noqa: E402
from ib_config import HOST, PORT, CLIENT_ID, REQUIRE_PAPER_ACCOUNT  # noqa: E402

# IDEALPRO will not take FX orders below roughly this size.
IDEALPRO_MIN_USD = 25_000
# Default is to convert the WHOLE CAD balance. The sizing rate comes from
# yfinance and the fill rate comes from IDEALPRO, so an adverse tick between the
# two can leave a small CAD debit instead of a small CAD credit. That is
# harmless (a few thousand CAD at ~1.5% is a few dollars a year), but
# --buffer-pct will hold some back if you would rather it never happen.
SAFETY_BUFFER = 0.0


def usdcad_rate():
    """CAD per 1 USD, from yfinance -- the same source the rest of the project
    uses, so no IBKR market-data subscription is needed."""
    import yfinance as yf
    raw = yf.download("USDCAD=X", period="5d", progress=False, auto_adjust=True)
    close = raw.xs("Close", axis=1, level=0) if hasattr(raw.columns, "levels") else raw["Close"]
    return float(close.squeeze().dropna().iloc[-1])


def _ledger(ib, acct, field):
    """Per-currency ledger values. accountSummary() only reports one
    base-currency total; the per-currency breakdown lives in accountValues()
    under IBKR's '$LEDGER-<field>' tags. The 'BASE' row is that same total again
    restated in the base currency, so it is excluded.

    Note the tag really is '$LEDGER-CashBalance', not 'CashBalance' -- the plain
    tag exists for some fields but not this one, and silently returns nothing."""
    out = {}
    for v in ib.accountValues(acct):
        if v.tag == f"$LEDGER-{field}" and v.currency and v.currency != "BASE":
            out[v.currency] = float(v.value)
    return out


def cash_by_currency(ib, acct):
    return _ledger(ib, acct, "CashBalance")


def accrued_by_currency(ib, acct):
    """Interest accrued but not yet posted. Negative on a borrowed balance."""
    return _ledger(ib, acct, "AccruedCash")


def main():
    ap = argparse.ArgumentParser(description="Convert CAD to USD on the IBKR account.")
    ap.add_argument("--live", action="store_true", help="actually place the FX order (default is a dry run)")
    ap.add_argument("--amount-cad", type=float, default=None,
                    help="CAD to convert (default: the entire CAD balance)")
    ap.add_argument("--buffer-pct", type=float, default=SAFETY_BUFFER * 100,
                    help="percent of the CAD balance to hold back (default 0, convert it all)")
    ap.add_argument("--yes", action="store_true", help="skip the typed confirmation")
    ap.add_argument("--allow-live-account", action="store_true", help="override the paper guard (DANGER)")
    args = ap.parse_args()

    ib = IB()
    print(f"\nConnecting to IBKR at {HOST}:{PORT} ...")
    try:
        ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=15)
    except Exception as e:
        print("  CONNECTION FAILED:", repr(e))
        print("  Run ib_test.py first and fix the setup (see README.md).")
        return

    try:
        acct = ib.managedAccounts()[0]
        is_paper = acct.startswith("D")
        print(f"  Account: {acct}  ({'paper' if is_paper else 'NOT PAPER'})")
        if REQUIRE_PAPER_ACCOUNT and not is_paper and not args.allow_live_account:
            print("  ABORT: not a paper account and --allow-live-account was not given.")
            return

        summary = {v.tag: v for v in ib.accountSummary(acct)}
        nlv = float(summary["NetLiquidation"].value)
        base = summary["NetLiquidation"].currency
        cash = cash_by_currency(ib, acct)
        cad, usd = cash.get("CAD", 0.0), cash.get("USD", 0.0)

        accrued = accrued_by_currency(ib, acct)
        print(f"\nBEFORE")
        print(f"  Net liquidation : {nlv:>14,.2f} {base}")
        print(f"  CAD cash        : {cad:>14,.2f}")
        print(f"  USD cash        : {usd:>14,.2f}" + ("   <- the margin loan" if usd < 0 else ""))
        if accrued:
            print("  Interest accrued but not yet posted:")
            for ccy, amt in sorted(accrued.items()):
                note = "  <- cost of the USD loan" if amt < 0 else "  <- earned on the CAD"
                print(f"    {ccy:<4}{amt:>14,.2f}{note}")

        if cad <= 0:
            print("\n  Nothing to do: no positive CAD balance.")
            return

        rate = usdcad_rate()
        cad_to_convert = (args.amount_cad if args.amount_cad is not None
                          else cad * (1 - args.buffer_pct / 100.0))
        if cad_to_convert > cad:
            print(f"\n  ABORT: asked to convert {cad_to_convert:,.2f} CAD but only {cad:,.2f} is available.")
            return
        qty_usd = math.floor(cad_to_convert / rate)

        print(f"\nTRADE")
        print(f"  BUY  {qty_usd:,} USD.CAD on IDEALPRO   (rate {rate:.4f} CAD per USD)")
        print(f"  Buys  {qty_usd:>14,} USD")
        print(f"  Costs {qty_usd * rate:>14,.2f} CAD")

        print(f"\nEXPECTED AFTER")
        print(f"  CAD cash        : {cad - qty_usd * rate:>14,.2f}")
        print(f"  USD cash        : {usd + qty_usd:>14,.2f}" +
              ("   <- loan cleared" if usd < 0 and usd + qty_usd >= 0 else ""))
        print(f"  Net liquidation : ~unchanged. A conversion swaps equal value; only")
        print(f"                    commission and spread should move it (a few dollars).")
        print(f"  Stock positions : untouched. This order does not trade any equity.")

        if qty_usd < IDEALPRO_MIN_USD:
            print(f"\n  ABORT: {qty_usd:,} USD is below IDEALPRO's ~{IDEALPRO_MIN_USD:,} minimum.")
            return

        if not args.live:
            print("\n  DRY RUN -- nothing placed. Re-run with --live to convert.")
            return

        if not args.yes:
            reply = input(f"\n  Convert {qty_usd * rate:,.2f} CAD into {qty_usd:,} USD on {acct}? "
                          "Type 'yes' to confirm: ").strip()
            if reply != "yes":
                print("  Cancelled.")
                return

        contract = Forex("USDCAD")          # BUY this pair = buy USD, pay CAD
        ib.qualifyContracts(contract)
        order = Order(action="BUY", totalQuantity=qty_usd, orderType="MKT", transmit=True)
        trade = ib.placeOrder(contract, order)

        print("\n  Order sent. Waiting for fill ...")
        for _ in range(20):                 # FX on IDEALPRO fills near-instantly
            ib.sleep(0.5)
            if trade.orderStatus.status in ("Filled", "Cancelled", "Inactive", "ApiCancelled"):
                break
        print(f"  Status: {trade.orderStatus.status}   filled {trade.orderStatus.filled:,.0f}"
              f" @ {trade.orderStatus.avgFillPrice or float('nan'):.4f}")

        ib.sleep(1)
        cash2 = cash_by_currency(ib, acct)
        summary2 = {v.tag: v for v in ib.accountSummary(acct)}
        nlv2 = float(summary2["NetLiquidation"].value)
        print(f"\nACTUAL AFTER")
        print(f"  CAD cash        : {cash2.get('CAD', 0.0):>14,.2f}")
        print(f"  USD cash        : {cash2.get('USD', 0.0):>14,.2f}")
        print(f"  Net liquidation : {nlv2:>14,.2f} {summary2['NetLiquidation'].currency}"
              f"   (was {nlv:,.2f}, change {nlv2 - nlv:+,.2f})")
        if abs(nlv2 - nlv) > 0.01 * abs(nlv):
            print("  !! Net liquidation moved more than 1%. That should NOT happen on a")
            print("     currency conversion. Stop and check before doing anything else.")
        print("\n  Done. Run ib_test.py to confirm positions are unchanged.")
    finally:
        ib.disconnect()


if __name__ == "__main__":
    main()
