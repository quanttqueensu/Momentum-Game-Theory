import datetime as dt
import glob
import os
import pandas as pd
import io
import requests


today_str = dt.date.today().strftime("%m-%d-%Y")

df = pd.read_csv(f"current.csv")
all_tickers = set()
for tickers_str in df["tickers"]:
    all_tickers.update(tickers_str.split(","))


# Only need tickers that appeared in your backtest window
window = df[(df["date"] >= "2005-01-01") & (df["date"] <= "2024-12-31")]

all_tickers = set()
for tickers_str in window["tickers"]:
    all_tickers.update(tickers_str.split(","))

print(f"Universe size: {len(all_tickers)} unique tickers")

print(f"Total unique tickers ever in the S&P 500: {len(all_tickers)}")