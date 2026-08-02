"""
strategy_lib.py  --  the club strategy, self-contained in this folder.

THE TWO-ENGINE BOOK:

    65%  STYLE ENGINE   top-1 of {SPY, QQQ, IWM, EFA, EEM} by composite
                        momentum (3/6/12m z-scores), incumbency buffer 1;
                        held only while trailing 12m OR 6m total return
                        beats the matching T-bill return (fast re-entry);
                        otherwise hurdled IEF, else T-bill cash.
    35%  SECTOR ENGINE  top-4 of 11 iShares US sectors by CONGESTION-GAME
                        equilibrium rank: each sector's payoff is its
                        composite momentum minus a crowding tax on its
                        correlation with where the rest of the sleeve's
                        capital sits (Nash equilibrium via replicator
                        dynamics), so four winners that are one trade in
                        four wrappers get substituted, not stacked.
                        Top-6 incumbency buffer in equilibrium rank, equal
                        weights; risk-off when SPY < 231d MA into the same
                        hurdled defensive as the style engine (IEF only if
                        it beats T-bills, else cash), re-entering once
                        SPY > 126d MA (fast re-entry).
    +    ONE CRASH-ONLY VOL THROTTLE: the book is never throttled while SPY
         closes above its 126d MA (high vol in an uptrend is turbulence, not
         danger). Below it, at each monthly rebalance, if the combined target
         book's trailing-21d vol (asset returns x weights, never the
         strategy's own history) exceeds 12% ann., trim all risk positions
         pro-rata into the defensive pick. Never levered.

Everything the strategy needs lives in THIS folder.

Conventions:
  * signals on the month-end close; execution at the NEXT trading day's close
  * 10 bps per traded leg; monthly decisions only, daily accounting
  * cash earns the FRED 3m T-bill; missing quotes earn the T-bill (splice:
    AGG pre-2003, IEF pre-2002, EFA pre-2001-08, EEM pre-2003 ...)
  * no backfill: an asset is scoreable only once it has 13 months of history
  * parameters were selected on 2001-01..2018-12 (IS); treat 2019+ results
    as expectation-setting, not proof (see README disclosures)
"""
import os, io, ssl, urllib.request
import numpy as np
import pandas as pd

HERE  = os.path.dirname(os.path.abspath(__file__))
DATA  = os.path.join(HERE, "data")
CACHE_PRICES = os.path.join(DATA, "prices.parquet")
CACHE_TBILL  = os.path.join(DATA, "tbill_dgs3mo.parquet")

# ---- universes & locked parameters -------------------------------------------------
SECTORS = ["IYW", "IYF", "IYH", "IYE", "IYC", "IYZ", "IYK", "IDU", "IYM", "IYJ", "IYR"]
STYLES  = ["SPY", "QQQ", "IWM", "EFA", "EEM"]
DEFENSIVE = ["AGG", "IEF"]
ALL_TICKERS = list(dict.fromkeys(SECTORS + STYLES + DEFENSIVE))
CASH = "CASH"

W_STYLE, W_SECTOR = 0.65, 0.35
BOOK_VT     = 0.12                     # crash-only: applies below SPY's 126d MA
VOL_WINDOW  = 21                       # fast vol read (flat ridge 10-63; fast wins in crashes)
TOP_K, BUFFER_EXIT = 4, 6              # sector engine
STYLE_K, STYLE_BUFFER = 1, 1           # style engine
REGIME_EXIT_MA, REGIME_ENTER_MA = 231, 126
GAME_LAM, GAME_CORR_DAYS = 8.0, 126    # sector congestion game (played over all 11)
COST_BPS    = 10.0
PRICE_START = "1999-01-01"
IS_START, IS_END = "2001-01-01", "2018-12-31"

RISK_TICKERS = set(SECTORS + STYLES)

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:                                    # pragma: no cover
    _SSL_CTX = ssl.create_default_context()


