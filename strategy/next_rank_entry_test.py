"""Research only: reject new style entries with a known next-month rank > 2.

Run from the repository root:
    PYTHONDONTWRITEBYTECODE=1 python3 strategy/next_rank_entry_test.py

Uses cached inputs and the production sector selector, simulator, and costs.
Does not change production selection or connect to a broker.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

import strategy_lib as S


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"
PREFIX = "Next_Month_Rank_Entry_Filter"
VARIANTS = ("baseline", "retain_incumbent", "defensive")
LABELS = {
    "baseline": "Current strategy",
    "retain_incumbent": "Reject entry; retain eligible incumbent",
    "defensive": "Reject entry; use defensive holding",
}
COSTS = (0, 10, 25)


def next_ranks(monthly):
    """At formation t, rank the scores that formation t+1 will use.

    Production ranking shifts returns by one month. Thus the next ranking
    uses returns through t, all observable at t's completed closing prices.
    No next-month returns, hurdles, or realized holding durations enter here.
    """
    r = monthly[S.STYLES]
    score = sum(S.cs_z(S.mom(r, 0, h)) for h in (3, 6, 12)) / 3
    return score.rank(axis=1, ascending=False)


def style_path(di, variant="baseline"):
    if variant not in VARIANTS:
        raise ValueError(f"Unknown variant: {variant}")
    scores = S.composite(di["monthly"], S.STYLES)
    projected = next_ranks(di["monthly"])
    path, events, incumbent = {}, [], set()
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
        candidate = min(entry, key=lambda a: ranks[a]) if entry else None
        new_entry = candidate is not None and candidate not in incumbent
        projected_rank = (float(projected.loc[t, candidate])
                          if candidate is not None else np.nan)
        reject = bool(variant != "baseline" and new_entry
                      and projected_rank > S.STYLE_K + S.STYLE_BUFFER)
        allowed_entry = set() if reject else entry
        keep = incumbent & hold
        if reject and variant == "defensive":
            keep = set()
        held = sorted(keep | allowed_entry, key=lambda a: ranks[a])[:S.STYLE_K]
        weights = (pd.Series(1.0 / S.STYLE_K, index=held, dtype=float)
                   if held else pd.Series(dtype=float))
        defensive_weight = 1.0 - float(weights.sum())
        if defensive_weight > 1e-9:
            defensive = S.pick_defensive(di, t)
            weights[defensive] = weights.get(defensive, 0.0) + defensive_weight
        path[t] = weights
        events.append({
            "formation": t.date().isoformat(), "variant": variant,
            "incumbent": ",".join(sorted(incumbent)), "candidate": candidate,
            "new_entry": new_entry, "known_next_rank": projected_rank,
            "rejected": reject, "selected": ",".join(weights.index),
        })
        incumbent = set(held)
    return path, pd.DataFrame(events)


def assert_paths_equal(left, right):
    assert left.keys() == right.keys()
    for t in left:
        a, b = left[t].sort_index(), right[t].sort_index()
        pd.testing.assert_series_equal(a, b, check_names=False, atol=1e-12, rtol=1e-12)


def verify_causality(di, paths):
    # An actual next month's ranking must match today's projection, despite
    # that month's prices being excluded from today's information set.
    actual = S.composite(di["monthly"], S.STYLES).rank(axis=1, ascending=False)
    pd.testing.assert_frame_equal(
        next_ranks(di["monthly"]).iloc[:-1].reset_index(drop=True),
        actual.iloc[1:].reset_index(drop=True),
    )
    # Recompute decisions from truncated inputs: future observations cannot
    # alter selections already made, including during the 2020 crash.
    for cutoff in (pd.Timestamp("2018-12-31"), pd.Timestamp("2020-03-31")):
        prefix = {key: value.loc[:cutoff] for key, value in di.items()}
        for variant in VARIANTS:
            prefix_path, _ = style_path(prefix, variant)
            expected = {t: w for t, w in paths[variant].items() if t <= cutoff}
            assert_paths_equal(prefix_path, expected)
    # Arbitrary next-month outcomes cannot affect the forecast known today.
    last = di["monthly"].index[-1]
    next_month = last + pd.offsets.MonthEnd(1)
    expected = next_ranks(di["monthly"]).loc[last]
    for shock in (-0.30, 0.30):
        future = pd.DataFrame(shock, index=[next_month], columns=di["monthly"].columns)
        extended = pd.concat([di["monthly"], future])
        actual_next = S.composite(extended, S.STYLES).loc[next_month].rank(ascending=False)
        pd.testing.assert_series_equal(expected, actual_next, check_names=False)


def period_nav(nav, start, end):
    selected = nav.loc[start:end]
    anchor = nav.loc[nav.index < pd.Timestamp(start)].tail(1)
    if anchor.empty:
        anchor = pd.Series([1.0], index=[selected.index[0] - pd.Timedelta(days=1)])
    return pd.concat([anchor, selected])


def paired_interval(delta, draws=10_000):
    """Paired circular 12-month block interval for annualized mean difference."""
    values = delta.to_numpy()
    n, block = len(values), 12
    rng = np.random.default_rng(20261102)
    starts = rng.integers(0, n, size=(draws, (n + block - 1) // block))
    indices = ((starts[:, :, None] + np.arange(block)) % n).reshape(draws, -1)[:, :n]
    lo, hi = np.quantile(values[indices].mean(axis=1) * 12, [0.025, 0.975])
    return float(lo), float(hi)


def md_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(map(str, row)) + " |" for row in rows]
    return "\n".join(lines)


def main():
    for name in (S.CACHE_PRICES, S.CACHE_TBILL):
        if not Path(name).exists():
            raise FileNotFoundError(f"Cached input required; refresh separately: {name}")
    di = S.get_data(refresh=False)
    paths, event_frames = {}, []
    for variant in VARIANTS:
        paths[variant], events = style_path(di, variant)
        event_frames.append(events)
    assert_paths_equal(paths["baseline"], S.style_weight_path(di))
    verify_causality(di, paths)
    print("Verified production style baseline and chronological invariance.", flush=True)

    returns, navs, sectors, combined = {}, {}, {}, {}
    for variant in VARIANTS:
        sectors[variant] = S.sector_weight_path(di, paths[variant])
        combined[variant] = S.combine_paths([
            (paths[variant], S.W_STYLE), (sectors[variant], S.W_SECTOR)])
    last_signal = S.latest_formation(di, paths["baseline"], sectors["baseline"])
    periods = (
        ("2001-2018", S.IS_START, S.IS_END),
        ("2019-latest", "2019-01-01", str(last_signal.date())),
        ("Full", S.IS_START, str(last_signal.date())),
    )
    events = pd.concat(event_frames, ignore_index=True)
    events["formation"] = pd.to_datetime(events["formation"])
    events = events[events["formation"] <= last_signal]
    events["style_changed"] = events.groupby("variant", sort=False)["selected"].transform(
        lambda holdings: holdings.ne(holdings.shift(1)))
    summaries = []
    for variant in VARIANTS:
        weights = {t: w for t, w in combined[variant].items() if t <= last_signal}
        for cost in COSTS:
            r, stats = S.simulate(weights, di, cost_bps=cost)
            r = r.loc[S.IS_START:last_signal]
            returns[variant, cost], navs[variant, cost] = r, stats["nav"]
            for period, start, end in periods:
                metrics = S.metrics(r, S.in_sample_mask(r.index, start, end), rf=di["tbill_m"])
                daily = S.drawdown_stats(equity=period_nav(stats["nav"], start, end))
                selected_events = events[(events["variant"] == variant)
                                         & events["formation"].between(start, end)]
                # Exclude signals without a following trading date in the
                # cached prices: October 2026's choice is not yet executed.
                executed_events = selected_events[
                    selected_events["formation"] < di["close"].index.max()]
                changed_sector_months = sum(
                    set(sectors[variant][t].index) != set(sectors["baseline"][t].index)
                    for t in sectors[variant]
                    if pd.Timestamp(start) <= t <= pd.Timestamp(end)
                    and t < di["close"].index.max()
                )
                row = dict(variant=variant, cost_bps=cost, period=period,
                           start=start, end=end, **metrics,
                           daily_max_dd=daily["max_dd"],
                           rejected_entries=int(executed_events["rejected"].sum()),
                           style_changes=int(executed_events["style_changed"].sum()),
                           new_entry_candidates=int(executed_events["new_entry"].sum()),
                           sector_months_changed=changed_sector_months)
                summaries.append(row)
            full = summaries[-1]
            print(f"{variant:<17} cost={cost:>2}bps: "
                  f"CAGR={full['ann_ret']:+.2%}, Sharpe={full['sharpe']:.3f}, "
                  f"daily DD={full['daily_max_dd']:.2%}", flush=True)

    # Baseline return path must also match the production end-to-end build.
    native, _ = S.build_strategy(DI=di)
    pd.testing.assert_series_equal(returns["baseline", 10], native.loc[S.IS_START:last_signal])
    summary = pd.DataFrame(summaries)
    intervals = []
    for variant in VARIANTS[1:]:
        delta = returns[variant, 10] - returns["baseline", 10]
        for period, start, end in periods:
            sample = delta.loc[start:end]
            lo, hi = paired_interval(sample)
            intervals.append(dict(variant=variant, period=period,
                                  annualized_mean_difference=sample.mean() * 12,
                                  low_95=lo, high_95=hi))
    intervals = pd.DataFrame(intervals)

    OUT.mkdir(exist_ok=True)
    summary.to_csv(OUT / f"{PREFIX}_Summary.csv", index=False)
    events.to_csv(OUT / f"{PREFIX}_Decisions.csv", index=False, date_format="%Y-%m-%d")
    intervals.to_csv(OUT / f"{PREFIX}_Intervals.csv", index=False)
    pd.DataFrame({f"{variant}_{cost}bps": r for (variant, cost), r in returns.items()}).to_csv(
        OUT / f"{PREFIX}_Monthly_Returns.csv", index_label="earned_month")

    lines = [
        "# Known next-month rank: new-entry filter backtest",
        "", f"Research date: 2026-11-02. Cached ETF prices through {di['close'].index.max().date()}; "
        f"last complete signal month {last_signal.date()}.", "",
        "## Finding", "",
    ]
    primary = summary[(summary.variant == "retain_incumbent") & (summary.cost_bps == 10)
                      & (summary.period == "Full")].iloc[0]
    baseline = summary[(summary.variant == "baseline") & (summary.cost_bps == 10)
                       & (summary.period == "Full")].iloc[0]
    first_return = returns["baseline", 10].index.min()
    lines += [
        f"The primary filter reduced style-holding changes from {baseline.style_changes:.0f} "
        f"to {primary.style_changes:.0f}, but reduced net full-period CAGR from "
        f"{baseline.ann_ret:.2%} to {primary.ann_ret:.2%} and Sharpe from "
        f"{baseline.sharpe:.3f} to {primary.sharpe:.3f}. There were only "
        f"{primary.rejected_entries:.0f} rejected historical entries with executions "
        "in the cached sample. The filter helped modestly in the later period; "
        "the full-period paired interval spans zero. These results do not support "
        "adding the filter to production on performance grounds.", "",
        f"The inherited simulator's first reported monthly return is labelled "
        f"{first_return.date()}, and the last is labelled {last_signal.date()}. "
        "The latest label represents the completed October 30 trading close. "
        "The initial partial simulation month is omitted, matching production.", "",
        "## Rule fixed before examining results", "",
        "Keep the production 65% style / 35% sector strategy and its current leader-first "
        "style selection, cash hurdles, defensive choice, regime rules, and disabled throttle. "
        "Only a new style entry is screened. Reject the qualifying first-ranked candidate "
        "if its already-known next-month momentum rank is worse than 2. An existing holding "
        "is not screened merely because it is forecast to exit. Missing forecast ranks "
        "do not trigger rejection.", "",
        "Primary fallback: retain the previous style ETF only if it still ranks in the "
        "current top two and passes the current 6m OR 12m cash hurdle; otherwise use the "
        "production IEF-or-cash defensive choice. Secondary fallback sensitivity: a "
        "rejected entry goes directly to that defensive choice. Neither version chooses "
        "a different new lower-ranked ETF.", "",
        "The forecast is calculated from unshifted 3/6/12-month returns through the "
        "completed formation month. This equals the following month's ranking because "
        "the production ranking skips one month. No following-month ETF returns, cash "
        "hurdles, or realized holding durations are used by the filter. A next rank of "
        "2 is allowed even though the leader-first selector may replace it next month.", "",
        "Sector correlations and the congestion game are recalculated separately for "
        "each style path, including the changed 65% style exposure. Returns use the "
        "production daily simulator, next-trading-day closing execution, and cost per "
        "gross dollar traded, with buy and sell legs both charged. The primary cost "
        "is 10 bps; 0 and 25 bps are sensitivity checks, not optimized settings.", "",
        "## Net results at 10 bps per traded leg", "",
    ]
    result_rows = []
    for period, _, _ in periods:
        for variant in VARIANTS:
            row = summary[(summary.variant == variant) & (summary.cost_bps == 10)
                          & (summary.period == period)].iloc[0]
            result_rows.append([period, LABELS[variant], f"{row.ann_ret:.2%}",
                                f"{row.sharpe:.3f}", f"{row.daily_max_dd:.2%}",
                                int(row.rejected_entries), int(row.style_changes), int(row.n)])
    lines += [md_table(["Period", "Strategy", "CAGR", "Sharpe", "Daily max DD",
                        "Rejected entries", "Style changes", "Return months"], result_rows), "",
              "Rejection and style-change counts cover formation dates within each "
              "labelled period that have executions in the cached sample; they include "
              "defensive transitions and, for style changes, the initial allocation. The "
              "latest October 2026 signal has no November 2 execution or holding return "
              "in this data and is excluded from those counts. Sharpe is excess of "
              "the repository's T-bill series; drawdown uses daily NAV with the "
              "preceding period-end NAV included as the starting value.", "",
              "## Cost sensitivity, full period", ""]
    cost_rows = []
    for cost in COSTS:
        for variant in VARIANTS:
            row = summary[(summary.variant == variant) & (summary.cost_bps == cost)
                          & (summary.period == "Full")].iloc[0]
            cost_rows.append([cost, LABELS[variant], f"{row.ann_ret:.2%}", f"{row.sharpe:.3f}"])
    lines += [md_table(["Cost per leg (bps)", "Strategy", "CAGR", "Sharpe"], cost_rows),
              "", "## Paired uncertainty check", "",
              "Circular 12-month moving-block bootstrap, 10,000 resamples, seed "
              "20261102. Intervals describe the annualized arithmetic mean of paired "
              "monthly return differences at 10 bps, not a CAGR difference or a "
              "probability that a strategy is superior.", ""]
    lines.append(md_table(
        ["Variant minus baseline", "Period", "Annualized mean difference", "95% block interval"],
        [[LABELS[row.variant], row.period, f"{row.annualized_mean_difference:+.2%}",
          f"[{row.low_95:+.2%}, {row.high_95:+.2%}]"] for row in intervals.itertuples()]))
    lines += ["", "## Latest formation: decision only", ""]
    latest_rows = []
    for variant in VARIANTS:
        row = events[(events.variant == variant) & (events.formation == last_signal)].iloc[0]
        latest_rows.append([LABELS[variant], row.incumbent, row.candidate,
                            f"{row.known_next_rank:.0f}", row.rejected, row.selected])
    lines += [md_table(["Strategy", "Its own incumbent", "Candidate", "Known next rank",
                        "Rejected?", "Selected"], latest_rows), "",
              "Each counterfactual maintains its own incumbent history. Its latest "
              "holding is not necessarily what would result from adopting a new rule "
              "today while retaining the production account's current positions.", "",
              "## Verification and limits", "",
              "- The unfiltered research selector exactly matches the production "
              "style weights at every formation, and its net return path matches "
              "the end-to-end production strategy.",
              "- Forecasts exactly match the next ranking across the historical "
              "sample. Truncating all inputs at December 2018 and March 2020 leaves "
              "all earlier decisions unchanged. Hypothetical +30% and -30% next-month "
              "returns leave the forecast known today unchanged.",
              "- 2001-2018 is the repository's original development period. 2019+ "
              "is a later-period diagnostic, not a clean holdout: existing rules "
              "were examined against it, and this new question arose after observing "
              "the current QQQ signal. These are exploratory results, not fresh "
              "out-of-sample validation.",
              "- Inputs are the same cached adjusted-price and FRED histories for "
              "all variants, not a point-in-time vintage database. Historical "
              "revisions and original publication delays are not reconstructed.",
              "- The inherited simulator charges turnover across its position "
              "dictionary, including CASH changes, and its monthly-return series "
              "omits its initial partial month. These conventions are shared by "
              "all variants; the reported sample begins in 2001, after warm-up.",
              "- This study does not change production strategy parameters, submit "
              "orders, or automatically promote the research filter.", "",
              "## Reproduce", "", "```bash",
              "PYTHONDONTWRITEBYTECODE=1 python3 strategy/next_rank_entry_test.py", "```", "",
              "Input fingerprints:", ""]
    for filename in (S.CACHE_PRICES, S.CACHE_TBILL, str(Path(S.__file__))):
        digest = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
        lines.append(f"- `{Path(filename).relative_to(ROOT)}`: `{digest}`")
    report = OUT / f"{PREFIX}.md"
    report.write_text("\n".join(lines) + "\n")
    print("Verified production return baseline. Saved:", report, flush=True)
    print(summary[(summary.cost_bps == 10)][[
        "variant", "period", "ann_ret", "sharpe", "daily_max_dd", "rejected_entries"]].to_string(index=False))
    print(intervals.to_string(index=False))


if __name__ == "__main__":
    main()
