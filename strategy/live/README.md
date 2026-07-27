# Live Execution — IBKR Paper Trading

This folder connects **The Two-Engine Book** (the locked strategy in the parent
folder) to an Interactive Brokers **paper** account, so it can trade for real
(with fake money) once a month.

## The mental model (read this first)

- **The strategy decides WHAT to hold** from yfinance/FRED data — unchanged.
  `strategy_lib.py` and `signals.py` do this. IBKR is **not** the data source.
- **IBKR is only the hands**: it tells us current positions + account value, and
  it executes the orders we hand it.
- Your script does **not** talk to IBKR's servers directly. It talks to a
  **desktop connector app** (TWS) running on this Mac, over a local socket.
  That app must be running for any script here to work. The website
  (Client Portal) can't be driven by a script — that's why TWS is required.

```
  strategy_lib (yfinance)  ->  target weights  ->  execute_rebalance.py
                                                          |  local socket 127.0.0.1:7497
                                                          v
                                                    TWS (paper login)  ->  IBKR servers
```

## Files

| File | What it is |
|---|---|
| `ib_config.py` | Connection settings (host, port, client id). Port 7497 = TWS paper. |
| `ib_test.py` | READ-ONLY connection test. Prints account + positions. Places nothing. |
| `execute_rebalance.py` | The bridge. Computes orders; dry-run by default, `--live` to trade. |

## One-time setup

### 1. Install TWS (paper)
Download **Trader Workstation** from
`interactivebrokers.com` → Trading → Platforms → Trader Workstation, and install
it. (The "IBKR Desktop" / mobile apps won't expose the API — you need TWS.)

### 2. Get your paper login
Paper accounts have their **own** username/password, separate from your main
login. In Client Portal (the website): **Settings → Account Settings → Paper
Trading Account**. Create it / note the credentials. The paper account number
starts with **`DU`**.

### 3. Log into TWS with the PAPER credentials
Launch TWS, log in with the paper username/password. The title bar should say
it's a paper/simulated account.

### 4. Turn the API on (the step everyone forgets)
In TWS: **File → Global Configuration → API → Settings**, then:
- ☑ **Enable ActiveX and Socket Clients**
- **Socket port**: `7497` (must match `PORT` in `ib_config.py`)
- ☑ Add `127.0.0.1` under **Trusted IPs** (so it won't prompt every connect)
- ☐ **Read-Only API** must be **UNCHECKED** (checked = can't place orders)
- Click **Apply / OK**.

Leave TWS running whenever you run the scripts. Note: TWS **auto-logs-out** on a
schedule — reset that under Lock and Exit → Auto Logoff if it's a nuisance.

## Install the Python library (already done on this machine)
```
pip3 install ib_async
```

## Everyday use

### Test the connection (do this first, and any time it acts up)
```
python3 ib_test.py
```
Expect: your `DU…` account, its value, and current positions. If it fails, the
error names the setup step to fix.

### The monthly rebalance
Run on the **last trading day of the month, near the close** (MOC orders must
reach IBKR before ~15:50 ET):

```
python3 execute_rebalance.py --refresh          # 1) DRY RUN on fresh data — prints the orders
python3 execute_rebalance.py --refresh --live   # 2) actually place the MOC orders
```

Always run the dry run first and read the order table. `--live` re-checks it's a
paper account and asks you to type `yes` before transmitting. Watch the fills in
TWS at the close, then `python3 ib_test.py` afterwards to confirm positions.

Flags: `--refresh` re-downloads prices (use it on rebalance day); `--live`
transmits; `--yes` skips the typed confirm; `--allow-live-account` overrides the
paper guard (don't).

## What comes from where (the "how does data work" answer)

| Need | Source |
|---|---|
| Momentum scores, the game, the throttle → target weights | yfinance + FRED (cached in `../data/`) |
| Share sizing price (weight → share count) | latest yfinance close |
| Current positions, cash, account value | IBKR (live from TWS) |
| Order execution (the fills) | IBKR MOC auction |

No IBKR **market-data subscription** is needed: signals come from yfinance and
sizing uses the last close, so the paper account works out of the box.

## Safety rails built in
- Dry-run is the default; nothing trades without `--live`.
- Refuses to trade an account whose id doesn't start with `D` (paper guard).
- Aborts if any single order exceeds 90% of account value (fat-finger guard).
- Warns if you're past the MOC cutoff or the market is closed.
- Typed `yes` confirmation before any live order.

## Not done yet (future)
- Scheduling: for now you run it by hand on rebalance day. A monthly `cron`/
  `launchd` job is a later step once you trust it.
- Fractional shares / live IBKR sizing prices: currently whole shares sized off
  the last close — fine at this account size.
