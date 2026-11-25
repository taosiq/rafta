from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import jobs
from app.config import get_settings
from app.db import get_db
from app.models import JobRun
from app.schemas import JobIn

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _out(j: JobRun) -> dict:
    duration = (j.finished_at - j.started_at).total_seconds() if j.finished_at and j.started_at else None
    return {
        "id": j.id,
        "job_type": j.job_type,
        "trigger": j.trigger,
        "status": j.status,
        "created_at": j.created_at,
        "started_at": j.started_at,
        "finished_at": j.finished_at,
        "duration_s": duration,
        "message": j.message,
    }


@router.get("")
def list_jobs(limit: int = 20, db: Session = Depends(get_db)):
    rows = db.execute(select(JobRun).order_by(JobRun.id.desc()).limit(min(limit, 100))).scalars().all()
    return {
        "jobs": [_out(j) for j in rows],
        "schedule": get_settings().forecast_cron,
        "next_run": jobs.next_scheduled_run(),
    }


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(JobRun, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return _out(job)


@router.post("", status_code=202)
def create_job(body: JobIn):
    return {"job_id": jobs.submit(body.job_type, trigger="manual")}
