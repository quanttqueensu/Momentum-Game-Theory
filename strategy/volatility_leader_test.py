"""Research volatility-conditioned use of the already-known next ranking.

Run: PYTHONDONTWRITEBYTECODE=1 python3 strategy/volatility_leader_test.py
Uses cached production inputs; does not modify the model or contact IBKR.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

import strategy_lib as S
from next_rank_entry_test import (
    assert_paths_equal, md_table, next_ranks, paired_interval, period_nav,
)


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"
PREFIX = "Volatility_Leader_Timing"
# Fixed before examining backtest returns. These are comparisons, not a search
# for the best threshold. Candidate volatility is the primary regime measure.
CONFIGS = {
    "baseline": ("baseline", "candidate", np.inf),
    "advance_candidate_20": ("advance", "candidate", 0.20),
    "retain_next_incumbent_20": ("retain", "candidate", 0.20),
    "advance_candidate_15": ("advance", "candidate", 0.15),
    "advance_candidate_25": ("advance", "candidate", 0.25),
    "advance_spy_20": ("advance", "SPY", 0.20),
    "advance_always": ("advance", "candidate", -np.inf),
}
LABELS = {
    "baseline": "Current strategy",
    "advance_candidate_20": "Use next leader when candidate vol >20%",
    "retain_next_incumbent_20": "Keep incumbent if next leader; candidate vol >20%",
    "advance_candidate_15": "Candidate-vol threshold 15%",
    "advance_candidate_25": "Candidate-vol threshold 25%",
    "advance_spy_20": "SPY-vol threshold 20%",
    "advance_always": "Always use qualifying next leader",
}
COSTS = (0, 10, 25)


def volatility(di):
    """21 daily observations, sample standard deviation, annualized."""
    return (di["rets"][S.STYLES].rolling(21, min_periods=21).std()
            * np.sqrt(252)).resample("ME").last().reindex(di["monthly"].index)


def style_path(di, variant):
    action, source, threshold = CONFIGS[variant]
    scores = S.composite(di["monthly"], S.STYLES)
    projected = next_ranks(di["monthly"])
    vols = volatility(di)
    path, records, incumbent = {}, [], set()
    for t in scores.index:
        row = scores.loc[t].dropna()
        if len(row) < 3:
            continue
        ranks = row.rank(ascending=False)
        tb6, tb12 = di["tbill6"].get(t, np.nan), di["tbill12"].get(t, np.nan)
        passing = {
            a for a in row.index
            if (not np.isnan(tb6) and di["tot6"].loc[t, a] > tb6)
            or (not np.isnan(tb12) and di["tot12"].loc[t, a] > tb12)
        }
        entry = {a for a in row.index if ranks[a] <= S.STYLE_K and a in passing}
        hold = {a for a in row.index
                if ranks[a] <= S.STYLE_K + S.STYLE_BUFFER and a in passing}
        held = sorted((incumbent & hold) | entry, key=lambda a: ranks[a])[:S.STYLE_K]
        candidate = min(entry, key=lambda a: ranks[a]) if entry else None
        winners = projected.loc[t][projected.loc[t] == 1].index
        next_leader = winners[0] if len(winners) == 1 else None
        candidate_vol = float(vols.loc[t, candidate]) if candidate else np.nan
        regime_vol = candidate_vol if source == "candidate" else float(vols.loc[t, source])
        regime = bool(regime_vol > threshold)
        disagreement = candidate is not None and next_leader is not None and candidate != next_leader
        next_passes = next_leader in passing
        eligible = bool(disagreement and next_passes)
        override = bool(action != "baseline" and regime and eligible)
        if action == "retain":
            override = bool(override and next_leader in incumbent and next_leader in hold)
        if override:
            held = [next_leader]
        weights = (pd.Series(1.0 / S.STYLE_K, index=held, dtype=float)
                   if held else pd.Series(dtype=float))
        defensive_weight = 1.0 - float(weights.sum())
        if defensive_weight > 1e-9:
            defensive = S.pick_defensive(di, t)
            weights[defensive] = weights.get(defensive, 0.0) + defensive_weight
        path[t] = weights
        records.append(dict(
            formation=t, variant=variant, incumbent=",".join(sorted(incumbent)),
            current_leader=candidate, known_next_leader=next_leader,
            candidate_vol=candidate_vol, spy_vol=float(vols.loc[t, "SPY"]),
            regime=regime, leaders_differ=disagreement, next_leader_passes_today=next_passes,
            override=override, selected=",".join(weights.index),
        ))
        incumbent = set(held)
    return path, pd.DataFrame(records)


def checks(di, paths):
    assert_paths_equal(paths["baseline"], S.style_weight_path(di))
    # Every prediction must be identical to the next actual ranking, whose
    # newest month's returns are deliberately skipped.
    actual = S.composite(di["monthly"], S.STYLES).rank(axis=1, ascending=False)
    pd.testing.assert_frame_equal(
        next_ranks(di["monthly"]).iloc[:-1].reset_index(drop=True),
        actual.iloc[1:].reset_index(drop=True))
    # Both forecasts and the volatility regime must survive truncating future
    # data. Test selections around the original split and the pandemic crash.
    for cutoff in (pd.Timestamp("2018-12-31"), pd.Timestamp("2020-03-31")):
        prefix = {key: value.loc[:cutoff] for key, value in di.items()}
        for variant in CONFIGS:
            selected, _ = style_path(prefix, variant)
            expected = {t: w for t, w in paths[variant].items() if t <= cutoff}
            assert_paths_equal(selected, expected)
    # With a disabled volatility trigger, the alternative must be baseline.
    CONFIGS["test_never"] = ("advance", "candidate", np.inf)
    try:
        never, _ = style_path(di, "test_never")
        assert_paths_equal(never, paths["baseline"])
    finally:
        del CONFIGS["test_never"]


def event_comparison(di, events, last_signal):
    """One holding-period ETF comparison on all primary-trigger occasions.

    Event selection uses information at formation. The future prices below
    are outcomes for evaluation only, never inputs to either strategy.
    Each ETF is charged the same 10 bps on entry and 10 bps on exit. This
    diagnostic excludes sector effects and incumbent-specific saved turnover;
    the full portfolio simulation includes those effects separately.
    """
    rows = []
    days = di["close"].index
    chosen = events[(events.variant == "advance_candidate_20") & events.override
                    & (events.formation >= pd.Timestamp(S.IS_START))]
    for event in chosen.itertuples():
        if event.formation > last_signal:
            continue
        next_formation = event.formation + pd.offsets.MonthEnd(1)
        entry_i = days.searchsorted(event.formation, side="right")
        exit_i = days.searchsorted(next_formation, side="right")
        if entry_i >= len(days) or exit_i >= len(days):
            continue
        entry_date, exit_date = days[entry_i], days[exit_i]
        old, new = event.current_leader, event.known_next_leader
        old_gross = float(di["close"].loc[exit_date, old] / di["close"].loc[entry_date, old])
        new_gross = float(di["close"].loc[exit_date, new] / di["close"].loc[entry_date, new])
        if not np.isfinite(old_gross + new_gross):
            continue
        old_net, new_net = old_gross * 0.999**2 - 1, new_gross * 0.999**2 - 1
        rows.append(dict(formation=event.formation, entry=entry_date, exit=exit_date,
                         current_leader=old, next_leader=new, candidate_vol=event.candidate_vol,
                         current_leader_return=old_net, next_leader_return=new_net,
                         next_minus_current=new_net-old_net))
    return pd.DataFrame(rows)


def main():
    for filename in (S.CACHE_PRICES, S.CACHE_TBILL):
        if not Path(filename).exists():
            raise FileNotFoundError(f"Cached input required: {filename}")
    di = S.get_data(refresh=False)
    paths, frames = {}, []
    for variant in CONFIGS:
        paths[variant], events = style_path(di, variant)
        frames.append(events)
    checks(di, paths)
    print("Verified baseline, prediction identity, disabled-trigger control, and causal prefixes.", flush=True)

    sector_paths = {key: S.sector_weight_path(di, path) for key, path in paths.items()}
    last = S.latest_formation(di, paths["baseline"], sector_paths["baseline"])
    events = pd.concat(frames, ignore_index=True)
    events = events[events.formation <= last].copy()
    events["style_changed"] = events.groupby("variant", sort=False).selected.transform(
        lambda holdings: holdings.ne(holdings.shift(1)))
    periods = (("2001-2018", S.IS_START, S.IS_END),
               ("2019-latest", "2019-01-01", str(last.date())),
               ("Full", S.IS_START, str(last.date())))
    series, summaries = {}, []
    for variant, style in paths.items():
        book = S.combine_paths([(style, S.W_STYLE), (sector_paths[variant], S.W_SECTOR)])
        book = {t: w for t, w in book.items() if t <= last}
        for cost in COSTS:
            returns, sim = S.simulate(book, di, cost_bps=cost)
            returns = returns.loc[S.IS_START:last]
            series[variant, cost] = returns
            for period, start, end in periods:
                metrics = S.metrics(returns, S.in_sample_mask(returns.index, start, end), rf=di["tbill_m"])
                daily_dd = S.drawdown_stats(equity=period_nav(sim["nav"], start, end))["max_dd"]
                records = events[(events.variant == variant) & events.formation.between(start, end)
                                 & (events.formation < di["close"].index.max())]
                summaries.append(dict(variant=variant, period=period, cost_bps=cost,
                                      **metrics, daily_max_dd=daily_dd,
                                      overrides=int(records.override.sum()),
                                      style_changes=int(records.style_changed.sum())))
            full = summaries[-1]
            print(f"{variant:<26} {cost:>2}bps: CAGR {full['ann_ret']:.2%}, "
                  f"Sharpe {full['sharpe']:.3f}, DD {full['daily_max_dd']:.2%}, "
                  f"overrides {full['overrides']}", flush=True)
    native, _ = S.build_strategy(DI=di)
    pd.testing.assert_series_equal(series["baseline", 10], native.loc[S.IS_START:last])
    summary = pd.DataFrame(summaries)

    intervals = []
    for variant in CONFIGS:
        if variant == "baseline":
            continue
        delta = series[variant, 10] - series["baseline", 10]
        for period, start, end in periods:
            sample = delta.loc[start:end]
            lo, hi = paired_interval(sample)
            intervals.append(dict(variant=variant, period=period,
                                  annualized_mean_difference=sample.mean()*12,
                                  low_95=lo, high_95=hi))
    intervals = pd.DataFrame(intervals)
    event_returns = event_comparison(di, events, last)
    vols = volatility(di)
    snapshot = []
    for ticker in ("SPY", "QQQ", "IWD"):
        r = di["rets"][ticker].loc[:last].dropna()
        p = di["close"][ticker].loc[:last].dropna()
        history = vols[ticker].loc[:last].iloc[:-1].dropna()
        current_vol = float(vols.loc[last, ticker])
        snapshot.append(dict(ticker=ticker, as_of=p.index[-1], close=p.iloc[-1],
                             last_day_return=r.iloc[-1], month_return=di["monthly"].loc[last,ticker],
                             realized_vol_21d=current_vol,
                             percentile_vs_prior_month_ends=float((history<current_vol).mean()),
                             drawdown_from_cached_high=p.iloc[-1]/p.cummax().iloc[-1]-1))
    snapshot = pd.DataFrame(snapshot)
    OUT.mkdir(exist_ok=True)
    for suffix, data in (("Summary", summary), ("Decisions", events),
                         ("Intervals", intervals), ("Events", event_returns), ("Market_Snapshot", snapshot)):
        data.to_csv(OUT/f"{PREFIX}_{suffix}.csv", index=False, date_format="%Y-%m-%d")
    pd.DataFrame({f"{variant}_{cost}bps": returns for (variant,cost),returns in series.items()}).to_csv(
        OUT/f"{PREFIX}_Monthly_Returns.csv", index_label="earned_month")

    def result(variant, period="Full"):
        return summary[(summary.variant == variant) & (summary.period == period)
                       & (summary.cost_bps == 10)].iloc[0]

    base, primary = result("baseline"), result("advance_candidate_20")
    later_base, later_primary = result("baseline", "2019-latest"), result("advance_candidate_20", "2019-latest")
    targeted = result("retain_next_incumbent_20")
    lines = ["# Volatility and the already-known next-month leader", "",
             f"Research date: November 2, 2026. Cached prices through {di['close'].index.max().date()}. "
             f"Last complete signal month: {last.date()}.", "", "## Findings", "",
             f"At 10 bps per traded leg, advancing to the next leader during candidate "
             f"volatility above 20% reduced full-period CAGR from {base.ann_ret:.2%} "
             f"to {primary.ann_ret:.2%}, while reducing the worst daily drawdown from "
             f"{base.daily_max_dd:.2%} to {primary.daily_max_dd:.2%}. Its full-period "
             "Sharpe was lower, and the paired return-difference interval spans zero.", "",
             f"The later-period result was better: CAGR {later_primary.ann_ret:.2%} "
             f"versus {later_base.ann_ret:.2%}, across {later_primary.overrides:.0f} "
             "executed overrides. Its paired interval also spans zero. This later "
             "period is not a clean holdout.", "",
             f"The narrower rule of retaining an eligible incumbent when it is also "
             f"the next leader had only {targeted.overrides:.0f} completed historical "
             f"overrides and a full-period CAGR of {targeted.ann_ret:.2%}. It would "
             "retain IWD for the current signal, but the small sample provides little "
             "evidence for that specific override. The current signal has no realized "
             "holding-period outcome in the cached data.", "",
             "These are risk/return tradeoffs rather than evidence of a reliably "
             "more profitable current trade. No tested alternative improved "
             "full-period CAGR and Sharpe over baseline, and no production rule "
             "was changed.", "",
             "## Market context at the rebalance", ""]
    lines.append(md_table(
        ["ETF", "October return", "Last daily return", "21-day annualized realized vol", "Historical month-end vol percentile"],
        [[x.ticker,f"{x.month_return:+.2%}",f"{x.last_day_return:+.2%}",
          f"{x.realized_vol_21d:.2%}",f"{x.percentile_vs_prior_month_ends:.1%}"]
         for x in snapshot.itertuples()]))
    lines += ["", "Volatility is the sample standard deviation of the latest 21 daily "
              "adjusted-close returns multiplied by sqrt(252). The percentile compares "
              "with earlier month-end observations available in the same cached history. "
              "QQQ is substantially more volatile than IWD, while SPY's measured "
              "volatility is below the study's 20% broad-market threshold.", "",
              "Cboe's official page reports a previous VIX close of 19.42 for October 30. "
              "That is option-implied broad-market volatility, a different measure from "
              "the realized ETF volatilities above. No November 2 intraday observation "
              "is used to choose historical month-end regimes. "
              "[Cboe VIX](https://www.cboe.com/tradable-products/vix/)", "",
              "## Rules specified before examining returns", "",
              "Primary rule: if the currently first-ranked style ETF passes today's "
              "6m OR 12m cash hurdle, its 21-day annualized volatility exceeds 20%, "
              "the known next-month momentum leader differs, and that next leader "
              "also passes today's hurdle, allocate the style sleeve to the next "
              "leader now. Otherwise follow the production leader-first selector. "
              "The alternative leader can be below today's top two. This condition "
              "is evaluated at each monthly formation, including for an existing "
              "holding; it is not restricted to new entries.", "",
              "Targeted incumbent variant: under the same 20% candidate-volatility "
              "condition, retain the incumbent only if it is the known next leader, "
              "is still in today's top two, and passes today's cash hurdle. Otherwise "
              "follow production. This directly tests retaining IWD in a QQQ-to-IWD "
              "situation without advancing to arbitrary new ETFs.", "",
              "Sensitivity checks: candidate-volatility thresholds of 15% and 25%; "
              "SPY rather than candidate volatility above 20%; and unconditional "
              "use of a differing next leader that passes today's hurdle. These "
              "are displayed together rather than selecting the best threshold. "
              "A threshold named 20% is a round research convention, not an "
              "independently validated definition of a high-volatility regime.", "",
              "The next ranking uses only returns through the completed formation "
              "month because the production ranking skips one month. Future returns "
              "and future cash hurdles are never used to select positions. Knowing "
              "next month's leader does not guarantee it will pass next month's "
              "cash hurdle or be held then.", "",
              "All variants retain the 65/35 portfolio split, cash hurdles, defensive "
              "selection, regime rules, disabled throttle, next-trading-day closing "
              "execution, and daily buy-and-hold accounting. The sector congestion "
              "game is recalculated for each counterfactual style path. Each version "
              "maintains its own incumbent history.", "",
              "## Net backtest at 10 bps per traded leg", ""]
    rows = []
    for period,_,_ in periods:
        for variant in CONFIGS:
            x=summary[(summary.variant==variant)&(summary.period==period)&(summary.cost_bps==10)].iloc[0]
            rows.append([period,LABELS[variant],f"{x.ann_ret:.2%}",f"{x.sharpe:.3f}",
                         f"{x.daily_max_dd:.2%}",int(x.overrides),int(x.style_changes)])
    lines += [md_table(["Period","Rule","CAGR","Sharpe","Daily max DD","Overrides","Style changes"],rows),"",
              "Override and change counts are formation-dated and require an "
              "execution within the cached data; the latest October signal has "
              "no November execution or outcome in this dataset. The inherited "
              "simulator omits its initial partial month; the reported monthly "
              f"returns run from {series['baseline',10].index.min().date()} through {last.date()}.","",
              "## Cost sensitivity: full period",""]
    lines.append(md_table(
        ["Rule","Cost per leg (bps)","CAGR","Sharpe"],
        [[LABELS[x.variant],x.cost_bps,f"{x.ann_ret:.2%}",f"{x.sharpe:.3f}"]
         for x in summary[summary.period=="Full"].itertuples()]))
    lines += ["","## Uncertainty: paired return differences at 10 bps", "",
              "12-month circular moving-block bootstrap, 10,000 resamples, fixed seed "
              "20261102. Differences below are annualized arithmetic mean return "
              "differences, not CAGR differences. Intervals are descriptive and do "
              "not correct for testing several related strategy variants.",""]
    lines.append(md_table(
        ["Rule minus baseline","Period","Annualized mean difference","95% block interval"],
        [[LABELS[x.variant],x.period,f"{x.annualized_mean_difference:+.2%}",
          f"[{x.low_95:+.2%}, {x.high_95:+.2%}]"] for x in intervals.itertuples()]))
    lines += ["","## Matched volatile-month diagnostic", "",
              "On primary-rule trigger months, compare the current and next leaders "
              "from the next trading day's close to the following rebalance close. "
              "Both ETFs are charged 10 bps on entry and 10 bps on exit. This is an "
              "ETF-only diagnostic; it excludes sector changes and the ability to "
              "avoid a trade by retaining an existing position. Those effects are "
              "included in the full strategy results above. Only fully observed "
              "holding periods are included.",""]
    event_rows=[]
    for label,start,end in periods:
        sample=event_returns[event_returns.formation.between(start,end)]
        if len(sample):
            event_rows.append([label,len(sample),f"{sample.current_leader_return.mean():+.2%}",
                               f"{sample.next_leader_return.mean():+.2%}",
                               f"{sample.next_minus_current.mean():+.2%}",
                               f"{(sample.next_minus_current>0).mean():.1%}"])
    lines += [md_table(["Formation period","Cases","Current leader mean","Next leader mean",
                        "Mean difference","Next leader wins"],event_rows),"",
              "These events can cluster in the same market episode; the number of "
              "events is not the number of independent observations.","",
              "## Latest signal: decisions without a realized outcome", ""]
    lines.append(md_table(
        ["Rule","Its incumbent","Current leader","Known next leader","Candidate vol","Regime?","Override?","Selected"],
        [[LABELS[x.variant],x.incumbent,x.current_leader,x.known_next_leader,
          f"{x.candidate_vol:.2%}",x.regime,x.override,x.selected]
         for x in events[events.formation==last].itertuples()]))
    lines += ["","## Verification and limits", "",
              "- The baseline weights and net return path exactly match production. "
              "The disabled-trigger control also matches baseline.",
              "- Forecasts equal the next ranking across the full history. "
              "Truncating all inputs at December 2018 and March 2020 leaves all "
              "earlier strategy decisions unchanged, including their volatility regimes.",
              "- This is exploratory research motivated by the current QQQ signal. "
              "2019+ is a later-period diagnostic, not a clean holdout. Choosing a "
              "threshold after examining these results would introduce further selection bias.",
              "- Cached adjusted prices and FRED histories are not point-in-time "
              "vintage datasets. Original release delays and historical revisions "
              "are not reconstructed.",
              "- The inherited simulator charges turnover across its position "
              "dictionary, including CASH changes. Its conventions are identical "
              "for all comparisons; no production accounting change was made.",
              "- No strategy rule, broker configuration, or order was changed by "
              "this research script.","","## Reproduce","","```bash",
              "PYTHONDONTWRITEBYTECODE=1 python3 strategy/volatility_leader_test.py","```", "",
              "Input fingerprints:",""]
    for filename in (S.CACHE_PRICES, S.CACHE_TBILL, str(Path(S.__file__)),
                     str(Path(__file__)), str(Path(__file__).with_name("next_rank_entry_test.py"))):
        digest=hashlib.sha256(Path(filename).read_bytes()).hexdigest()
        lines.append(f"- `{Path(filename).relative_to(ROOT)}`: `{digest}`")
    report=OUT/f"{PREFIX}.md"
    report.write_text("\n".join(lines)+"\n")
    print("Verified production returns. Saved:",report,flush=True)
    print(summary[(summary.cost_bps==10)][[
        "variant","period","ann_ret","sharpe","daily_max_dd","overrides"]].to_string(index=False))
    print("Primary-rule event count:",len(event_returns),flush=True)


if __name__=="__main__":
    main()
