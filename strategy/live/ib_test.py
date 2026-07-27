"""
ib_test.py -- the "prove the connection works" script. READ-ONLY: it connects,
prints who you are and what you hold, and disconnects. It places NO orders.

This is the IBKR equivalent of the data-source proof cells in
connectivity_notebook.ipynb. Run it FIRST, before execute_rebalance.py, to
confirm TWS is configured correctly.

    python3 ib_test.py

If it fails, the error message tells you which setup step to fix (see README.md).
"""
from ib_async import IB
from ib_config import HOST, PORT, CLIENT_ID


def money(x):
    try:
        return f"${float(x):,.2f}"
    except (TypeError, ValueError):
        return str(x)


def main():
    ib = IB()
    print(f"Connecting to the IBKR connector at {HOST}:{PORT} (clientId={CLIENT_ID}) ...")
    try:
        ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=15)
    except Exception as e:
        print("\n  CONNECTION FAILED:", repr(e))
        print("""
  Checklist (see README.md, section 'Configure TWS'):
    1. Is TWS running and logged into your PAPER account?
    2. In TWS: File > Global Configuration > API > Settings
         - 'Enable ActiveX and Socket Clients' is CHECKED
         - Socket port is 7497 (matches PORT in ib_config.py)
         - '127.0.0.1' is in the Trusted IPs list
    3. First connection each session pops a blue 'Accept incoming
       connection' dialog IN TWS -- click Accept (or pre-trust the IP).
""")
        return

    accts = ib.managedAccounts()
    print("\n  Connected. Managed account(s):", ", ".join(accts))

    for a in accts:
        tag = "PAPER (good)" if a.startswith("D") else "*** NOT a paper account -- be careful ***"
        print(f"    {a}  ->  {tag}")

    acct = accts[0]
    summary = {v.tag: v.value for v in ib.accountSummary(acct)}
    print("\n  Account snapshot:")
    for tag in ("NetLiquidation", "TotalCashValue", "AvailableFunds", "BuyingPower"):
        if tag in summary:
            print(f"    {tag:16} {money(summary[tag])}")

    positions = [p for p in ib.positions(acct)]
    print(f"\n  Current positions: {len(positions)}")
    if positions:
        print(f"    {'SYMBOL':<8}{'SHARES':>10}{'AVG COST':>14}")
        for p in sorted(positions, key=lambda p: p.contract.symbol):
            print(f"    {p.contract.symbol:<8}{p.position:>10.0f}{money(p.avgCost):>14}")
    else:
        print("    (none -- fresh paper account)")

    ib.disconnect()
    print("\n  Disconnected cleanly. The pipe works. Next: python3 execute_rebalance.py")


if __name__ == "__main__":
    main()
