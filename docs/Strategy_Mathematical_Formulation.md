# Momentum Game Theory Strategy: Mathematical Formulation

## Purpose

This document describes the mathematics implemented by the production strategy.
It distinguishes the formulas actually used by the code from the surrounding
economic interpretation and research experiments.

The production implementation is in
[`strategy/strategy_lib.py`](../strategy/strategy_lib.py). The live signal and
execution programs import this implementation rather than reproducing the
strategy independently.

## 1. Portfolio structure

The strategy divides the portfolio into two sleeves:

- **Style sleeve:** 65% of capital.
- **Sector sleeve:** 35% of capital.

Before the optional volatility throttle, the complete target portfolio is

$$
\boxed{
W^{\mathrm{book}}_t
=
0.65W^{\mathrm{style}}_t
+
0.35W^{\mathrm{sector}}_t
}
$$

The weights inside each sleeve sum to one. Consequently, the two coefficients
above produce whole-portfolio weights.

## 2. Returns and momentum

Let $P_{i,t}$ be the adjusted month-end price of ETF $i$. Its monthly return is

$$
r_{i,t}=\frac{P_{i,t}}{P_{i,t-1}}-1.
$$

### 2.1 Ranking momentum

For each horizon $h\in\{3,6,12\}$, the ranking signal skips the most recent
month:

$$
M^{(h)}_{i,t}
=
\prod_{k=1}^{h}(1+r_{i,t-k})-1
=
\frac{P_{i,t-1}}{P_{i,t-h-1}}-1.
$$

The signal therefore measures the $h$ months ending one month before the
formation date.

