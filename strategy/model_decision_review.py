"""Bounded research review of the current style decision and parameter stability.

Run: PYTHONDONTWRITEBYTECODE=1 python3 strategy/model_decision_review.py
Cached data only. Does not modify production code or connect to a broker.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

import strategy_lib as S
import volatility_leader_test as V
from next_rank_entry_test import assert_paths_equal, md_table, next_ranks, period_nav


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"
PREFIX = "Style_Decision_Review"
COSTS = (0, 10, 25)
# Fixed as a bounded family before running this review's return comparisons.
# The question and several families are already informed by earlier studies.
CONFIGS = {
    "baseline": {},
    "true_top2_buffer": {"policy": "buffer"},
    "top2_equal": {"policy": "top2"},
    "ranking_skip0": {"skip": 0},
    "rank_3_only": {"horizons": (3,)},
    "rank_6_only": {"horizons": (6,)},
    "rank_12_only": {"horizons": (12,)},
    "rank_3_12_drop6": {"horizons": (3, 12)},
    "rank_6_12_drop3": {"horizons": (6, 12)},
    "rank_3_6_drop12": {"horizons": (3, 6)},
    "six_weight_1_6": {"score_weights": (5/12, 1/6, 5/12)},
    "six_weight_1_2": {"score_weights": (1/4, 1/2, 1/4)},
    "reject_new_loss3": {"policy": "reject_loss", "threshold": -0.03},
    "reject_new_loss5": {"policy": "reject_loss", "threshold": -0.05},
    "reject_new_loss7p5": {"policy": "reject_loss", "threshold": -0.075},
    "defensive_after_loss5": {"policy": "defensive_loss", "threshold": -0.05},
    "defensive_after_loss7p5": {"policy": "defensive_loss", "threshold": -0.075},
    "advance_after_loss3": {"policy": "advance_loss", "threshold": -0.03},
    "advance_after_loss5": {"policy": "advance_loss", "threshold": -0.05},
    "advance_after_loss7p5": {"policy": "advance_loss", "threshold": -0.075},
    "reject_known_next_outside2": {"policy": "reject_next"},
    "advance_vol15": {"vol_policy": "advance_candidate_15"},
    "advance_vol20": {"vol_policy": "advance_candidate_20"},
    "advance_vol25": {"vol_policy": "advance_candidate_25"},
    "retain_next_incumbent_vol20": {"vol_policy": "retain_next_incumbent_20"},
    "advance_always": {"vol_policy": "advance_always"},
    "style_weight35": {"w_style": 0.35},
    "style_weight50": {"w_style": 0.50},
    "style_weight80": {"w_style": 0.80},
    "restore_throttle15": {"book_vt": 0.15},
    "restore_throttle20": {"book_vt": 0.20},
}
FEATURES = {
    "market": ["prior_return", "asset_vol", "spy_return", "spy_vol"],
    "combined": ["prior_return", "asset_vol", "spy_return", "spy_vol",
                 "score", "six_carry", "excess12", "known_next_rank"],
}


def style_path(di, config):
    if "vol_policy" in config:
        return V.style_path(di, config["vol_policy"])[0]
    horizons = config.get("horizons", (3, 6, 12))
    fractions = config.get("score_weights", (1/len(horizons),)*len(horizons))
    scores = sum(fraction*S.cs_z(S.mom(di["monthly"][S.STYLES], config.get("skip", 1), horizon))
                 for horizon, fraction in zip(horizons, fractions))
    projected = next_ranks(di["monthly"])
    policy = config.get("policy", "baseline")
    out, incumbent = {}, set()
    for t in scores.index:
        row = scores.loc[t].dropna()
        if len(row) < 3:
            continue
        ranked = row.rank(ascending=False)
        tb6, tb12 = di["tbill6"].get(t, np.nan), di["tbill12"].get(t, np.nan)
        passing = {
            a for a in row.index
            if (not np.isnan(tb6) and di["tot6"].loc[t, a] > tb6)
            or (not np.isnan(tb12) and di["tot12"].loc[t, a] > tb12)
        }
        entry = {a for a in row.index if ranked[a] <= 1 and a in passing}
        hold = {a for a in row.index if ranked[a] <= 2 and a in passing}
        keep = incumbent & hold
        candidate = min(entry, key=lambda a: ranked[a]) if entry else None
        if policy == "buffer" and keep:
            held = sorted(keep, key=lambda a: ranked[a])[:1]
        elif policy == "top2":
            held = sorted(hold, key=lambda a: ranked[a])
        else:
            if candidate and candidate not in incumbent:
                veto = ((policy == "reject_loss" and
                         di["monthly"].loc[t, candidate] < config["threshold"])
                        or (policy == "reject_next" and projected.loc[t, candidate] > 2))
                if veto:
                    entry = set()
            held = sorted(keep | entry, key=lambda a: ranked[a])[:1]
        if policy == "defensive_loss" and held:
            if di["monthly"].loc[t, held[0]] < config["threshold"]:
                held = []
        if policy == "advance_loss" and candidate:
            future = projected.loc[t][projected.loc[t] == 1].index
            if len(future) == 1 and future[0] in passing:
                if di["monthly"].loc[t, candidate] < config["threshold"]:
                    held = [future[0]]
        out[t] = (pd.Series(1/len(held), index=held, dtype=float) if held
                  else pd.Series({S.pick_defensive(di, t): 1.0}))
        incumbent = set(held)
    return out


def signal_features(di, style, returns, last):
    parts = {h: S.cs_z(S.mom(di["monthly"][S.STYLES], 1, h)) for h in (3,6,12)}
    vol = V.volatility(di)
    projected = next_ranks(di["monthly"])
    rows, previous = [], set()
    for t, weights in sorted(style.items()):
        selected = set(weights.index) & set(S.STYLES)
        for ticker in sorted(selected):
            if not (pd.Timestamp(S.IS_START) <= t <= last):
                continue
            z = [parts[h].loc[t, ticker] for h in (3,6,12)]
            following = t + pd.offsets.MonthEnd(1)
            resolved = following <= last and following in returns.index
            rows.append(dict(formation=t, etf=ticker, new_entry=ticker not in previous,
                             prior_return=di["monthly"].loc[t,ticker], asset_vol=vol.loc[t,ticker],
                             spy_return=di["monthly"].loc[t,"SPY"], spy_vol=vol.loc[t,"SPY"],
                             score=sum(z)/3, six_carry=z[1]-(z[0]+z[2])/2,
                             excess12=di["tot12"].loc[t,ticker]-di["tbill12"].get(t),
                             known_next_rank=projected.loc[t,ticker],
                             following_month=following,
                             etf_following=(di["monthly"].loc[following,ticker] if resolved else np.nan),
                             book_following=(returns.loc[following] if resolved else np.nan)))
        previous = selected
    return pd.DataFrame(rows)


def nearest_examples(features, last):
    target = features[features.formation == last].iloc[0]
    history = features[(features.formation < last) & features.book_following.notna()].copy()
    cohorts = {
        "all_bad": history.prior_return < -0.05,
        "QQQ_bad": (history.etf == target.etf) & (history.prior_return < -0.05),
        "new_bad": history.new_entry & (history.prior_return < -0.05),
        "new_QQQ_bad": history.new_entry & (history.etf == target.etf) & (history.prior_return < -0.05),
    }
    records = []
    for metric, columns in FEATURES.items():
        # Scale each feature using preceding signal observations; no following
        # returns, outcome direction, or nearest-neighbor profits enter distance.
        scale = history[columns].std().replace(0, 1)
        distance = ((history[columns]-target[columns])/scale).pow(2).mean(axis=1).pow(0.5)
        for cohort, mask in cohorts.items():
            sample = history[mask].copy()
            sample["distance"] = distance[mask]
            sample = sample.sort_values(["distance", "formation"])
            for rank, row in enumerate(sample.to_dict("records"), 1):
                records.append(dict(metric=metric, cohort=cohort, neighbor_rank=rank, **row))
    return pd.DataFrame(records), target


def family_intervals(deltas, draws=10_000):
    """Paired 12-month block bootstrap, marginal and simultaneous mean bands."""
    values = deltas.to_numpy()
    n, m = values.shape
    rng = np.random.default_rng(20261102)
    starts = rng.integers(0,n,size=(draws,(n+11)//12))
    indices = ((starts[:,:,None]+np.arange(12)) % n).reshape(draws,-1)[:,:n]
    estimates = np.empty((draws,m))
    for j in range(m):
        estimates[:,j] = values[indices,j].mean(axis=1)*12
    observed = values.mean(axis=0)*12
    lo, hi = np.quantile(estimates,[0.025,0.975],axis=0)
    common_width = np.quantile(np.abs(estimates-observed).max(axis=1),0.95)
    return pd.DataFrame(dict(variant=deltas.columns,
                             annualized_mean_difference=observed,
                             marginal_low95=lo, marginal_high95=hi,
                             family_low95=observed-common_width,
                             family_high95=observed+common_width))


def sharpe_intervals(returns, rf, draws=10_000):
    """Risk-adjusted comparison using the same paired time-block resamples."""
    baseline = returns["baseline"]
    risk_free = rf.reindex(baseline.index).fillna(0).to_numpy()
    n = len(baseline)
    rng = np.random.default_rng(20261102)
    starts = rng.integers(0,n,size=(draws,(n+11)//12))
    indices = ((starts[:,:,None]+np.arange(12)) % n).reshape(draws,-1)[:,:n]
    rf_samples = risk_free[indices]

    def sampled_sharpe(values):
        sample = values[indices]
        return ((sample-rf_samples).mean(axis=1)*np.sqrt(12)
                / sample.std(axis=1,ddof=1))

    base_samples = sampled_sharpe(baseline.to_numpy())
    base_sharpe = S.metrics(baseline,rf=rf)["sharpe"]
    names = [name for name in returns if name != "baseline"]
    estimates = np.column_stack([sampled_sharpe(returns[name].to_numpy())-base_samples
                                for name in names])
    observed = np.array([S.metrics(returns[name],rf=rf)["sharpe"]-base_sharpe for name in names])
    lo,hi = np.quantile(estimates,[0.025,0.975],axis=0)
    width = np.quantile(np.abs(estimates-observed).max(axis=1),0.95)
    return pd.DataFrame(dict(variant=names,sharpe_difference=observed,
                             marginal_low95=lo,marginal_high95=hi,
                             family_low95=observed-width,family_high95=observed+width))


def adaptive_targets(books, returns, rf):
    """Choose an expert once a year using only the preceding 60 net months.

    Each expert keeps its own counterfactual state. Selected full-book targets
    are passed to the production simulator, which charges actual transitions.
    This is a historical diagnostic, not a clean validation of these families.
    """
    chosen, targets, log = "baseline", {}, []
    for t in sorted(books["baseline"]):
        if t.month == 12 and t.year >= 2009:
            scores = {}
            for variant, r in returns.items():
                training = r.loc[:t].tail(60)
                if len(training) == 60:
                    scores[variant] = S.metrics(training, rf=rf)["sharpe"]
            if scores:
                chosen = max(scores, key=lambda name: (scores[name], name == "baseline", name))
                log.append(dict(formation=t, holding_year=t.year+1, selected=chosen,
                                training_sharpe=scores[chosen],
                                baseline_training_sharpe=scores["baseline"],
                                training_through=returns[chosen].loc[:t].index[-1]))
        targets[t] = books[chosen][t]
    return targets, pd.DataFrame(log)


def main():
    for filename in (S.CACHE_PRICES,S.CACHE_TBILL):
        if not Path(filename).exists():
            raise FileNotFoundError(filename)
    di = S.get_data(refresh=False)
    styles = {name:style_path(di,config) for name,config in CONFIGS.items()}
    assert_paths_equal(styles["baseline"],S.style_weight_path(di))
    # Every policy's decisions must remain unchanged when future data vanish.
    for cutoff in (pd.Timestamp("2018-12-31"),pd.Timestamp("2020-03-31")):
        prefix = {key:value.loc[:cutoff] for key,value in di.items()}
        for name,config in CONFIGS.items():
            assert_paths_equal(style_path(prefix,config),
                               {t:w for t,w in styles[name].items() if t <= cutoff})
    print(f"Verified all {len(CONFIGS)} selector configurations and causal prefixes.",flush=True)

    last = S.latest_formation(di,styles["baseline"],S.sector_weight_path(di,styles["baseline"]))
    periods = (("2001-2018",S.IS_START,S.IS_END),
               ("2019-latest","2019-01-01",str(last.date())),
               ("Full",S.IS_START,str(last.date())),
               ("2010-latest","2010-01-01",str(last.date())))
    books, monthly, summaries, targets = {}, {}, [], []
    sector_cache = {}
    for name,config in CONFIGS.items():
        style = styles[name]
        ws = config.get("w_style",S.W_STYLE)
        wt = config.get("book_vt",S.BOOK_VT)
        signature = (ws,tuple((t,tuple(sorted(w.items()))) for t,w in sorted(style.items())))
        if signature not in sector_cache:
            sector_cache[signature] = S.sector_weight_path(di,style,w_style=ws,w_sector=1-ws)
        sector = sector_cache[signature]
        book = S.combine_paths([(style,ws),(sector,1-ws)])
        book = {t:S.throttle_target(di,w.copy(),t,wt) for t,w in book.items() if t <= last}
        books[name] = book
        targets.append(dict(variant=name,selected_style=",".join(style[last].index),
                            style_weights=json.dumps(style[last].to_dict(),sort_keys=True),
                            full_book=json.dumps(book[last].to_dict(),sort_keys=True)))
        for cost in COSTS:
            r,sim = S.simulate(book,di,cost_bps=cost,book_vt=0)
            r = r.loc[S.IS_START:last]
            if monthly:
                assert r.index.equals(monthly["baseline",0].index)
            monthly[name,cost] = r
            for label,start,end in periods:
                metrics = S.metrics(r,S.in_sample_mask(r.index,start,end),rf=di["tbill_m"])
                dd = S.drawdown_stats(equity=period_nav(sim["nav"],start,end))["max_dd"]
                summaries.append(dict(variant=name,cost_bps=cost,period=label,
                                      **metrics,daily_max_dd=dd,
                                      ann_turnover_entire_simulation=sim["ann_turnover"]))
        x = next(row for row in summaries if row["variant"]==name and row["cost_bps"]==10 and row["period"]=="Full")
        print(f"{name:<29} CAGR {x['ann_ret']:.2%}, Sharpe {x['sharpe']:.3f}, "
              f"daily DD {x['daily_max_dd']:.2%}; now {targets[-1]['selected_style']}",flush=True)
    native,_=S.build_strategy(DI=di)
    pd.testing.assert_series_equal(monthly["baseline",10],native.loc[S.IS_START:last])

    adaptive, selection_log = adaptive_targets(
        books,{name:monthly[name,10] for name in CONFIGS},di["tbill_m"])
    for cost in COSTS:
        r,sim=S.simulate(adaptive,di,cost_bps=cost,book_vt=0)
        r=r.loc[S.IS_START:last]
        monthly["annual_selection_60m",cost]=r
        for label,start,end in periods:
            metrics=S.metrics(r,S.in_sample_mask(r.index,start,end),rf=di["tbill_m"])
            dd=S.drawdown_stats(equity=period_nav(sim["nav"],start,end))["max_dd"]
            summaries.append(dict(variant="annual_selection_60m",cost_bps=cost,period=label,
                                  **metrics,daily_max_dd=dd,
                                  ann_turnover_entire_simulation=sim["ann_turnover"]))
    assert (selection_log.training_through <= selection_log.formation).all()
    summary=pd.DataFrame(summaries)
    features=signal_features(di,styles["baseline"],monthly["baseline",10],last)
    neighbors,current=nearest_examples(features,last)
    # Similarity rankings cannot use the sign or size of future returns.
    scrambled=features.copy()
    for column in ("etf_following","book_following"):
        observed=scrambled[column].notna()
        scrambled.loc[observed,column]=scrambled.loc[observed,column].iloc[::-1].to_numpy()
    other,_=nearest_examples(scrambled,last)
    pd.testing.assert_frame_equal(neighbors[["metric","cohort","formation","distance"]],
                                  other[["metric","cohort","formation","distance"]])
    differences=pd.DataFrame({name:monthly[name,10]-monthly["baseline",10]
                              for name in CONFIGS if name!="baseline"})
    intervals=family_intervals(differences)
    risk_intervals=sharpe_intervals({name:monthly[name,10] for name in CONFIGS},di["tbill_m"])
    # Neighbor summaries include all fixed k choices, rather than choosing k
    # according to the sign of their outcomes.
    neighbor_summary=[]
    for (metric,cohort),group in neighbors.groupby(["metric","cohort"]):
        for k in (1,3,5,10):
            selected=group[group.neighbor_rank<=k]
            neighbor_summary.append(dict(metric=metric,cohort=cohort,k_requested=k,n=len(selected),
                etf_mean=selected.etf_following.mean(),etf_median=selected.etf_following.median(),
                book_mean=selected.book_following.mean(),book_median=selected.book_following.median()))
    OUT.mkdir(exist_ok=True)
    outputs={"Summary":summary,"Neighbors":neighbors,"Neighbor_Summaries":pd.DataFrame(neighbor_summary),
             "Similarity_Features":features,"Family_Intervals":intervals,
             "Sharpe_Intervals":risk_intervals,
             "Annual_Selections":selection_log,"Current_Targets":pd.DataFrame(targets)}
    for suffix,data in outputs.items():
        data.to_csv(OUT/f"{PREFIX}_{suffix}.csv",index=False,date_format="%Y-%m-%d")
    pd.DataFrame({f"{name}_{cost}bps":r for (name,cost),r in monthly.items()}).to_csv(
        OUT/f"{PREFIX}_Monthly_Returns.csv",index_label="earned_month")
    (OUT/f"{PREFIX}_Configurations.json").write_text(json.dumps(CONFIGS,indent=2)+"\n")
    write_report(di,last,current,neighbors,summary,intervals,risk_intervals,selection_log)
    print("\nFULL RESULTS AT 10 BPS:")
    print(summary[(summary.cost_bps==10)&(summary.period=="Full")][[
        "variant","ann_ret","sharpe","daily_max_dd"]].sort_values("sharpe",ascending=False).to_string(index=False))
    print("\nAnnual selection choices:",selection_log.selected.value_counts().to_dict())
    print("Saved",OUT/f"{PREFIX}.md",flush=True)


def write_report(di,last,current,neighbors,summary,intervals,risk_intervals,selection_log):
    def stats(name,period="Full",cost=10):
        return summary[(summary.variant==name)&(summary.period==period)&(summary.cost_bps==cost)].iloc[0]
    full=summary[(summary.cost_bps==10)&(summary.period=="Full")]
    fixed=full[full.variant!="annual_selection_60m"]
    best=fixed.sort_values("sharpe",ascending=False).iloc[0]
    train=summary[(summary.cost_bps==10)&(summary.period=="2001-2018")
                  &(summary.variant!="annual_selection_60m")].sort_values("sharpe",ascending=False).iloc[0]
    base=stats("baseline")
    balanced=stats("style_weight50")
    lines=["# Current style decision: analogues and bounded parameter review","",
           f"Research date: November 2, 2026. Cached prices through {di['close'].index.max().date()}; "
           f"current signal {last.date()}. {len(CONFIGS)} fixed configurations, three cost "
           "levels, plus a historical annual-selection diagnostic. Production is unchanged.","",
           "## Findings and decision", "",
           "The expanded tests do not provide a strong basis for overriding today's "
           "QQQ selection or rewriting entry rules around this trade. True incumbent "
           "retention, dropping six-month momentum, skipping no month, and rejecting "
           "new entries after a 5% loss all reduced full-period CAGR and Sharpe. "
           "Some more severe 7.5% rules showed tiny retrospective improvements; "
           "they would still select QQQ today and do not establish a robust new rule.", "",
           f"The separate sizing result is promising: 50% style / 50% sector "
           f"allocation produced CAGR {balanced.ann_ret:.2%} versus {base.ann_ret:.2%}, "
           f"Sharpe {balanced.sharpe:.3f} versus {base.sharpe:.3f}, annualized volatility "
           f"{balanced.ann_vol:.2%} versus {base.ann_vol:.2%}, and daily max drawdown "
           f"{balanced.daily_max_dd:.2%} versus {base.daily_max_dd:.2%}. It also improved "
           "Sharpe in both the 2001-2018 and 2019+ comparisons. It still selects QQQ, "
           "but reduces the style allocation. This is a candidate for separate "
           "risk-budget review and forward paper tracking, not a demonstrated "
           "advantage from replacing QQQ with IWD for November.", "",
           "Keep the current signal rules for the existing paper test. Do not "
           "automatically promote a retrospective winner or alter pending orders "
           "from this research. Similarity examples do not settle the next return; "
           "sizing and confidence in the forecast are separate decisions.", "",
           "## Closest historical examples","",
           "There is no unique historical repeat. Similarity is computed without "
           "using subsequent returns. Market distance uses selected ETF monthly "
           "return and 21-day annualized volatility, SPY monthly return, and SPY "
           "volatility. Combined distance adds the selected ETF's skipped momentum "
           "score, six-month component dominance, unskipped twelve-month excess "
           "return over cash, and its already-known next-month rank. Each feature "
           "is divided by its standard deviation across preceding selected-style "
           "observations; distance is equal-weight root-mean-square standardized "
           "difference. These feature weights are subjective, not a validated forecast.","",
           "Candidates must have lost more than 5% in the signal month and have "
           "an observed following calendar month. Cohorts distinguish all styles, "
           "QQQ only, new entries, and new QQQ entries. The current QQQ month has "
           "no following-month outcome and is excluded.",""]
    closest=neighbors[neighbors.neighbor_rank==1]
    lines.append(md_table(
        ["Metric","Cohort","Closest signal month","ETF","New entry?","ETF prior month",
         "ETF following month (gross)","Full book following month (net)"],
        [[x.metric,x.cohort,x.formation.strftime("%Y-%m"),x.etf,x.new_entry,
          f"{x.prior_return:+.2%}",f"{x.etf_following:+.2%}",f"{x.book_following:+.2%}"]
         for x in closest.itertuples()]))
    lines += ["","All neighbors, feature values, distances, and fixed k=1/3/5/10 "
              "summaries are saved in the CSV artifacts. A nearest case is an "
              "example, not an estimate that the same outcome will recur.","",
              "## Parameter comparisons","",
              "The bounded family includes true top-two incumbent retention; "
              "equal-weight top-two selection; skipping zero rather than one "
              "month; single-horizon and leave-one-horizon-out momentum; six-month "
              "score weights of 1/6 and 1/2; new-entry loss filters at -3%, -5%, "
              "and -7.5%; defensive exits after -5% or -7.5%; early use of the "
              "next leader after those three losses; the known-next-rank veto; "
              "15/20/25% candidate-volatility overrides; conditional incumbent "
              "retention; unconditional early use of the next leader; style "
              "allocation weights of 35%, 50%, and 80%; and restoring the "
              "existing 15% or 20% volatility throttle. Full definitions are in "
              "the saved configuration JSON and research source.","",
              "New-entry loss vetoes retain an eligible current-top-two incumbent "
              "that passes today's cash hurdle, or use the existing defensive "
              "choice. Defensive-loss rules move the selected style holding to "
              "that defensive choice after a qualifying monthly loss. Early-leader "
              "rules require the alternate leader to pass today's hurdle. Top-two "
              "equal weighting chooses only current top-two ETFs that pass; if "
              "only one passes it receives the whole style allocation. No model "
              "uses future cash hurdles or future prices to choose a position.","",
              "Sector selections are recalculated for every style path and sleeve "
              "weight. Portfolio costs, drift, defensive/cash returns, and execution "
              "at the next trading day's close use the production simulator.","",
              "### Full period, net 10 bps per traded leg",""]
    lines.append(md_table(
        ["Configuration","CAGR","Sharpe","Daily max DD"],
        [[x.variant,f"{x.ann_ret:.2%}",f"{x.sharpe:.3f}",f"{x.daily_max_dd:.2%}"]
         for x in fixed.sort_values("sharpe",ascending=False).itertuples()]))
    lines += ["","The largest full-history Sharpe is not an automatic deployment "
              "choice. This search was motivated by today's uncomfortable QQQ "
              "trade and includes related families examined earlier in the session. "
              "Repeatedly testing historical data can select noise. "
              "[Bailey et al., The Probability of Backtest Overfitting]"
              "(https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)","",
              "### Temporal stability", "",
              f"Highest full-history Sharpe: `{best.variant}`. Highest 2001-2018 "
              f"Sharpe: `{train.variant}`. All later periods below are diagnostics, "
              "not clean holdouts: this research and existing rules already use "
              "knowledge of the history.",""]
    show=list(dict.fromkeys(["baseline",best.variant,train.variant,"style_weight50","true_top2_buffer",
                             "rank_3_12_drop6","reject_new_loss5","annual_selection_60m"]))
    rows=[]
    for period in ("2001-2018","2019-latest","2010-latest"):
        for name in show:
            x=stats(name,period)
            rows.append([period,name,f"{x.ann_ret:.2%}",f"{x.sharpe:.3f}",f"{x.daily_max_dd:.2%}"])
    lines += [md_table(["Period","Configuration","CAGR","Sharpe","Daily max DD"],rows),"",
              "Annual-selection diagnostic: from the December 2009 formation, "
              "choose one configuration each December using its preceding 60 "
              "monthly net returns' Sharpe. Each simulated expert maintains its "
              "own state; actual selected full-book targets are re-simulated, "
              "including the cost of switching between experts. Selection for "
              "2010 onward uses data only through the preceding December. Before "
              "2010 it follows baseline. This remains a retrospective diagnostic "
              "of an already-selected candidate family.","",
              "## Uncertainty and the number of tests", "",
              "Paired circular 12-month block bootstrap, 10,000 draws, seed "
              "20261102. Marginal intervals and a common-width simultaneous "
              "95% band for all fixed variants' annualized arithmetic mean "
              "return differences versus baseline are saved. The simultaneous "
              "band uses the 95th percentile of the largest absolute centered "
              "bootstrap error across the fixed family. This addresses this "
              "bounded family, not every earlier research choice or data "
              "revision, and is not a formal estimate of backtest-overfitting "
              "probability. It is also not a confidence interval for CAGR "
              "or Sharpe.",""]
    rows=[]
    for name in show:
        x=intervals[intervals.variant==name]
        if x.empty:
            continue
        x=x.iloc[0]
        rows.append([name,f"{x.annualized_mean_difference:+.2%}",
                     f"[{x.marginal_low95:+.2%}, {x.marginal_high95:+.2%}]",
                     f"[{x.family_low95:+.2%}, {x.family_high95:+.2%}]"])
    lines += [md_table(["Variant minus baseline","Annualized mean difference",
                        "Marginal 95% interval","Family 95% band"],rows),"",
              "Return-difference intervals do not test the lower-volatility or "
              "higher-Sharpe hypothesis. That comparison is assessed separately "
              "using the same paired blocks below. Sharpe differences are in "
              "Sharpe units, with a separate simultaneous band across the same "
              "fixed configuration family.", ""]
    risk_rows=[]
    for name in show:
        row=risk_intervals[risk_intervals.variant==name]
        if row.empty:
            continue
        x=row.iloc[0]
        risk_rows.append([name,f"{x.sharpe_difference:+.3f}",
                          f"[{x.marginal_low95:+.3f}, {x.marginal_high95:+.3f}]",
                          f"[{x.family_low95:+.3f}, {x.family_high95:+.3f}]"])
    lines += [md_table(["Variant minus baseline", "Sharpe difference", "Marginal 95% interval",
                        "Family 95% band"],risk_rows), "",
              "## Verification and limits", "",
              "- Baseline weights and returns exactly match production. Every "
              "configuration's earlier weights survive removing data after "
              "December 2018 and March 2020.",
              "- Permuting subsequent outcomes leaves the similarity rankings "
              "unchanged; no future outcomes enter neighbor distances.",
              "- Cached adjusted prices and FRED data are not original historical "
              "vintages. Original publication delays and revisions are not reconstructed.",
              "- Costs are checked at 0, 10, and 25 bps per leg. The inherited "
              "simulator charges CASH changes too and omits its initial partial "
              "month; all variants share those conventions. The common monthly "
              "sample starts in September 2001 and ends in October 2026.",
              "- No return from November 2026 is present. The research cannot "
              "determine whether QQQ or IWD will be the better November holding.",
              "- No strategy parameter, broker setting, position, or order was changed.","",
              "## Reproduce","","```bash",
              "PYTHONDONTWRITEBYTECODE=1 python3 strategy/model_decision_review.py","```","",
              "Input and code fingerprints:",""]
    for filename in (S.CACHE_PRICES,S.CACHE_TBILL,str(Path(S.__file__)),str(Path(__file__)),
                     str(Path(V.__file__)),str(Path(__file__).with_name("next_rank_entry_test.py"))):
        lines.append(f"- `{Path(filename).relative_to(ROOT)}`: "
                     f"`{hashlib.sha256(Path(filename).read_bytes()).hexdigest()}`")
    (OUT/f"{PREFIX}.md").write_text("\n".join(lines)+"\n")


if __name__=="__main__":
    main()