# ---- data ---------------------------------------------------------------------------
def load_prices(refresh=False):
    if os.path.exists(CACHE_PRICES) and not refresh:
        df = pd.read_parquet(CACHE_PRICES)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df
    import yfinance as yf
    print(f"[data] downloading {len(ALL_TICKERS)} tickers from {PRICE_START} ...")
    raw = yf.download(ALL_TICKERS, start=PRICE_START, auto_adjust=True, progress=False)
    close = (raw.xs("Close", axis=1, level=0)
             if isinstance(raw.columns, pd.MultiIndex) else raw["Close"])
    close.index = pd.to_datetime(close.index).tz_localize(None)
    os.makedirs(DATA, exist_ok=True)
    close.to_parquet(CACHE_PRICES)
    return close


def load_tbill(refresh=False):
    if os.path.exists(CACHE_TBILL) and not refresh:
        s = pd.read_parquet(CACHE_TBILL)["DGS3MO"]
        s.index = pd.to_datetime(s.index).tz_localize(None)
        return s
    print("[data] downloading FRED DGS3MO ...")
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS3MO"
    with urllib.request.urlopen(url, context=_SSL_CTX, timeout=60) as r:
        df = pd.read_csv(io.StringIO(r.read().decode()))
    df.columns = ["date", "DGS3MO"]
    df["date"] = pd.to_datetime(df["date"])
    df["DGS3MO"] = pd.to_numeric(df["DGS3MO"], errors="coerce")
    df = df.dropna().set_index("date")
    os.makedirs(DATA, exist_ok=True)
    df.to_parquet(CACHE_TBILL)
    return df["DGS3MO"]


def mom(rets, skip, window):
    return (1 + rets.shift(skip)).rolling(window).apply(np.prod, raw=True) - 1


def cs_z(panel):
    return panel.sub(panel.mean(axis=1), axis=0).div(
        panel.std(axis=1).replace(0, np.nan), axis=0)


def composite(monthly, cols):
    r = monthly[cols]
    return (cs_z(mom(r, 1, 3)) + cs_z(mom(r, 1, 6)) + cs_z(mom(r, 1, 12))) / 3


def build_data(refresh=False):
    close = load_prices(refresh)
    tb_y  = load_tbill(refresh)
    tb_d  = (tb_y / 100.0 / 252.0).shift(1).reindex(close.index).ffill().fillna(0.0)

    monthly   = close.resample("ME").last().pct_change(fill_method=None)
    exec_rets = close.shift(-1).resample("ME").last().pct_change(fill_method=None)
    idx = monthly.index

    tbill_m = (tb_y.resample("ME").last() / 100.0 / 12.0).shift(1).reindex(idx)
    tbill6  = (1 + tbill_m).rolling(6).apply(np.prod, raw=True) - 1
    tbill12 = (1 + tbill_m).rolling(12).apply(np.prod, raw=True) - 1
    tot6    = mom(monthly, 0, 6)
    tot12   = mom(monthly, 0, 12)

    spy = close["SPY"].dropna()
    on_exit  = (spy > spy.rolling(REGIME_EXIT_MA).mean()).resample("ME").last()
    on_enter = (spy > spy.rolling(REGIME_ENTER_MA).mean()).resample("ME").last()
    state, out = True, {}
    for t in on_exit.index:
        if state and on_exit.get(t) == False:
            state = False
        elif not state and on_enter.get(t) == True:
            state = True
        out[t] = 1.0 if state else 0.0
    regime = pd.Series(out).reindex(idx).fillna(1.0)
    uptrend = (spy > spy.rolling(REGIME_ENTER_MA).mean()).resample("ME").last()

    return dict(close=close, rets=close.pct_change(fill_method=None),
                monthly=monthly, exec_rets=exec_rets, tb_d=tb_d, tbill_m=tbill_m,
                tbill6=tbill6, tbill12=tbill12, tot6=tot6, tot12=tot12,
                regime=regime, uptrend=uptrend)


