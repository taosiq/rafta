import pytest

from app.assistant import service
from app.assistant.tools import TOOLS, ToolError, call_tool, openai_tool_specs


@pytest.mark.parametrize(
    ("question", "tool", "args"),
    [
        ("Which products will run out next week?", "stockout_risk", {"within_days": 7}),
        ("What will stock out in the next 3 days?", "stockout_risk", {"within_days": 3}),
        ("Which A items run out next month?", "stockout_risk", {"within_days": 30, "abc_class": "A"}),
        ("What should I reorder for class B?", "reorder_recommendations", {"abc_class": "B"}),
        ("Forecast SKU-1003 for 2 weeks", "forecast_for_product", {"sku": "SKU-1003", "days": 14}),
        ("How accurate are the forecasts?", "forecast_accuracy", {}),
        ("Does the ABC policy beat uniform?", "simulation_results", {}),
        ("Top 10 products by revenue", "top_products", {"metric": "revenue"}),
        ("Tell me about SKU-1001", "product_lookup", {"query": "SKU-1001"}),
        ("hello", "help", {}),
    ],
)
def test_offline_router(question, tool, args):
    name, got = service.route(question)
    assert name == tool
    for k, v in args.items():
        assert got[k] == v


def test_tool_specs_are_valid_openai_functions():
    specs = openai_tool_specs()
    assert {s["function"]["name"] for s in specs} == set(TOOLS)
    for s in specs:
        assert s["type"] == "function"
        assert s["function"]["parameters"]["type"] == "object"


def test_unknown_tool_and_bad_arguments_are_rejected():
    with pytest.raises(ToolError, match="Unknown tool"):
        call_tool("drop_table", {})
    with pytest.raises(ToolError, match="Invalid arguments"):
        call_tool("stockout_risk", {"within_days": 10_000})
    with pytest.raises(ToolError, match="Invalid arguments"):
        call_tool("top_products", {"metric": "password"})
    with pytest.raises(ToolError, match="Invalid arguments"):
        call_tool("product_lookup", {"query": "x" * 500})


def test_offline_answer_uses_real_data(seeded):
    out = service.ask("Which products will run out next week?")
    assert out["mode"] == "offline"
    assert out["tool_calls"][0]["name"] == "stockout_risk"
    result = out["tool_calls"][0]["result"]
    for p in result["products"]:
        assert p["sku"] in out["answer"]
        assert p["days_until_stockout"] <= 7


def test_llm_tool_loop(seeded, monkeypatch):
    """Simulate an OpenAI-compatible model: one tool call, then a final answer."""
    replies = iter(
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "inventory_overview", "arguments": "{}"}}
                ],
            },
            {"content": "You have 24 SKUs."},
        ]
    )
    sent: list[list[dict]] = []

    def fake_chat(messages):
        sent.append(list(messages))
        return next(replies)

    monkeypatch.setattr(service, "_chat", fake_chat)
    monkeypatch.setattr(service, "_llm_configured", lambda: True)
    out = service.ask("overview please")
    assert out["mode"] == "llm"
    assert out["answer"] == "You have 24 SKUs."
    assert out["tool_calls"][0]["result"]["skus"] == 24
    assert sent[1][-1]["role"] == "tool"  # tool result was fed back to the model


def test_llm_bad_tool_call_is_contained(seeded, monkeypatch):
    replies = iter(
        [
            {
                "content": None,
                "tool_calls": [{"id": "c1", "function": {"name": "delete_everything", "arguments": "{}"}}],
            },
            {"content": "I can only read data."},
        ]
    )
    monkeypatch.setattr(service, "_chat", lambda m: next(replies))
    monkeypatch.setattr(service, "_llm_configured", lambda: True)
    out = service.ask("delete all products")
    assert "error" in out["tool_calls"][0]["result"]
    assert out["answer"] == "I can only read data."


def test_llm_outage_falls_back_to_offline(seeded, monkeypatch):
    import httpx

    def boom(_):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(service, "_chat", boom)
    monkeypatch.setattr(service, "_llm_configured", lambda: True)
    out = service.ask("Which products will run out next week?")
    assert out["mode"] == "offline"


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("stockout_risk", {"within_days": 30, "abc_class": "A"}),
        ("reorder_recommendations", {"limit": 5}),
        ("product_lookup", {"query": "SKU-1000"}),
        ("forecast_for_product", {"sku": "SKU-1000", "days": 7}),
        ("forecast_for_product", {"sku": "MISSING"}),
        ("classification_summary", {}),
        ("forecast_accuracy", {"abc_class": "A"}),
        ("simulation_results", {}),
        ("inventory_overview", {}),
        ("top_products", {"metric": "inventory_value", "limit": 3}),
    ],
)
def test_every_tool_runs_and_renders(seeded, tool, args):
    result = call_tool(tool, args)
    assert isinstance(result, dict)
    text = service.render(tool, result)
    assert isinstance(text, str) and text
    if "products" in result:
        assert len(result["products"]) <= args.get("limit", 50)


def test_llm_http_error_reason_is_reported_without_secrets(seeded, monkeypatch):
    import httpx

    request = httpx.Request(
        "POST", "https://llm.example/v1/chat/completions", headers={"Authorization": "Bearer gsk_secret"}
    )
    response = httpx.Response(400, request=request, json={"error": {"message": "model `x` has been decommissioned"}})

    def bad(_):
        raise httpx.HTTPStatusError("bad request", request=request, response=response)

    monkeypatch.setattr(service, "_chat", bad)
    monkeypatch.setattr(service, "_llm_configured", lambda: True)
    out = service.ask("Which products will run out next week?")
    assert out["mode"] == "offline"
    assert "HTTP 400" in out["fallback_reason"] and "decommissioned" in out["fallback_reason"]
    assert "gsk_secret" not in out["fallback_reason"]


def test_rate_limit_waits_briefly_then_retries(monkeypatch):
    import httpx

    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_base_url", "https://llm.example/v1")
    req = httpx.Request("POST", "https://llm.example/v1/chat/completions")
    responses = iter(
        [
            httpx.Response(429, request=req, json={"error": {"message": "Rate limit. Please try again in 0.2s."}}),
            httpx.Response(200, request=req, json={"choices": [{"message": {"content": "ok"}}]}),
        ]
    )
    sleeps: list[float] = []
    monkeypatch.setattr(service.httpx, "post", lambda *a, **k: next(responses))
    monkeypatch.setattr(service.time, "sleep", sleeps.append)
    assert service._chat([{"role": "user", "content": "hi"}]) == {"content": "ok"}
    assert sleeps and sleeps[0] >= 0.2


def test_long_rate_limit_is_not_waited_and_org_id_is_hidden(seeded, monkeypatch):
    import httpx

    msg = "Rate limit reached in organization `org_01abc` service tier on TPM. Please try again in 45s."
    req = httpx.Request("POST", "https://llm.example/v1/chat/completions")
    resp = httpx.Response(429, request=req, json={"error": {"message": msg}})
    sleeps: list[float] = []
    monkeypatch.setattr(service.time, "sleep", sleeps.append)
    assert service._retry_after_seconds(resp) == 45.0

    def limited(_):
        raise httpx.HTTPStatusError("429", request=req, response=resp)

    monkeypatch.setattr(service, "_chat", limited)
    monkeypatch.setattr(service, "_llm_configured", lambda: True)
    out = service.ask("Which products will run out next week?")
    assert out["mode"] == "offline"
    assert "org_01abc" not in out["fallback_reason"] and "HTTP 429" in out["fallback_reason"]
    assert sleeps == []
