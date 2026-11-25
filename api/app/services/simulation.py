"""Inventory simulation engine: does an ABC-differentiated policy beat a uniform one?

Experimental design (see docs/METHODOLOGY.md):

* **No look-ahead.** History is split at a cutoff. Classification and initial parameters use data
  before the cutoff only; the last `holdout_days` are the evaluation period.
* **Trace + bootstrap.** Replication 0 replays the real holdout demand. Further replications use a
  moving-block bootstrap of the holdout (blocks shared across SKUs to keep cross-correlation and
  weekly patterns).
* **Common random numbers.** Every policy sees the identical demand and lead-time draws in each
  replication, so differences are due to the policy alone and a paired t-test is valid.
* **Policy.** Continuous review (s, Q), lost sales, s = d*L + z*sigma_LT, Q = EOQ. d and sigma are
  re-estimated every `reestimate_every` days on a trailing window, as a planner would.
* **Fair comparison.** A uniform policy is also run at a grid of service levels to trace the
  cost-vs-fill-rate frontier. A differentiated policy only "wins" if it sits *below* that frontier,
  i.e. it is cheaper than a uniform policy that delivers the same fill rate.

The engine is vectorised over (policies x SKUs), so 20 replications x 120 days x 12 policies x
hundreds of SKUs run in about a second.
"""

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy.orm import Session

from app.models import SimulationRun
from app.services.classification import classify
from app.services.data import load_products, load_sales_matrix
from app.services.inventory import z_value

CLASSES = ("A", "B", "C")


@dataclass
class PolicySpec:
    name: str
    # Keys: "*" (all), "A"/"B"/"C", or ABC-XYZ cells like "AX". Most specific key wins.
    service_levels: dict[str, float]


@dataclass
class SimParams:
    holdout_days: int = 120
    warmup_days: int = 14
    estimation_window: int = 56
    reestimate_every: int = 7
    replications: int = 20
    block_size: int = 7
    seed: int = 42
    stockout_cost_multiplier: float = 1.0  # x unit margin per unit of lost sales
    lead_time_variability: bool = True
    policies: list[PolicySpec] = field(
        default_factory=lambda: [
            PolicySpec("Uniform 95%", {"*": 0.95}),
            PolicySpec("ABC 98/95/90", {"A": 0.98, "B": 0.95, "C": 0.90}),
            PolicySpec(
                "ABC-XYZ matrix",
                {
                    "AX": 0.99,
                    "AY": 0.98,
                    "AZ": 0.95,
                    "BX": 0.97,
                    "BY": 0.95,
                    "BZ": 0.92,
                    "CX": 0.93,
                    "CY": 0.90,
                    "CZ": 0.85,
                },
            ),
        ]
    )
    frontier_levels: list[float] = field(
        default_factory=lambda: [0.75, 0.80, 0.85, 0.90, 0.93, 0.95, 0.97, 0.98, 0.99, 0.995]
    )


def _level_for(spec: PolicySpec, abc: str, xyz: str) -> float:
    for key in (f"{abc}{xyz}", abc, "*"):
        if key in spec.service_levels:
            return float(spec.service_levels[key])
    return 0.95


def _bootstrap_index(n_days: int, block: int, rng: np.random.Generator) -> np.ndarray:
    starts = rng.integers(0, max(1, n_days - block + 1), size=int(np.ceil(n_days / block)))
    return np.concatenate([np.arange(s, s + block) for s in starts])[:n_days]