_DI = None
def get_data(refresh=False):
    global _DI
    if _DI is None or refresh:
        _DI = build_data(refresh)
    return _DI


def pick_defensive(DI, t):
    """IEF if its trailing 12m total return beats the 12m T-bill, else cash."""
    ief = DI["tot12"].loc[t, "IEF"] if "IEF" in DI["tot12"].columns else np.nan
    tb  = DI["tbill12"].get(t, np.nan)
    if not np.isnan(ief) and not np.isnan(tb) and ief > tb:
        return "IEF"
    return CASH


# ---- STYLE engine (65%) -------------------------------------------------------------
def style_weight_path(DI):
    """Top-1 style with incumbency buffer and the fast (12m OR 6m) T-bill
    hurdle; failing months go to hurdled IEF / cash. {formation_ts: weights}."""
    scores = composite(DI["monthly"], STYLES)
    out, cur_held = {}, set()
    for t in scores.index:
        row = scores.loc[t].dropna()
        if len(row) < 3:                       # need a real cross-section
            continue
        tb12, tb6 = DI["tbill12"].get(t, np.nan), DI["tbill6"].get(t, np.nan)
        passing = set()
        for a in row.index:
            p12 = (not np.isnan(tb12)) and (DI["tot12"].loc[t, a] > tb12)
            p6  = (not np.isnan(tb6))  and (DI["tot6"].loc[t, a] > tb6)
            if p12 or p6:
                passing.add(a)
        ranked = row.rank(ascending=False)
        entry  = {a for a in row.index if ranked[a] <= STYLE_K and a in passing}
        hold   = {a for a in row.index
                  if ranked[a] <= STYLE_K + STYLE_BUFFER and a in passing}
        held   = sorted((cur_held & hold) | entry, key=lambda a: ranked[a])[:STYLE_K]

        w = (pd.Series(1.0 / STYLE_K, index=held, dtype=float)
             if held else pd.Series(dtype=float))
        def_wt = 1.0 - float(w.sum())
        if def_wt > 1e-9:
            d = pick_defensive(DI, t)
            w[d] = w.get(d, 0.0) + def_wt
        out[t] = w
        cur_held = set(held)
    return out


# ---- SECTOR engine (35%) ------------------------------------------------------------
def congestion_equilibrium(mu, corr, lam=GAME_LAM, iters=300, eta=0.1):
    """Nash equilibrium of the capital-congestion game: allocating weight w_i
    to asset i earns its momentum score mu_i minus a crowding tax
    lam * (corr @ w)_i that grows with how much capital already sits in
    correlated assets. A potential game -- replicator dynamics converge to
    the simplex maximizer of  mu.w - (lam/2) w' corr w."""
    w = np.full(len(mu), 1.0 / len(mu))
    for _ in range(iters):
        grad = mu - lam * corr @ w
        w = w * np.exp(eta * (grad - grad.max()))  # shift for numerical stability
        w /= w.sum()
    return w


def sector_weight_path(DI):
    """Top-4 sectors by congestion-game equilibrium rank (crowded momentum is
    taxed), top-6 incumbency buffer, equal weights, fast-re-entry regime -> AGG.
    The equilibrium decides only WHICH sectors to hold; sizing stays equal
    weight (equilibrium sizing concentrates and backtests worse)."""
    scores = composite(DI["monthly"], SECTORS)
    reg = DI["regime"].reindex(scores.index).fillna(1.0)
    rets = DI["rets"]
    out, cur_held = {}, set()
    for t in scores.index:
        row = scores.loc[t].dropna()
        if len(row) < TOP_K:
            continue
        if reg.loc[t] == 0.0:
            out[t] = pd.Series({pick_defensive(DI, t): 1.0})
            cur_held = set()
            continue
        hist = rets[row.index].loc[:t].tail(GAME_CORR_DAYS)
        corr = hist.corr().fillna(0.0).to_numpy(copy=True)   # copy: pandas>=3 returns a read-only view
        np.fill_diagonal(corr, 1.0)
        eq = pd.Series(congestion_equilibrium(row.to_numpy(), corr), index=row.index)
        ranked = eq.rank(ascending=False)
        entry  = set(ranked[ranked <= TOP_K].index)
        hold   = set(ranked[ranked <= BUFFER_EXIT].index)
        held   = list((cur_held & hold) | entry)
        out[t] = pd.Series(1.0 / len(held), index=held)
        cur_held = set(held)
    return out


