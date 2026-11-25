"""Command-line entry points.

python -m app.cli seed [--if-empty] [--skus 150] [--days 730]
python -m app.cli pipeline
python -m app.cli experiment [--replications 30] [--holdout 120] [--out results.md]
python -m app.cli export-sample ../data/sample
"""

import argparse
import json
import sys
from pathlib import Path

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.db import Base, engine, session_scope


def _ensure_schema() -> None:
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)


def cmd_seed(args) -> None:
    from app.services.demo import is_empty, load_demo

    with session_scope() as db:
        if args.if_empty and not is_empty(db):
            print("database already has data; skipping seed")
            return
        print(json.dumps(load_demo(db, skus=args.skus, days=args.days, seed=args.seed)))
    if not args.no_pipeline:
        cmd_pipeline(args)


def cmd_pipeline(_args) -> None:
    from app.jobs import STEPS

    for step in ("classify", "forecast", "policy", "simulate"):
        with session_scope() as db:
            print(f"[{step}] {STEPS[step](db, {})}")


def cmd_experiment(args) -> None:
    """Run the thesis experiment and print a Markdown results table."""
    from app.services.simulation import SimParams, run_simulation

    params = SimParams(
        replications=args.replications,
        holdout_days=args.holdout,
        stockout_cost_multiplier=args.stockout_multiplier,
        seed=args.seed,
    )
    with session_scope() as db:
        run = run_simulation(db, params)
    r = run.results
    lines = [
        f"# Rafta policy experiment (simulation #{run.id})",
        "",
        f"Holdout {r['holdout_start']} to {r['holdout_end']}, {r['skus']} SKUs "
        f"({r['class_counts']}), {r['replications']} replications, common random numbers.",
        "",
        "| Policy | Total cost | Holding | Ordering | Shortage | Fill rate | Stock-out SKU-days |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for p in r["policies"]:
        o = p["overall"]
        lines.append(
            f"| {p['name']} | {o['total_cost']:,.0f} | {o['holding_cost']:,.0f} | "
            f"{o['ordering_cost']:,.0f} | {o['shortage_cost']:,.0f} | {o['fill_rate']:.2%} | "
            f"{o['stockout_days']:,.1f} |"
        )
    lines += [
        "",
        "| Candidate vs baseline | Cost diff (95% CI) | p | Stock-out days | Saving vs uniform frontier | Verdict |",
        "|---|---|---:|---:|---:|---|",
    ]
    for c in r["comparisons"]:
        tc = c["total_cost"]
        p = "n/a" if tc["p_value"] is None else f"{tc['p_value']:.3g}"
        sav = "n/a" if c["saving_vs_frontier_pct"] is None else f"{c['saving_vs_frontier_pct']:.1%}"
        lines.append(
            f"| {c['candidate']} vs {c['baseline']} | {tc['mean_diff']:+,.0f} "
            f"[{tc['ci_low']:+,.0f}, {tc['ci_high']:+,.0f}] | {p} | {c['stockout_days_pct']:+.1%} | "
            f"{sav} | **{c['verdict']}** |"
        )
    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")


def cmd_export(args) -> None:
    from app.services.demo import export_sample

    for path in export_sample(Path(args.directory), skus=args.skus, days=args.days):
        print(f"wrote {path}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="rafta")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("seed", help="load the synthetic demo dataset and run the pipeline")
    s.add_argument("--if-empty", action="store_true")
    s.add_argument("--no-pipeline", action="store_true")
    s.add_argument("--skus", type=int, default=150)
    s.add_argument("--days", type=int, default=730)
    s.add_argument("--seed", type=int, default=7)
    s.set_defaults(func=cmd_seed)

    sub.add_parser("pipeline", help="classify, forecast, compute policies, simulate").set_defaults(func=cmd_pipeline)

    e = sub.add_parser("experiment", help="run the ABC vs uniform experiment")
    e.add_argument("--replications", type=int, default=30)
    e.add_argument("--holdout", type=int, default=120)
    e.add_argument("--stockout-multiplier", type=float, default=1.0)
    e.add_argument("--seed", type=int, default=42)
    e.add_argument("--out")
    e.set_defaults(func=cmd_experiment)

    x = sub.add_parser("export-sample", help="write sample CSVs")
    x.add_argument("directory")
    x.add_argument("--skus", type=int, default=150)
    x.add_argument("--days", type=int, default=730)
    x.set_defaults(func=cmd_export)

    args = parser.parse_args(argv)
    _ensure_schema()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