def simulate(sales: pd.DataFrame, products: pd.DataFrame, params: SimParams) -> dict:
    """Pure function: demand matrix + product master data -> experiment results."""
    H = params.holdout_days
    if len(sales) < H + params.estimation_window + 28:
        raise ValueError(f"Need at least {H + params.estimation_window + 28} days of history for a {H}-day holdout.")

    ids = [c for c in sales.columns if c in products.index]
    train = sales.iloc[:-H][ids]
    holdout = sales.iloc[-H:][ids].to_numpy(dtype=float)
    p = products.loc[ids]
    n = len(ids)

    # Classification on pre-cutoff data only.
    cls = classify(train, p["unit_price"]).reindex(ids)
    abc = cls["abc"].fillna("C").to_numpy()
    xyz = cls["xyz"].fillna("Z").to_numpy()

    # Policy matrix: main policies first, then the uniform frontier grid.
    specs = list(params.policies) + [PolicySpec(f"Uniform {lv:.1%}", {"*": lv}) for lv in params.frontier_levels]
    n_main = len(params.policies)
    P = len(specs)
    z = np.array([[z_value(_level_for(s, abc[j], xyz[j])) for j in range(n)] for s in specs])  # (P, n)

    unit_cost = p["unit_cost"].to_numpy(float)
    margin = np.maximum(p["unit_price"].to_numpy(float) - unit_cost, 0.0)
    shortage_unit = params.stockout_cost_multiplier * margin
    hold_unit_day = unit_cost * p["holding_rate"].to_numpy(float) / 365.0
    order_cost = p["order_cost"].to_numpy(float)
    L = np.maximum(p["lead_time_days"].to_numpy(int), 1)
    sigma_L = p["lead_time_std_days"].to_numpy(float) if params.lead_time_variability else np.zeros(n)
    moq = p["moq"].to_numpy(float)
    holding_year = unit_cost * p["holding_rate"].to_numpy(float)

    W = params.estimation_window
    tail = train.to_numpy(dtype=float)[-W:]
    max_arrival = H + int(L.max() + 4 * sigma_L.max()) + 2

    metric_names = (
        "holding",
        "ordering",
        "shortage",
        "demand",
        "served",
        "lost",
        "stockout_days",
        "orders",
        "inv_value",
    )
    reps = max(1, params.replications)
    per_rep = {m: np.zeros((reps, P, n)) for m in metric_names}
    trajectory = np.zeros((n_main, H))  # inventory value per day, replication 0

    for r in range(reps):
        rng = np.random.default_rng(params.seed + r)
        demand = holdout if r == 0 else holdout[_bootstrap_index(H, params.block_size, rng)]
        lt_noise = rng.standard_normal((H, n))  # common random numbers across policies

        history = np.vstack([tail, demand])  # estimation reads only days < t
        on_hand = np.zeros((P, n))
        pipeline = np.zeros((P, n))
        arrivals = np.zeros((max_arrival, P, n))
        rop = np.zeros((P, n))
        q = np.ones((P, n))

        for t in range(H):
            if t % params.reestimate_every == 0:
                window = history[t : t + W]
                mu = window.mean(axis=0)
                sd = window.std(axis=0, ddof=1)
                sigma_lt = np.sqrt(L * sd**2 + mu**2 * sigma_L**2)
                rop = mu * L + z * sigma_lt
                eoq = np.sqrt(
                    np.divide(2 * mu * 365 * order_cost, holding_year, out=np.zeros(n), where=holding_year > 0)
                )
                q = np.broadcast_to(np.maximum(np.ceil(np.maximum(eoq, 1.0)), moq), (P, n)).copy()
                if t == 0:  # start every policy at its own steady state: s + Q/2
                    on_hand = rop + q / 2.0

            on_hand += arrivals[t]
            pipeline -= arrivals[t]

            d = demand[t]
            served = np.minimum(on_hand, d)
            lost = d - served
            on_hand -= served

            position = on_hand + pipeline
            trigger = position <= rop
            n_lots = np.where(trigger, np.ceil(np.maximum(rop - position, 0) / q + 1e-9).clip(min=1), 0)
            qty = n_lots * q
            lead = np.maximum(1, np.rint(L + sigma_L * lt_noise[t]).astype(int))
            arrive = np.minimum(t + lead, max_arrival - 1)
            np.add.at(arrivals, (np.broadcast_to(arrive, (P, n)), np.arange(P)[:, None], np.arange(n)[None, :]), qty)
            pipeline += qty

            if t >= params.warmup_days:
                per_rep["holding"][r] += on_hand * hold_unit_day
                per_rep["ordering"][r] += trigger * order_cost
                per_rep["shortage"][r] += lost * shortage_unit
                per_rep["demand"][r] += d
                per_rep["served"][r] += served
                per_rep["lost"][r] += lost
                per_rep["stockout_days"][r] += lost > 1e-9
                per_rep["orders"][r] += trigger
                per_rep["inv_value"][r] += on_hand * unit_cost
            if r == 0:
                trajectory[:, t] = (on_hand[:n_main] * unit_cost).sum(axis=1)

    days_measured = H - params.warmup_days
    per_rep["inv_value"] /= max(days_measured, 1)
    per_rep["total"] = per_rep["holding"] + per_rep["ordering"] + per_rep["shortage"]

    def summarise(mask: np.ndarray) -> list[dict]:
        out = []
        for i in range(P):
            agg = {m: per_rep[m][:, i, mask].sum(axis=1) for m in per_rep}  # (reps,)
            fill = agg["served"] / np.maximum(agg["demand"], 1e-9)
            out.append(
                {
                    "total_cost": float(agg["total"].mean()),
                    "holding_cost": float(agg["holding"].mean()),
                    "ordering_cost": float(agg["ordering"].mean()),
                    "shortage_cost": float(agg["shortage"].mean()),
                    "fill_rate": float(fill.mean()),
                    "stockout_days": float(agg["stockout_days"].mean()),
                    "units_lost": float(agg["lost"].mean()),
                    "orders": float(agg["orders"].mean()),
                    "avg_inventory_value": float(agg["inv_value"].mean()),
                    "_total_reps": agg["total"],
                    "_fill_reps": fill,
                    "_stockout_reps": agg["stockout_days"],
                }
            )
        return out

    all_mask = np.ones(n, dtype=bool)
    overall = summarise(all_mask)
    by_class = {c: summarise(abc == c) for c in CLASSES if (abc == c).any()}

    def strip(d: dict) -> dict:
        return {k: v for k, v in d.items() if not k.startswith("_")}

    policies_out = []
    for i in range(n_main):
        policies_out.append(
            {
                "name": specs[i].name,
                "service_levels": specs[i].service_levels,
                "overall": strip(overall[i]),
                "by_class": {c: strip(v[i]) for c, v in by_class.items()},
                "trajectory": [round(float(x), 2) for x in trajectory[i]],
            }
        )

    frontier = [{"service_level": lv, **strip(overall[n_main + k])} for k, lv in enumerate(params.frontier_levels)]

    comparisons = [
        _compare(overall[0], overall[i], specs[0].name, specs[i].name, frontier, reps) for i in range(1, n_main)
    ]

    per_sku = []
    for j, pid in enumerate(ids):
        row = {"product_id": int(pid), "sku": p.at[pid, "sku"], "abc": abc[j], "xyz": xyz[j]}
        for i in range(n_main):
            dem = per_rep["demand"][:, i, j].mean()
            row[specs[i].name] = {
                "total_cost": round(float(per_rep["total"][:, i, j].mean()), 2),
                "fill_rate": round(float(per_rep["served"][:, i, j].mean() / dem), 4) if dem > 0 else 1.0,
                "stockout_days": round(float(per_rep["stockout_days"][:, i, j].mean()), 2),
            }
        per_sku.append(row)

    return {
        "skus": n,
        "class_counts": {c: int((abc == c).sum()) for c in CLASSES},
        "holdout_start": str(sales.index[-H].date()),
        "holdout_end": str(sales.index[-1].date()),
        "days_measured": days_measured,
        "replications": reps,
        "policies": policies_out,
        "frontier": frontier,
        "comparisons": comparisons,
        "per_sku": per_sku,
    }