# ---- book assembly ------------------------------------------------------------------
def combine_paths(paths_weights):
    common = set.intersection(*(set(p.keys()) for p, _ in paths_weights))
    out = {}
    for t in sorted(common):
        s = pd.Series(dtype=float)
        for p, bw in paths_weights:
            s = s.add(p[t] * bw, fill_value=0.0)
        out[t] = s[s.abs() > 1e-12]
    return out


def throttle_target(DI, tgt, t, book_vt=BOOK_VT):
    """Apply the crash-only vol throttle to one month's target weights.
    No cap while SPY is above its 126d MA; below it, trim to `book_vt`."""
    if not book_vt:
        return tgt
    if bool(DI["uptrend"].get(t, True)):
        return tgt
    risk_w = tgt[[c for c in tgt.index if c in RISK_TICKERS]]
    if not len(risk_w) or risk_w.sum() <= 0:
        return tgt
    rets = DI["rets"]
    priced = [c for c in tgt.index if c in rets.columns]
    hist = rets.loc[:t].iloc[-VOL_WINDOW:][priced].fillna(0.0)
    pv = float((hist @ tgt[priced].values).std() * np.sqrt(252))
    if pv <= 0 or book_vt / pv >= 1.0:
        return tgt
    scale = book_vt / pv
    tgt = tgt.copy()
    cut = risk_w * (1.0 - scale)
    tgt[cut.index] = tgt[cut.index] - cut
    d = pick_defensive(DI, t)
    tgt[d] = tgt.get(d, 0.0) + float(cut.sum())
    return tgt[tgt.abs() > 1e-12]


def simulate(weights_by_formation, DI=None, *, book_vt=BOOK_VT, cost_bps=COST_BPS,
             start=None, end=None):
    """Daily buy-and-hold accounting of the monthly targets (+ throttle).
    Returns (monthly net returns by earned month-end, stats dict)."""
    DI = DI or get_data()
    close, rets, tb_d = DI["close"], DI["rets"], DI["tb_d"]
    form_dates = sorted(weights_by_formation.keys())
    if start:
        form_dates = [t for t in form_dates if t >= pd.Timestamp(start)]
    if end:
        form_dates = [t for t in form_dates if t <= pd.Timestamp(end)]

    days = close.index
    first_exec = days[days.searchsorted(form_dates[0]) + 1]
    last_day   = days[min(days.searchsorted(form_dates[-1]) + 22, len(days) - 1)]
    sim_days   = days[(days >= first_exec) & (days <= last_day)]

    exec_of = {}
    for t in form_dates:
        i = days.searchsorted(t, side="right")
        if i < len(days):
            exec_of.setdefault(days[i], []).append(t)

    pos, nav = {}, 1.0
    turnover, nav_path = [], []
    for d in sim_days:
        newpos = {}
        for tkr, val in pos.items():
            if tkr == CASH:
                newpos[CASH] = newpos.get(CASH, 0.0) + val * (1 + tb_d.loc[d])
                continue
            r = rets.at[d, tkr] if tkr in rets.columns else np.nan
            if np.isnan(r):
                r = tb_d.loc[d]                    # splice: no quote -> T-bill
            newpos[tkr] = newpos.get(tkr, 0.0) + val * (1 + r)
        pos = newpos
        nav = sum(pos.values()) if pos else nav

        traded = 0.0
        if d in exec_of:
            t = exec_of[d][-1]
            tgt = throttle_target(DI, weights_by_formation[t], t, book_vt)
            tgt_vals = {tkr: w * nav for tkr, w in tgt.items()}
            allk = set(tgt_vals) | set(pos)
            traded = sum(abs(tgt_vals.get(kk, 0.0) - pos.get(kk, 0.0)) for kk in allk)
            pos = {kk: v for kk, v in tgt_vals.items() if v > 1e-15}

        if traded > 0:
            cost = traded * cost_bps / 10_000.0
            tot = sum(pos.values())
            pos = {kk: v * (tot - cost) / tot for kk, v in pos.items()}
            nav = tot - cost
            turnover.append(traded / nav)
        nav_path.append((d, nav))

    nav_s = pd.Series(dict(nav_path)).sort_index()
    monthly = nav_s.resample("ME").last().pct_change(fill_method=None).dropna()
    ann_turn = sum(turnover) / max(len(nav_s), 1) * 252
    return monthly, dict(nav=nav_s, ann_turnover=ann_turn)


