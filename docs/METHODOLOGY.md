# Methodology

This document describes how Rafta answers its research question, in enough detail to reproduce the experiment or reuse it in a thesis chapter.

> **RQ.** For an SME with hundreds of SKUs, does an ABC-differentiated cycle-service policy achieve lower total inventory cost and fewer stock-outs than a uniform service policy?

## 1. Data

Inputs are three CSV files: product master data, daily sales and a stock snapshot ([api/app/services/ingest.py](../api/app/services/ingest.py)). Sales are pivoted into a dense daily demand matrix with zero-filled days.

The bundled dataset ([api/app/services/synthetic.py](../api/app/services/synthetic.py)) simulates a home and kitchen retailer: 150 SKUs over 730 days. Demand follows six patterns: smooth, weekly-seasonal, yearly-seasonal, trending, intermittent and promotional. It is drawn from over-dispersed (gamma–Poisson) processes, with log-normal prices and volumes so that revenue concentration is Pareto-like. Lead times range from 3 to 21 days, with 0–30% variability.

*Limitation:* synthetic data has known properties. Before drawing business conclusions, validate on a real dataset, such as the M5 competition data aggregated to one store or a partner company's POS export.

## 2. Classification

* **ABC.** SKUs are ranked by revenue over the last 365 days. An SKU is A if the cumulative revenue share *before* it is below 80%, and B below 95%; otherwise it is C. Using the share *before* the SKU guarantees at least one A item and avoids off-by-one errors at the boundary.
* **XYZ.** Coefficient of variation of **weekly** demand, using complete weeks only. Partial edge weeks inflate the CV, a bug caught by a unit test. X ≤ 0.5 < Y ≤ 1.0 < Z.
* The average demand interval (ADI) is also stored to flag intermittent SKUs.

## 3. Forecasting and backtesting

Models ([api/app/services/forecasting.py](../api/app/services/forecasting.py)):

| Model | Notes |
|---|---|
| Seasonal naive (7-day) | Benchmark; the denominator of MASE |
| Moving average (28 days) | |
| Simple exponential smoothing | α ∈ {0.05, 0.1, 0.2, 0.3, 0.5}, selected by in-sample SSE, vectorised |
| Holt-Winters ETS | Damped additive trend, additive weekly seasonality (statsmodels) |
| Croston-SBA | For intermittent demand; initialised with mean size and interval |
| LightGBM (global) | One model across all SKUs on mean-scaled demand. Lags 1/7/14/28, rolling means, non-zero ratio, calendar features; Tweedie loss; recursive multi-step |

**Backtesting:** expanding-window rolling origin with *k* = 3 folds and *h* = 28 days. A unit test spies on every model fit and asserts it never sees data at or after its fold's origin.

**Metrics:** MAE, RMSE, WAPE (volume-weighted when aggregated), bias, and MASE scaled by the in-sample seasonal-naive MAE.

**Selection:** the model with the lowest MASE is chosen per SKU and refitted on all history for the final forecast. Its backtest RMSE becomes the demand uncertainty σ used for safety stock, which is better than raw demand variance because it measures the error of the plan actually used. The 80% prediction interval is ŷ ± 1.2816·RMSE.

## 4. Replenishment policy

Continuous review (s, Q):

* σ_LT = √(L·σ_d² + d²·σ_L²)
* SS = z(CSL)·σ_LT
* s = d·L + SS
* Q = max(⌈√(2DS/H)⌉, MOQ), with H = unit cost × annual holding rate

**Status:**
* *stock-out risk* if on-hand stock is 0, or the projected stock-out comes within one lead time (an order placed today would arrive too late).
* *reorder* if inventory position ≤ s.
* *healthy* otherwise.

The suggested order is the smallest multiple of Q that lifts the inventory position above s.

## 5. Simulation experiment

Implemented in [api/app/services/simulation.py](../api/app/services/simulation.py).

**Split.** The final `holdout_days` (default 120) form the evaluation period. Classification and initial parameters use only earlier data.

