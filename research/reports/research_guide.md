# Research guide: the 65% style sleeve

A plain-language guide to the `research/` folder: what the style sleeve does, what its 7 ETFs are, and what each
experiment tested and found. Written 2026-11-26.

**Contents**

1. [How the style sleeve works](#1-how-the-style-sleeve-works)
2. [The 7 ETFs: size, style and region](#2-the-7-etfs-size-style-and-region)
3. [The experiments](#3-the-experiments)
4. [The common thread](#4-the-common-thread)
5. [Glossary](#5-glossary)

---

## 1. How the style sleeve works

The strategy splits money into a **65% style sleeve** and a **35% sector sleeve**. All the experiments here are about
the style sleeve unless noted.

Every month the style sleeve:

1. **Scores** the 7 style ETFs. The score is the average of each ETF's 3-, 6- and 12-month return (skipping the most
   recent month), each turned into a z-score, i.e. compared with the other 6 ETFs.
2. **Picks the #1 ETF** and puts 100% of the sleeve in it.
3. **Checks the T-bill hurdle.** The pick must have a 6- or 12-month return above Treasury bills. If it fails, the
   money goes to **IEF** (intermediate Treasuries), or to **cash** if bonds are weak too.

Every experiment changes one of these pieces, or measures how much one of them helps.

---

## 2. The 7 ETFs: size, style and region

The 7 ETFs are combinations of three standard ways of splitting the stock market.

### Small vs large: company size

Size is measured by market value (share price × number of shares).

| | Examples | ETF |
|---|---|---|
| **Large** | Apple, Microsoft, JPMorgan: the 500 biggest US companies | **SPY** (S&P 500) |
| **Small** | About 2,000 smaller US companies: regional banks, small manufacturers, biotech | **IWM** (Russell 2000) |

Small companies are riskier and swing more. They tend to do well coming out of recessions and badly when interest rates
rise or the economy weakens.

### Value vs growth: how the company is priced

Both groups are mostly large US companies, split by how expensive the stock is relative to what the company earns or owns.

| | What it means | Examples | ETF |
|---|---|---|---|
| **Growth** | Expensive relative to current profits, because investors expect fast growth | Nvidia, Tesla, Amazon, most tech | **IWF** (Russell 1000 Growth), **QQQ** (Nasdaq-100, mostly tech) |
| **Value** | Cheap relative to profits or assets; slower-growing, "boring" businesses | Banks, oil, utilities, industrials, healthcare | **IWD** (Russell 1000 Value) |

Growth tends to lead when investors are optimistic and interest rates are low (2010-2021, the AI boom). Value tends to
lead when rates rise or optimism fades (2000-2006, 2022).

### International vs US: where the companies are

| | What it means | ETF |
|---|---|---|
| **US** | American companies | SPY, QQQ, IWM, IWF, IWD |
| **Developed international** | Europe, Japan, UK, Australia, Canada | **EFA** |
| **Emerging markets** | China, India, Taiwan, Brazil, South Korea, Mexico | **EEM** |

The US and foreign markets take turns leading over long stretches: international led in 2002-2007, the US in
2010-2024. A falling US dollar boosts foreign returns for a US investor.

### Why this matters for the research

- The 7 ETFs are really three choices: **size** (SPY vs IWM), **style** (IWD vs IWF/QQQ) and **region** (US vs EFA vs EEM).
- They all hold stocks, so they mostly move together. Over 2004-2026 their average correlation is **0.81**, and one
  common factor (the stock market) explains **84%** of their movement. They behave like about **1.4 independent bets**.
- The differences between them are a small slice on top of the market, and that slice is what the momentum score tries
  to predict. This is the main reason the score is hard to improve.

---

## 3. The experiments

All tests compare against production on 2002-2018 data and 4 rebalance days (0, 5, 10 and 15 trading days before
month-end), unless noted. **2019-2026** was kept aside as an out-of-sample check.

### Group 1: understanding the current signal (measurements, not new strategies)

#### Score predictive power
`scripts/score_predictive_power.py` · tables in `tables/score_predictive_power/`

- **Question:** does the score predict next month's returns?
- **How:** each month, compare the score with the next month's return. Ranking: do higher-ranked ETFs do better? Trend:
  do ETFs that beat T-bills keep beating them?
- **Result:** the #1 ETF beats the average style ETF by about **4%/yr**, but ranks 2-7 have no order (#2 did slightly
  worse than average).
- **Takeaway:** the score finds a leader and can't rank the rest.

#### Sleeve split
`scripts/sleeve_split.py` · `results/sleeve_split_insample.png`

- **Question:** where does the sleeve's edge come from, the ranking or the hurdle?
- **How:** five versions: production; ranking only (always invested); hurdle with a random passing ETF; hurdle with all
  passing ETFs equally weighted; neither (equal-weight all 7).
- **Result:** the **hurdle drives most of the Sharpe ratio**, because it gets the sleeve out of falling markets. The
  ranking adds return by concentrating in the leader; a random passing ETF did much worse.
- **Takeaway:** "get out when trends turn down" 

### Group 2: changing the score

#### Damped returns
`scripts/damped_returns_test.py` · `results/damped_returns_insample.png`

- **Question:** do extreme months distort the score?
- **How:** cap each monthly return at ±2 standard deviations of the ETF's own recent volatility before scoring.
- **Result:** no improvement.
- **Takeaway:** big months are usually real momentum, not noise.

#### Soft-damped z-scores
`scripts/soft_damp_zscore_test.py` · `results/soft_damp_zscore_insample.png`

- **Question:** same worry, handled at the score level.
- **How:** squeeze large z-scores with `C·tanh(z/C)` (C = 1.5) before averaging the three lookbacks.
- **Result:** slightly worse than production.
- **Takeaway:** an ETF far ahead of the others is usually the right pick; shrinking its lead hurts.

#### High-score penalty
`scripts/high_score_penalty_test.py` · `results/high_score_penalty_insample.png`

- **Question:** should an ETF that is extremely far ahead be pulled back in case it's overextended?
- **How:** `score − 0.5 × (score − 1.0)` for any score above 1.0.
- **Result:** **no change at all**. The lines on the chart are identical.
- **Why:** with a penalty below 1, the leader is pulled back but stays the leader. The strategy only uses rank order, so
  the rule can never change a pick.

#### Factor momentum
`scripts/factor_momentum_test.py` · `results/factor_momentum_insample.png`, `results/factor_momentum_french.png`

- **Question:** instead of ranking the 7 ETFs, follow the trend of the size, style and region splits (section 2).
- **How:**
  - Stage A: on academic data from 1963-1999, does trend-following each split work?
  - Stage B: on the ETFs, a decision tree:
    1. If international beats US recently, pick EFA or EEM.
    2. Else, if small beats large, pick IWM.
    3. Else, if growth beats value, pick QQQ or IWF; otherwise IWD.
- **Result:**
  - It worked before 2000 but faded afterwards. On the ETFs it cost about 0.10 Sharpe.
  - The 6-month version (purple line) looks best on the chart, but the chart shows one rebalance day. Averaged over all
    four it only tied production, and it lost on 2019-2026.
- **Takeaway:** factor trends stopped working around 2000. A chart from a single rebalance day can mislead.

### Group 3: changing how the money is allocated

#### Equal-weight hurdle holdout
`scripts/ew_hurdle_holdout.py` · `results/ew_hurdle_holdout.png`

- **Question:** sleeve split found that equal-weighting every ETF passing the hurdle looked better in-sample. Does it hold
  on new data?
- **How:** one-time test on 2019-2026.
- **Result:** **failed**. Sharpe 0.73 vs 0.86, CAGR 11.1% vs 14.7%, drawdown no smaller.
- **Takeaway:** its in-sample edge was mostly production's bad luck in 2008, and spreading the money gave up the leader's return.

#### Breadth sizing
`scripts/breadth_sizing_test.py` · `results/breadth_sizing_insample.png`, `breadth_sizing_holdout.png`, `breadth_sizing_offsets.png`

- **Question:** hold less of the pick when only a few style ETFs are still trending up (an early warning that the market
  is weakening)?
- **How:** count the share of the 7 ETFs passing the hurdle and hold that share of the sleeve in the pick, the rest in
  IEF or cash. For example, 4 of 7 passing means 57% in the pick.
- **Result:**

  | | Sharpe | CAGR | Max drawdown |
  |---|---|---|---|
  | 2002-2018: production | 0.763 | 11.17% | -26.2% |
  | 2002-2018: breadth sizing | 0.886 | 11.92% | -15.5% |
  | 2019-2026: production | 0.859 | 14.69% | -16.8% |
  | 2019-2026: breadth sizing | 0.745 | 12.00% | -15.2% |

  - On 2019-2026 it lost on **all 21** possible rebalance days.
  - On 1928-2018 US history it was no better than just holding about 80% of production.
- **Why:** after a sell-off, breadth stays low for months while prices are already recovering, so it misses rebounds.
  Its in-sample win came mostly from production's unlucky 2008 rebalance days (see `breadth_sizing_offsets.png`).

#### Switch band (T2)
`scripts/switch_band_test.py` · `results/switch_band_insample.png`, `switch_band_holdout.png`

- **Question:** can we trade less without hurting results?
- **How:** switch to a new #1 only if its score beats the current holding's score by **more than 0.5**. Near-ties keep
  the current ETF. Exits via the hurdle are unchanged.
- **Example:** you hold IWF at 1.05. QQQ becomes #1 at 1.20 (gap 0.15): keep IWF. QQQ at 1.80 (gap 0.75): switch.
- **Result: passed every test.**

  | | Sharpe | CAGR | Max drawdown | Style switches/yr |
  |---|---|---|---|---|
  | 2002-2018: production | 0.763 | 11.17% | -26.2% | 3.87 |
  | 2002-2018: switch band | 0.762 | 11.26% | -26.2% | 2.36 (-39%) |
  | 2019-2026: production | 0.859 | 14.69% | -16.8% | 4.03 |
  | 2019-2026: switch band | 0.869 | 14.92% | -17.1% | 2.16 (-46%) |

  - It also held up on 1964-2018 US data (+0.03 pp/yr).
  - It saves about **20 bps/yr** in trading costs at 10 bps per trade, plus fewer taxable trades.
- **Note:** in a replay of the dot-com crash it stayed in tech about 3 months longer than production.
- **Why it works:** the score can't tell near-tied ETFs apart (see *Score predictive power*), so switching on near-ties
  was paying costs to chase noise.

### Group 4: the sector sleeve

#### Sector signal
`scripts/sector_signal_research.py` · `results/sector_signal_insample.png` · `reports/sector_signal_research.md`

- **Question:** can a better score improve the 35% sector sleeve (top 4 of 11 sector ETFs)?
- **How:** test **residual momentum** (each sector's return after removing what the S&P 500 explains) and
  **volatility-adjusted momentum** (return ÷ volatility).
- **Result:** noise, no improvement.

---

## 4. The common thread

| What we tried | Result | Why |
|---|---|---|
| Make the score smarter (damping, penalty, factor trends, sector signals) | Failed | The ETFs move together, so there is little to rank |
| Spread or shrink the bet (equal weight, breadth sizing) | Good in-sample, failed on new data | Their edge was production's 2008 bad luck; holding less misses rebounds |
| Stop trading on noise (switch band) | **Passed** | Near-tie switches were costs, not information |

**In short:** the score finds a leader, the hurdle protects in slow bear markets, and the remaining gains come from
trading the signal more sensibly, not from a cleverer signal.

