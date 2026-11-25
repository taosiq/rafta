"""Background jobs and the nightly scheduler.

Jobs run on a single-worker thread pool, so they execute one at a time inside a process, and
take a PostgreSQL advisory lock, so two API replicas never run the same pipeline concurrently.
Every run is recorded in `job_runs` with its status, duration and message for the dashboard.

Free and dependency-light on purpose: APScheduler in-process instead of Celery + Redis. The job
functions are plain callables, so moving to a dedicated worker later is a small change.
"""

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_scope
from app.models import JobRun, utcnow
from app.services.classification import run_classification
from app.services.forecasting import run_forecasts
from app.services.inventory import run_policies
from app.services.simulation import SimParams, run_simulation

log = logging.getLogger(__name__)
ADVISORY_LOCK_KEY = 72_616_674  # arbitrary constant: "rafta"

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rafta-job")
_scheduler: BackgroundScheduler | None = None


def _classify(db: Session, params: dict) -> str:
    out = run_classification(db)
    return f"Classified {out['products']} products"


def _forecast(db: Session, params: dict) -> str:
    s = get_settings()
    run = run_forecasts(
        db,
        horizon=params.get("horizon", s.forecast_horizon_days),
        folds=params.get("folds", s.backtest_folds),
        enable_lightgbm=s.enable_lightgbm,
    )
    sel = run.summary["selected"]
    return f"Forecast run #{run.id}: median MASE {sel['median_mase']:.3f}, weighted WAPE {sel['weighted_wape']:.1%}"


def _policy(db: Session, params: dict) -> str:
    out = run_policies(db)
    return "Policies: " + ", ".join(f"{k} {v}" for k, v in sorted(out["status_counts"].items()))


def _simulate(db: Session, params: dict) -> str:
    run = run_simulation(db, params.get("sim") or SimParams())
    cmp = run.results["comparisons"][0] if run.results["comparisons"] else None
    if cmp is None:
        return f"Simulation #{run.id} complete"
    return f"Simulation #{run.id}: {cmp['candidate']} vs {cmp['baseline']} -> {cmp['verdict']}"


STEPS: dict[str, Callable[[Session, dict], str]] = {
    "classify": _classify,
    "forecast": _forecast,
    "policy": _policy,
    "simulate": _simulate,
}
PIPELINES: dict[str, list[str]] = {
    **{k: [k] for k in STEPS},
    "pipeline": ["classify", "forecast", "policy", "simulate"],
    "refresh": ["classify", "forecast", "policy"],  # what the nightly schedule runs
}


@contextmanager
def _advisory_lock(db: Session):
    if db.bind is None or db.bind.dialect.name != "postgresql":
        yield True
        return
    got = db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY}).scalar()
    try:
        yield bool(got)
    finally:
        if got:
            db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})


def execute(job_id: int, job_type: str, params: dict | None = None) -> None:
    """Run a job synchronously (the worker thread calls this)."""
    params = params or {}
    with session_scope() as db:
        job = db.get(JobRun, job_id)
        job.status, job.started_at = "running", utcnow()

    messages: list[str] = []
    status = "success"
    started = time.perf_counter()
    try:
        with session_scope() as lock_db, _advisory_lock(lock_db) as acquired:
            if not acquired:
                raise RuntimeError("Another job is running on a different instance")
            for step in PIPELINES[job_type]:
                with session_scope() as db:
                    messages.append(STEPS[step](db, params))
                log.info("job %s step %s done", job_id, step)
    except Exception as exc:
        log.exception("job %s failed", job_id)
        status = "failed"
        messages.append(f"Error: {exc}")

    with session_scope() as db:
        job = db.get(JobRun, job_id)
        job.status, job.finished_at = status, utcnow()
        job.message = " | ".join(messages) + f" ({time.perf_counter() - started:.1f}s)"


def submit(job_type: str, trigger: str = "manual", params: dict | None = None, wait: bool = False) -> int:
    if job_type not in PIPELINES:
        raise ValueError(f"Unknown job type '{job_type}'")
    with session_scope() as db:
        job = JobRun(job_type=job_type, trigger=trigger, status="queued")
        db.add(job)
        db.flush()
        job_id = job.id
    future = _executor.submit(execute, job_id, job_type, params)
    if wait:
        future.result()
    return job_id


def start_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    s = get_settings()
    if not s.scheduler_enabled or _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        submit,
        CronTrigger.from_crontab(s.forecast_cron, timezone="UTC"),
        args=["refresh", "schedule"],
        id="nightly-refresh",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    _scheduler.start()
    log.info("scheduler started: refresh at '%s' UTC", s.forecast_cron)
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def next_scheduled_run() -> str | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job("nightly-refresh")
    return job.next_run_time.isoformat() if job and job.next_run_time else None
