"""Historical examples: selected style ETF just lost more than 5% in a month.

Run: PYTHONDONTWRITEBYTECODE=1 python3 strategy/bad_month_followthrough.py
Read-only with respect to production strategy, cached inputs, and broker state.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

import strategy_lib as S
from next_rank_entry_test import md_table, next_ranks


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"
PREFIX = "Bad_Month_Style_Followthrough"
THRESHOLD = -0.05


def collect_cases(di, style, returns, last):
    ranks = next_ranks(di["monthly"])
    days = di["close"].index
    cases, previous = [], set()
    for t, weights in sorted(style.items()):
        selected = set(weights.index) & set(S.STYLES)
        for ticker in sorted(selected):
            prior_return = float(di["monthly"].loc[t, ticker])
            following = t + pd.offsets.MonthEnd(1)
            if not (pd.Timestamp(S.IS_START) <= t <= last and prior_return < THRESHOLD):
                continue
            known_rank = float(ranks.loc[t, ticker])
            future_leaders = ranks.loc[t][ranks.loc[t] == 1].index
            resolved = bool(following <= last and following in returns.index)
            # Exact model execution window, supplied as a separate diagnostic.
            # Calendar-month returns below are the primary user-facing result.
            entry_i = days.searchsorted(t, side="right")
            exit_i = days.searchsorted(following, side="right")
            entry_date = days[entry_i] if entry_i < len(days) else pd.NaT
            exit_date = days[exit_i] if exit_i < len(days) else pd.NaT
            holding_return = np.nan
            if pd.notna(entry_date) and pd.notna(exit_date):
                holding_return = float(di["close"].loc[exit_date, ticker]
                                       / di["close"].loc[entry_date, ticker] - 1)
            cases.append(dict(
                formation=t, style_etf=ticker,
                previous_style_etf=",".join(sorted(previous)),
                new_entry=ticker not in previous,
                prior_month_return=prior_return,
                known_next_rank=known_rank,
                known_next_leader=future_leaders[0] if len(future_leaders) == 1 else None,
                known_next_outside_top_two=bool(known_rank > 2),
                following_month=following, outcome_observed=resolved,
                etf_following_calendar_return=(float(di["monthly"].loc[following, ticker])
                                               if resolved else np.nan),
                book_following_calendar_net_return=(float(returns.loc[following])
                                                    if resolved else np.nan),
                entry_close_date=entry_date, next_rebalance_close_date=exit_date,
                etf_execution_window_gross_return=holding_return,
            ))
        previous = selected
    return pd.DataFrame(cases)


def summarize(cases):
    observed = cases[cases.outcome_observed]
    groups = {
        "All selected style ETFs after a loss worse than 5%": observed,
        "New entries": observed[observed.new_entry],
        "Existing holdings": observed[~observed.new_entry],
        "QQQ: all": observed[observed.style_etf == "QQQ"],
        "QQQ: new entries": observed[(observed.style_etf == "QQQ") & observed.new_entry],
        "New entries with known next rank outside top two": observed[
            observed.new_entry & observed.known_next_outside_top_two],
    }
    rows = []
    for group, events in groups.items():
        etf = events.etf_following_calendar_return
        book = events.book_following_calendar_net_return
        rows.append(dict(
            group=group, cases=len(events), etf_positive=int((etf > 0).sum()),
            etf_mean=etf.mean(), etf_median=etf.median(), etf_worst=etf.min(), etf_best=etf.max(),
            book_positive=int((book > 0).sum()), book_mean=book.mean(),
            book_median=book.median(), book_worst=book.min(), book_best=book.max(),
        ))
    return pd.DataFrame(rows)


def event_table(events, include_state=True):
    rows = []
    for x in events.itertuples():
        row = [x.formation.strftime("%Y-%m"), x.style_etf]
        if include_state:
            row.append("New entry" if x.new_entry else "Already held")
        row += [f"{x.prior_month_return:+.2%}", x.following_month.strftime("%Y-%m"),
                f"{x.etf_following_calendar_return:+.2%}",
                f"{x.book_following_calendar_net_return:+.2%}"]
        rows.append(row)
    headers = ["Bad month / signal", "Selected ETF"]
    if include_state:
        headers.append("Selection")
    headers += ["ETF bad-month return", "Following month", "ETF following return (gross)",
                "Full strategy following return (net)"]
    return md_table(headers, rows)


def main():
    for filename in (S.CACHE_PRICES, S.CACHE_TBILL):
        if not Path(filename).exists():
            raise FileNotFoundError(f"Cached input required: {filename}")
    di = S.get_data(refresh=False)
    style = S.style_weight_path(di)
    sector = S.sector_weight_path(di, style)
    last = S.latest_formation(di, style, sector)
    book = S.combine_paths([(style, S.W_STYLE), (sector, S.W_SECTOR)])
    book = {t: w for t, w in book.items() if t <= last}
    returns, _ = S.simulate(book, di, cost_bps=10)
    returns = returns.loc[S.IS_START:last]
    native, _ = S.build_strategy(DI=di)
    pd.testing.assert_series_equal(returns, native.loc[S.IS_START:last])
    cases = collect_cases(di, style, returns, last)
    observed = cases[cases.outcome_observed]
    summary = summarize(cases)
    # Guard against mixing current/pending cases into the historical average.
    assert (observed.following_month <= last).all()
    assert (observed.prior_month_return < THRESHOLD).all()
    assert not observed[["etf_following_calendar_return",
                         "book_following_calendar_net_return"]].isna().any().any()
    for x in observed.itertuples():
        prior_prices = di["close"][x.style_etf].loc[:x.formation].resample("ME").last()
        calculated = float(prior_prices.iloc[-1] / prior_prices.iloc[-2] - 1)
        np.testing.assert_allclose(calculated, x.prior_month_return, rtol=1e-12, atol=1e-12)
    # Truncating the monthly and daily inputs does not alter which examples
    # qualified before that cutoff. Outcomes are evaluated only afterwards.
    cutoff = pd.Timestamp("2018-12-31")
    prefix_di = {key: value.loc[:cutoff] for key, value in di.items()}
    prefix_cases = collect_cases(prefix_di, S.style_weight_path(prefix_di),
                                 returns.loc[:cutoff], cutoff)
    columns = ["formation", "style_etf", "new_entry", "prior_month_return", "known_next_rank"]
    pd.testing.assert_frame_equal(
        cases[cases.formation <= cutoff][columns].reset_index(drop=True),
        prefix_cases[columns].reset_index(drop=True))

    OUT.mkdir(exist_ok=True)
    cases.to_csv(OUT / f"{PREFIX}_Cases.csv", index=False, date_format="%Y-%m-%d")
    summary.to_csv(OUT / f"{PREFIX}_Summary.csv", index=False)
    new = observed[observed.new_entry]
    qqq_new = new[new.style_etf == "QQQ"]
    all_stats = summary.iloc[0]
    new_stats = summary[summary.group == "New entries"].iloc[0]
    lines = [
        "# Style ETF losses worse than 5%: following-month examples", "",
        f"Research date: November 2, 2026. Cached prices through {di['close'].index.max().date()}. "
        f"Last completed signal month: {last.date()}.", "",
        "## Interpretation and result", "",
        "The requested threshold is interpreted as a monthly loss worse than -5%, "
        "matching QQQ's approximately -6.66% October return. It does not mean a "
        "return below positive 5%. The selected ETF is the one the model chooses "
        "at that bad month's end for the following month. The ETF need not have "
        "been held during the loss month. New entries and existing holdings are "
        "therefore shown separately; today is a proposed new QQQ entry from IWD.", "",
        f"There are {len(observed)} completed historical examples. The selected ETF "
        f"rose in {int(all_stats.etf_positive)}/{len(observed)} following calendar "
        f"months, averaging {all_stats.etf_mean:+.2%}; the full strategy rose in "
        f"{int(all_stats.book_positive)}/{len(observed)}, averaging {all_stats.book_mean:+.2%} net.", "",
        f"The closer new-entry subset has {len(new)} examples: ETF positive "
        f"{int(new_stats.etf_positive)}/{len(new)}, mean {new_stats.etf_mean:+.2%}; "
        f"full strategy positive {int(new_stats.book_positive)}/{len(new)}, mean "
        f"{new_stats.book_mean:+.2%} net. Only {len(qqq_new)} are new QQQ entries; "
        "they have opposing outcomes. The pattern does not consistently imply "
        "either a rebound or continued losses, and the closest sample is small.", "",
        "## Closest examples: new entries", "", event_table(new, include_state=False), "",
        "## All completed matching examples", "", event_table(observed), "",
        "## Cohort summaries", "",
    ]
    lines.append(md_table(
        ["Cohort", "Cases", "ETF positive", "ETF mean", "ETF median", "ETF worst",
         "Book positive", "Book mean net", "Book median net", "Book worst net"],
        [[x.group, x.cases, f"{x.etf_positive}/{x.cases}", f"{x.etf_mean:+.2%}",
          f"{x.etf_median:+.2%}", f"{x.etf_worst:+.2%}", f"{x.book_positive}/{x.cases}",
          f"{x.book_mean:+.2%}", f"{x.book_median:+.2%}", f"{x.book_worst:+.2%}"]
         for x in summary.itertuples()]))
    pending = cases[~cases.outcome_observed]
    lines += ["", "## Current / unresolved cases", ""]
    for x in pending.itertuples():
        lines.append(f"- {x.formation:%Y-%m}: {x.style_etf} returned "
                     f"{x.prior_month_return:+.2%}; selected for {x.following_month:%Y-%m}. "
                     f"New entry: {x.new_entry}. Known next rank: {x.known_next_rank:.0f}. "
                     "No following-month outcome exists in this dataset; excluded from averages.")
    lines += ["", "## Measurement and limits", "",
        "- ETF following-month returns are adjusted calendar-month total returns, "
        "before trading costs. They are returns on the ETF itself, not the 65% "
        "sleeve's weighted contribution to the portfolio.",
        "- Full-strategy returns are the production daily backtest aggregated to "
        "the following calendar month, net of 10 bps per traded leg. They include "
        "both sleeves, actual model execution at the first following trading day's "
        "close, weight drift, cash returns, and rebalancing costs. The old holdings "
        "remain exposed until that execution close. This is why the full-book "
        "return need not equal 65% of the ETF return plus a simple fixed sector return.",
        "- Calendar-month ETF returns differ from the exact first-trading-day-close "
        "to next-rebalance-close return. The CSV includes both the exact execution "
        "dates and that ETF-only gross execution-window return as a separate "
        "diagnostic when the exit close is available.",
        "- All matches are reported, including losses. Adjacent event months can "
        "belong to the same market episode and are not independent observations. "
        "The counts describe this history, not estimated probabilities for November 2026.",
        "- The cohort with a known next rank outside the top two is identified "
        "using information already available at formation. It is a descriptive "
        "subgroup, not a newly optimized strategy or an independent validation sample.",
        "- The study is motivated by today's QQQ signal. Existing strategy rules "
        "were also developed against historical data. This is exploratory, with "
        "cached revised prices/FRED data rather than point-in-time data vintages.",
        "- Verification: the portfolio returns exactly match production; all "
        "loss-month returns were independently reconstructed from cached prices; "
        "truncating future observations leaves the earlier qualifying cases unchanged.",
        "- No production selector, broker settings, or orders were changed.", "",
        "## Reproduce", "", "```bash",
        "PYTHONDONTWRITEBYTECODE=1 python3 strategy/bad_month_followthrough.py", "```", "",
        "Input and code fingerprints:", ""]
    for filename in (S.CACHE_PRICES, S.CACHE_TBILL, str(Path(S.__file__)), str(Path(__file__))):
        digest = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
        lines.append(f"- `{Path(filename).relative_to(ROOT)}`: `{digest}`")
    report = OUT / f"{PREFIX}.md"
    report.write_text("\n".join(lines) + "\n")
    print(summary.to_string(index=False), flush=True)
    print("\nClosest matches:")
    print(event_table(new, include_state=False))
    print("\nVerified production baseline, event returns, and chronological selection.")
    print("Saved:", report)


if __name__ == "__main__":
    main()