def _paired(a: np.ndarray, b: np.ndarray) -> dict:
    diff = b - a
    mean = float(diff.mean())
    if len(diff) < 2 or np.allclose(diff, diff[0]):
        return {"mean_diff": mean, "ci_low": mean, "ci_high": mean, "p_value": None}
    se = diff.std(ddof=1) / np.sqrt(len(diff))
    t_crit = stats.t.ppf(0.975, len(diff) - 1)
    p_value = float(stats.ttest_rel(b, a).pvalue)
    return {"mean_diff": mean, "ci_low": mean - t_crit * se, "ci_high": mean + t_crit * se, "p_value": p_value}


def _compare(base: dict, cand: dict, base_name: str, cand_name: str, frontier: list[dict], reps: int) -> dict:
    cost = _paired(base["_total_reps"], cand["_total_reps"])
    fill = _paired(base["_fill_reps"], cand["_fill_reps"])
    stockouts = _paired(base["_stockout_reps"], cand["_stockout_reps"])

    # Frontier test: what would a uniform policy cost at the candidate's fill rate?
    pts = sorted(frontier, key=lambda f: f["fill_rate"])
    fr = np.array([f["fill_rate"] for f in pts])
    cs = np.array([f["total_cost"] for f in pts])
    target = cand["fill_rate"]
    within = fr.min() <= target <= fr.max()
    uniform_cost_at_same_fill = float(np.interp(target, fr, cs)) if within else None
    saving = (uniform_cost_at_same_fill - cand["total_cost"]) if uniform_cost_at_same_fill else None

    significant = cost["p_value"] is not None and cost["p_value"] < 0.05
    cheaper = cost["mean_diff"] < 0
    fewer_stockouts = stockouts["mean_diff"] < 0
    if saving is not None and saving > 0 and significant:
        verdict = "dominates"  # below the uniform frontier: cheaper at equal service
    elif cheaper and fewer_stockouts:
        verdict = "better"
    elif not cheaper and not fewer_stockouts:
        verdict = "worse"
    else:
        verdict = "trade-off"

    return {
        "baseline": base_name,
        "candidate": cand_name,
        "total_cost": cost,
        "total_cost_pct": cost["mean_diff"] / base["total_cost"] if base["total_cost"] else 0.0,
        "fill_rate": fill,
        "stockout_days": stockouts,
        "stockout_days_pct": stockouts["mean_diff"] / base["stockout_days"] if base["stockout_days"] else 0.0,
        "uniform_cost_at_same_fill": uniform_cost_at_same_fill,
        "saving_vs_frontier": saving,
        "saving_vs_frontier_pct": (saving / uniform_cost_at_same_fill)
        if saving and uniform_cost_at_same_fill
        else None,
        "significant": significant,
        "verdict": verdict,
        "replications": reps,
    }


def run_simulation(db: Session, params: SimParams | None = None) -> SimulationRun:
    params = params or SimParams()
    sales = load_sales_matrix(db)
    products = load_products(db)
    if sales.empty or products.empty:
        raise ValueError("No data. Import products and sales first.")
    results = simulate(sales, products, params)
    run = SimulationRun(params=asdict(params), results=results)
    db.add(run)
    db.flush()
    return run
