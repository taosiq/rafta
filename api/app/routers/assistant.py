from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from app.assistant.service import ask
from app.assistant.tools import TOOLS
from app.config import get_settings
from app.schemas import AskIn

router = APIRouter(prefix="/assistant", tags=["assistant"])

EXAMPLES = [
    "Which products will run out next week?",
    "What should I reorder for class A?",
    "How accurate are the forecasts?",
    "Does the ABC policy beat the uniform policy?",
    "Show the top 5 products by revenue",
    "Give me an inventory overview",
]


@router.get("/status")
def status():
    s = get_settings()
    return {
        "mode": "llm" if s.llm_base_url else "offline",
        "model": s.llm_model if s.llm_base_url else None,
        "tools": [{"name": t.name, "description": t.description} for t in TOOLS.values()],
        "examples": EXAMPLES,
    }


@router.post("/ask")
async def ask_question(body: AskIn):
    return await run_in_threadpool(ask, body.question)
