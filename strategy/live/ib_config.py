"""
ib_config.py -- one place for the Interactive Brokers connection settings.

Your Python script does NOT talk to IBKR's servers directly. It talks to the
IBKR desktop connector app (TWS or IB Gateway) running on this Mac, over a
local socket. That app must be running and logged into the PAPER account, with
the API switched on, before any script here will connect. See README.md.

PORT tells the script which app / which account:
    TWS   paper : 7497      TWS   live : 7496
    Gateway paper : 4002    Gateway live : 4001

We are on TWS paper -> 7497. To switch to IB Gateway later, change PORT to 4002.
The live ports are here only so you can SEE how close 7497 (paper) is to 7496
(live). We never point at a live port in this project.
"""

HOST = "127.0.0.1"   # localhost -- the connector app runs on this same machine
PORT = 7497          # TWS paper. (IB Gateway paper = 4002)
CLIENT_ID = 17       # any integer; just has to be unique per simultaneous connection

# Safety rail: paper account numbers start with "D" (usually "DU").
# The scripts refuse to place orders on an account that doesn't, unless you
# explicitly override. Do not change this unless you know exactly why.
REQUIRE_PAPER_ACCOUNT = True