def build_strategy(*, w_style=W_STYLE, w_sector=W_SECTOR, book_vt=BOOK_VT,
                   cost_bps=COST_BPS, start=None, end=None, DI=None):
    """The locked strategy end-to-end."""
    DI = DI or get_data()
    ps = style_weight_path(DI)
    p6 = sector_weight_path(DI)
    wcomb = combine_paths([(ps, w_style), (p6, w_sector)])
    return simulate(wcomb, DI, book_vt=book_vt, cost_bps=cost_bps,
                    start=start, end=end)


# ---- metrics ------------------------------------------------------------------------
def in_sample_mask(index, start=IS_START, end=IS_END):
    return (index >= pd.Timestamp(start)) & (index <= pd.Timestamp(end))


def metrics(returns, mask=None):
    r = (returns[mask] if mask is not None else returns).dropna()
    n = len(r)
    if n < 2:
        return dict(ann_ret=np.nan, ann_vol=np.nan, sharpe=np.nan,
                    tstat=np.nan, max_dd=np.nan, n=n)
    ann_ret = (1 + r).prod() ** (12 / n) - 1
    ann_vol = r.std() * np.sqrt(12)
    sharpe  = ann_ret / ann_vol if ann_vol else np.nan
    tstat   = r.mean() / (r.std() / np.sqrt(n))
    eq      = (1 + r).cumprod()
    max_dd  = (eq / eq.cummax() - 1).min()
    return dict(ann_ret=ann_ret, ann_vol=ann_vol, sharpe=sharpe,
                tstat=tstat, max_dd=max_dd, n=n)


def roll12(r):
    return (1 + r).rolling(12).apply(np.prod, raw=True) - 1


def regret_vs_spy(r, DI=None, start=IS_START, end=IS_END):
    DI = DI or get_data()
    spy = DI["monthly"]["SPY"]
    m = in_sample_mask(r.index, start, end)
    rr = r[m].dropna()
    sp = spy.reindex(rr.index).dropna()
    rr = rr.reindex(sp.index)
    gap = (roll12(rr) - roll12(sp)).dropna()
    cy = (1 + rr).groupby(rr.index.year).prod() - 1
    sy = (1 + sp).groupby(sp.index.year).prod() - 1
    full = [y for y in cy.index if (rr.index.year == y).sum() == 12]
    cy, sy = cy[full], sy[full]
    bull = [y for y in full if sy[y] > 0.15]
    return dict(pct12=float((gap >= 0).mean()), worst12=float(gap.min()),
                p_lag5=float((gap < -0.05).mean()),
                bull_w=int(sum(cy[y] >= sy[y] for y in bull)), bull_n=len(bull),
                yrs_w=int(sum(cy[y] >= sy[y] for y in full)), yrs_n=len(full))
