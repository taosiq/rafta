import os
import tempfile
from pathlib import Path

# Configure the app *before* it is imported: isolated SQLite file, no scheduler, no LLM.
_TMP = Path(tempfile.mkdtemp(prefix="rafta-test-"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{(_TMP / 'test.db').as_posix()}")
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["SEED_ON_STARTUP"] = "false"
os.environ.pop("LLM_BASE_URL", None)

import pytest  # noqa: E402

from app import models  # noqa: E402,F401
from app.db import Base, engine, session_scope  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def schema():
    if engine.dialect.name == "sqlite":
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(scope="session")
def seeded(schema):
    """A small but complete dataset with every pipeline step run once."""
    from app.services.classification import run_classification
    from app.services.demo import load_demo
    from app.services.forecasting import run_forecasts
    from app.services.inventory import run_policies
    from app.services.simulation import SimParams, run_simulation

    with session_scope() as db:
        load_demo(db, skus=24, days=420, seed=3)
    with session_scope() as db:
        run_classification(db)
    with session_scope() as db:
        run_forecasts(db, horizon=14, folds=2)
    with session_scope() as db:
        run_policies(db)
    with session_scope() as db:
        run_simulation(db, SimParams(replications=5, holdout_days=90))
    return True
