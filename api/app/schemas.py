"""Request schemas (validated input). Responses are documented in OpenAPI via examples."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PolicyIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    service_levels: dict[str, float]

    @field_validator("service_levels")
    @classmethod
    def _check(cls, v: dict[str, float]) -> dict[str, float]:
        allowed = {"*", "A", "B", "C"} | {f"{a}{x}" for a in "ABC" for x in "XYZ"}
        bad = set(v) - allowed
        if bad:
            raise ValueError(f"invalid keys {sorted(bad)}; use '*', A/B/C or AX..CZ")
        if not v:
            raise ValueError("at least one service level is required")
        for key, level in v.items():
            if not 0.5 <= level <= 0.999:
                raise ValueError(f"service level for {key} must be between 0.5 and 0.999")
        return v


class SimulationIn(BaseModel):
    holdout_days: int = Field(120, ge=28, le=365)
    warmup_days: int = Field(14, ge=0, le=60)
    estimation_window: int = Field(56, ge=14, le=365)
    reestimate_every: int = Field(7, ge=1, le=60)
    replications: int = Field(20, ge=1, le=200)
    block_size: int = Field(7, ge=1, le=28)
    seed: int = Field(42, ge=0)
    stockout_cost_multiplier: float = Field(1.0, ge=0, le=20)
    lead_time_variability: bool = True
    policies: list[PolicyIn] | None = Field(None, min_length=2, max_length=6)


class JobIn(BaseModel):
    job_type: Literal["classify", "forecast", "policy", "simulate", "pipeline", "refresh"]


class AskIn(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)


class SeedIn(BaseModel):
    skus: int = Field(150, ge=10, le=1000)
    days: int = Field(730, ge=240, le=1460)
    seed: int = 7
