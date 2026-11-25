import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app import (
    __version__,
    jobs,
    models,  # noqa: F401  (registers tables on Base.metadata)
)
from app.config import get_settings
from app.db import Base, engine, session_scope
from app.routers import analytics, assistant, data
from app.routers import jobs as jobs_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("rafta")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if engine.dialect.name == "sqlite":  # Postgres schema is managed by Alembic migrations
        Base.metadata.create_all(engine)
    if settings.seed_on_startup:
        from app.services.demo import is_empty, load_demo

        with session_scope() as db:
            empty = is_empty(db)
            if empty:
                log.info("empty database: loading demo dataset")
                load_demo(db)
        if empty:
            jobs.submit("pipeline", trigger="startup")
    jobs.start_scheduler()
    yield
    jobs.stop_scheduler()


settings = get_settings()
app = FastAPI(
    title="Rafta API",
    version=__version__,
    description="AI inventory optimisation for SMEs: ABC/XYZ classification, backtested forecasting, "
    "(s, Q) policies and ABC-vs-uniform policy simulation.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    response.headers["server-timing"] = f"app;dur={(time.perf_counter() - started) * 1000:.1f}"
    return response


@app.get("/", include_in_schema=False)
def root():
    """The API has no UI of its own; send visitors to the interactive docs."""
    return RedirectResponse("/docs")


@app.get("/health", tags=["meta"])
def health():
    with engine.connect() as conn:
        conn.exec_driver_sql("SELECT 1")
    return {"status": "ok", "version": __version__, "database": engine.dialect.name}


API = "/api/v1"
app.include_router(analytics.router, prefix=API)
app.include_router(data.router, prefix=API)
app.include_router(jobs_router.router, prefix=API)
app.include_router(assistant.router, prefix=API)