**Dynamics** (daily, per SKU, vectorised over policies × SKUs):
1. Receive arrivals.
2. Serve demand from on-hand stock; unmet demand is lost.
3. Every 7 days, re-estimate d and σ_d on a trailing 56-day window. This is what a planner would do, and it creates no look-ahead.
4. If the inventory position ≤ s, order n·Q, with lead time L + σ_L·ε rounded and ≥ 1.
5. Accrue holding cost on end-of-day on-hand stock.

Each policy starts at its own steady state, s + Q/2, and the first 14 days are excluded as warm-up.

**Costs:** holding (c·h/365 per unit per day), ordering (S per order), and lost sales (unit margin × multiplier, default 1.0). Total = holding + ordering + shortage.

**Replications.** Replication 0 replays the actual holdout trace. Replications 1…R−1 are moving-block bootstraps (7-day blocks, shared across SKUs) of the holdout, which preserves weekly seasonality and cross-SKU correlation.

**Common random numbers.** In each replication, every policy sees identical demand and lead-time noise. Differences are therefore due to the policy alone, variance is greatly reduced, and a **paired** t-test on per-replication total cost is valid. A unit test confirms that two identical policies produce a difference of exactly zero.

**Policies compared.**
* Uniform 95% (baseline).
* ABC 98 / 95 / 90.
* ABC-XYZ matrix (AX 99% … CZ 85%).
* Any custom set, through the API or UI.

**The fairness problem, and the frontier.** "ABC 98/95/90 beats Uniform 95%" can simply mean that 95% was a bad uniform choice. So the uniform policy is also run at ten service levels (75%–99.5%) to trace a cost-vs-fill-rate frontier. A differentiated policy's *saving at equal service* is the uniform frontier's cost, interpolated at the candidate's fill rate, minus the candidate's cost.

**Verdict rule.**
* *dominates*: below the frontier **and** significantly cheaper than the baseline (p < 0.05).
* *better*: cheaper with fewer stock-outs.
* *worse*: more expensive with more stock-outs.
* *trade-off*: anything else.

## 6. Results (bundled dataset)

See [experiment-results.md](experiment-results.md); regenerate it with:

```bash
cd api && python -m app.cli experiment --replications 30 --out ../docs/experiment-results.md
```

**Findings:**
1. Both ABC policies are significantly cheaper than Uniform 95% (−2.3% and −2.9%, p < 10⁻⁴). They also have 14–26% fewer stock-out SKU-days, so cost and service improve together.
2. Most of that gain is available to a *better-tuned uniform policy*. At equal fill rate the saving is only 0.3–0.7%. Differentiation helps, but **choosing the right service level matters more than differentiating it**. This is consistent with Teunter, Babai & Syntetos (2010), who show that the cost-optimal ranking criterion is not revenue (classic ABC) but a ratio of shortage cost to holding cost and demand.
3. The ABC-XYZ matrix reduces stock-outs most, because it puts safety stock where variability, not only value, is highest.

**Threats to validity:** synthetic data; lost sales assumed to be observable (no demand censoring); deterministic shortage cost; no capacity, budget or joint-replenishment constraints; single echelon.

**Suggested extensions:**
* Run on M5 data.
* Add a cost-optimal criterion (Teunter et al., 2010) as a fourth policy.
* Use periodic review (R, S).
* Use a budget-constrained service allocation.

## References

* Silver, E. A., Pyke, D. F., & Thomas, D. J. (2017). *Inventory and Production Management in Supply Chains* (4th ed.). CRC Press.
* Teunter, R. H., Babai, M. Z., & Syntetos, A. A. (2010). ABC classification: service levels and inventory costs. *Production and Operations Management*, 19(3), 343–352.
* Syntetos, A. A., & Boylan, J. E. (2005). The accuracy of intermittent demand estimates. *International Journal of Forecasting*, 21(2), 303–314.
* Hyndman, R. J., & Koehler, A. B. (2006). Another look at measures of forecast accuracy. *International Journal of Forecasting*, 22(4), 679–688.
* Law, A. M. (2015). *Simulation Modeling and Analysis* (5th ed.), chapter on variance reduction (common random numbers).