This calculation is implemented by `mom(rets, skip=1, window=h)` in
[`strategy_lib.py`, lines 139--140](../strategy/strategy_lib.py#L139).

### 2.2 Cross-sectional standardization

For every horizon, momentum is standardized across the eligible ETFs at time
$t$:

$$
Z^{(h)}_{i,t}
=
\frac{M^{(h)}_{i,t}-\overline{M}^{(h)}_t}{s^{(h)}_t},
$$

where $\overline{M}^{(h)}_t$ is the cross-sectional mean and $s^{(h)}_t$ is the
cross-sectional sample standard deviation. Pandas uses a sample standard
deviation with `ddof=1` by default.

### 2.3 Composite momentum score

The score used by both production sleeves is the equal-weight average of the
three standardized signals:

$$
\boxed{
\mu_{i,t}
=
\frac{Z^{(3)}_{i,t}+Z^{(6)}_{i,t}+Z^{(12)}_{i,t}}{3}
}
$$

See [`strategy_lib.py`, lines 143--150](../strategy/strategy_lib.py#L143).

## 3. Style engine

The production style universe is

$$
\{\mathrm{SPY,QQQ,IWM,EFA,EEM,IWF,IWD}\}.
$$

Subject to the absolute-return hurdle below, the style engine selects the ETF
with the highest composite score:

$$
i_t^*=\operatorname*{arg\,max}_i\mu_{i,t}.
$$

### 3.1 Absolute-return hurdle

The hurdle uses unskipped returns, which include the current formation month:

$$
R^{(h)}_{i,t}
=
\prod_{k=0}^{h-1}(1+r_{i,t-k})-1.
$$

Let $R^{(h)}_{\mathrm{TB},t}$ denote the compounded T-bill return over the same
horizon. A style ETF qualifies when

$$
\boxed{
R^{(12)}_{i,t}>R^{(12)}_{\mathrm{TB},t}
\quad\lor\quad
R^{(6)}_{i,t}>R^{(6)}_{\mathrm{TB},t}
}
$$

The six-month condition permits faster re-entry after a decline. If no style
ETF qualifies, the sleeve moves to the defensive selection.

See [`strategy_lib.py`, lines 205--235](../strategy/strategy_lib.py#L205).

### 3.2 Defensive selection

The defensive asset is IEF only when its unskipped trailing twelve-month return
beats the compounded twelve-month T-bill return:

$$
D_t=
\begin{cases}
\mathrm{IEF}, & R^{(12)}_{\mathrm{IEF},t}>
R^{(12)}_{\mathrm{TB},t},\\
\mathrm{CASH}, & \text{otherwise}.
\end{cases}
$$

Notice that the defensive decision uses only the twelve-month hurdle, whereas
style ETFs may pass either the six- or twelve-month hurdle.

See [`strategy_lib.py`, lines 195--201](../strategy/strategy_lib.py#L195).

## 4. Sector congestion game

The sector universe contains eleven iShares U.S. sector ETFs:

$$
\{\mathrm{IYW,IYF,IYH,IYE,IYC,IYZ,IYK,IDU,IYM,IYJ,IYR}\}.
$$

The sector engine uses the main game-theory component of the strategy. Its goal
is to reward momentum while penalizing sectors that duplicate capital already
allocated to correlated exposures.

### 4.1 Correlation matrix

For every formation date, let $C_t$ be the sector correlation matrix estimated
from the most recent 126 daily-return rows:

$$
C_{ij,t}=\operatorname{Corr}_{126}(r_{i,d},r_{j,d}).
$$

The code replaces unavailable correlations with zero and explicitly sets every
diagonal entry to one.

See [`strategy_lib.py`, lines 292--298](../strategy/strategy_lib.py#L292).

### 4.2 Style-sleeve external crowding

The game also charges sectors for correlation with capital already held by the
65% style sleeve. Let $a$ index priced assets held inside the style sleeve, and
let $w^{\mathrm{style}}_{a,t}$ be their within-sleeve weights. The external
crowding term for sector $i$ is

$$
\boxed{
e_{i,t}
=
0.65
\sum_a
w^{\mathrm{style}}_{a,t}C_{ia,t}
}
$$

When the style sleeve holds one ETF at a within-sleeve weight of one, this
simplifies to

$$
e_{i,t}=0.65C_{i,a,t}.
$$

Cash has no return series and therefore contributes no correlation term. A
priced defensive holding such as IEF can contribute to the term.

See [`strategy_lib.py`, lines 299--305](../strategy/strategy_lib.py#L299).

### 4.3 Sector payoff

Let

- $\mu_t$ be the vector of sector composite-momentum scores;
- $w$ be the capital allocated across sectors by the game;
- $C_t$ be the trailing correlation matrix;
- $e_t$ be the fixed style-sleeve crowding vector; and
- $\lambda=8$ be the crowding-penalty coefficient.

The marginal payoff assigned to sector $i$ is

$$
\boxed{
u_i(w)
=
\mu_i
-
\lambda\left(\sum_j C_{ij}w_j+e_i\right)
}
$$

In vector form,

$$
\boxed{
u(w)=\mu-8(Cw+e)
}
$$

Thus,

$$
\text{sector payoff}
=
\text{standardized composite momentum}
-
8\times\text{correlated capital}.
$$

The penalty has two pieces:

1. $Cw$, representing crowding among the sectors; and
2. $e$, representing crowding against the style sleeve.

### 4.4 Potential function

The corresponding continuous capital-congestion potential function, including
the external term used by the production code, is

$$
\boxed{
\Phi(w)
=
\mu^\top w
-
\frac{\lambda}{2}w^\top Cw
-
\lambda e^\top w
}
$$

subject to

$$
w_i\geq0,
\qquad
\sum_i w_i=0.35.
$$

With $\lambda=8$,

$$
\Phi(w)=\mu^\top w-4w^\top Cw-8e^\top w.
$$

Its gradient is

$$
\nabla\Phi(w)=\mu-8(Cw+e),
$$

which is exactly the payoff vector calculated by the implementation.

### 4.5 Replicator-dynamics update

The implementation does not directly solve the constrained optimization
problem. It begins with the sector sleeve distributed equally:

$$
w_{i,0}=\frac{0.35}{N},
$$

where $N$ is the number of scoreable sectors. At iteration $n$, it calculates

$$
g_{i,n}=\mu_i-8(Cw_n+e)_i.
$$

It then applies the exponentiated replicator update

$$
\boxed{
w_{i,n+1}
=
0.35
\frac{
w_{i,n}\exp\left(0.1[g_{i,n}-\max_j g_{j,n}]\right)
}{
\sum_k w_{k,n}\exp\left(0.1[g_{k,n}-\max_j g_{j,n}]\right)
}
}
$$

The subtraction of $\max_j g_{j,n}$ provides numerical stability and does not
change the normalized result.

The locked parameters are:

| Parameter | Production value |
|---|---:|
| Crowding penalty, $\lambda$ | 8.0 |
| Replicator learning rate, $\eta$ | 0.1 |
| Iterations | 300 |
| Correlation observations | 126 daily rows |
| Capital distributed by the game | 35% |

See [`strategy_lib.py`, lines 239--266](../strategy/strategy_lib.py#L239).

The loop intentionally stops after exactly 300 iterations. The source comments
state that full numerical convergence takes approximately 3,400 iterations and
that changing the iteration count can change the selected sectors. Therefore,
the production output is best described as a **fixed, truncated replicator
state approximating an equilibrium**, rather than a fully converged solution.

## 5. Turning game weights into sector holdings

The final game weights are used to rank sectors; they are not used directly as
portfolio position sizes. Let

$$
q_{i,t}=\operatorname{rank}_{\mathrm{descending}}(w_{i,300,t}).
$$

The top-four entry set is

$$
E_t=\{i:q_{i,t}\leq4\}.
$$

Previously held sectors remain eligible while ranked in the top six:

$$
B_t=H_{t-1}\cap\{i:q_{i,t}\leq6\}.
$$

The code forms the selected set as

$$
\boxed{H_t=E_t\cup B_t}.
$$

It then assigns equal within-sleeve weights:

$$
w^{\mathrm{sector,final}}_{i,t}
=
\begin{cases}
1/|H_t|, & i\in H_t,\\
0, & \text{otherwise}.
\end{cases}
$$

The whole-book weight of selected sector $i$ is therefore

$$
W_{i,t}=0.35\,w^{\mathrm{sector,final}}_{i,t}.
$$

The central distinction is

$$
\boxed{\text{The congestion game selects sectors; it does not size them.}}
$$

See [`strategy_lib.py`, lines 306--313](../strategy/strategy_lib.py#L306).

## 6. Sector regime filter

The sector sleeve uses a two-threshold state machine. If it is currently
risk-on, it exits when SPY is not above its 231-trading-day moving average:

$$
P^{\mathrm{SPY}}_t\leq MA_{231,t}.
$$

Once risk-off, it re-enters only when SPY is above its 63-trading-day moving
average:

$$
P^{\mathrm{SPY}}_t>MA_{63,t}.
$$

During a risk-off state, the complete sector sleeve is assigned to the same
IEF-or-cash defensive selection defined in Section 3.2.

See [`strategy_lib.py`, lines 168--178](../strategy/strategy_lib.py#L168) and
[`strategy_lib.py`, lines 284--291](../strategy/strategy_lib.py#L284).

## 7. Optional volatility throttle

The throttle is disabled in the shipped strategy because `BOOK_VT = 0.0`.
The following formulas apply only if a positive target-volatility value is
configured.

Using the last 21 daily-return observations and the complete target portfolio,
annualized target-book volatility is

$$
\widehat{\sigma}_{p,t}
=
\operatorname{Std}_{21}
\left(\sum_i W_{i,t}r_{i,d}\right)\sqrt{252}.
$$

When SPY is below its 126-day moving average, risk positions are scaled by

$$
\boxed{
s_t=\min\left(1,\frac{\sigma_{\mathrm{target}}}
{\widehat{\sigma}_{p,t}}\right)
}.
$$

The capital removed from risk positions is transferred to that month's
defensive selection. The throttle never scales exposure above one.

See [`strategy_lib.py`, lines 357--383](../strategy/strategy_lib.py#L357).

## 8. Execution and transaction costs

Signals are formed at a completed month-end and executed at the following
trading day's close.

Let $V^{\mathrm{current}}_{i,t}$ and $V^{\mathrm{target}}_{i,t}$ be the dollar
values before and after rebalancing. Gross traded dollars are

$$
T_t
=
\sum_i
\left|
V^{\mathrm{target}}_{i,t}
-
V^{\mathrm{current}}_{i,t}
\right|.
$$

With a ten-basis-point cost per traded leg, the deduction is

$$
\boxed{
\operatorname{Cost}_t
=
T_t\frac{10}{10{,}000}
=
0.001T_t
}.
$$

Moving fully from one ETF to another includes both a sale and a purchase in
$T_t$.

See [`strategy_lib.py`, lines 384--439](../strategy/strategy_lib.py#L384).

## 9. Implementation observations

The following points describe the production code exactly and should be
considered when comparing it with the prose in `strategy/README.md`.

### 9.1 The sector sleeve can hold more than four sectors

The code unions all top-four entrants with previously held sectors that remain
in the top six:

```python
entry = set(ranked[ranked <= TOP_K].index)
hold = set(ranked[ranked <= BUFFER_EXIT].index)
held = sorted((cur_held & hold) | entry)
```

It does not truncate this union to four holdings. On the repository's cached
price history, risk-on months contain the following counts:

| Number of sectors | Number of cached formation months |
|---:|---:|
| 4 | 92 |
| 5 | 130 |
| 6 | 21 |

There are also 60 risk-off formation months containing no sector ETFs. Thus,
the implementation frequently holds five or six sectors even though the
documentation describes the sleeve as holding four.

### 9.2 The style top-two buffer does not retain a second-ranked incumbent

The style code creates a top-one entry set, unions it with an incumbent that
remains in the top two, sorts the union by rank, and finally keeps only its
highest-ranked member:

```python
held = sorted((cur_held & hold) | entry,
              key=lambda a: ranked[a])[:STYLE_K]
```

Because `STYLE_K` is one, a new first-ranked ETF displaces an incumbent that
has fallen to second. Consequently, the documented top-two incumbency buffer
does not delay that replacement in the current implementation.

## 10. Production parameter summary

| Component | Parameter | Value |
|---|---|---:|
| Book | Style allocation | 65% |
| Book | Sector allocation | 35% |
| Momentum | Ranking horizons | 3, 6 and 12 months |
| Momentum | Most recent ranking month | Skipped |
| Style hurdle | Absolute-return horizons | 6 or 12 months |
| Defensive hurdle | IEF comparison horizon | 12 months |
| Game | Crowding coefficient | 8.0 |
| Game | Daily correlation rows | 126 |
| Game | Replicator learning rate | 0.1 |
| Game | Replicator iterations | 300 |
| Sector selection | Entry rank | Top 4 |
| Sector selection | Incumbent eligibility | Top 6 |
| Regime | Exit moving average | 231 trading days |
| Regime | Re-entry moving average | 63 trading days |
| Throttle | Status | Disabled (`BOOK_VT = 0.0`) |
| Throttle | Volatility window, if enabled | 21 trading days |
| Throttle | Arming moving average | 126 trading days |
| Execution | Trading cost | 10 bps per traded leg |

## 11. Scope note

Research experiments do not alter the formulas above unless their changes are
explicitly moved into `strategy/strategy_lib.py`. The live programs currently
call the production functions documented here.
