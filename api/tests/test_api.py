import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client(seeded):
    with TestClient(app) as c:
        yield c


def test_root_redirects_to_docs(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/docs"


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_overview(client):
    body = client.get("/api/v1/overview").json()
    assert body["skus"] == 24
    assert sum(body["status_counts"].values()) == 24
    assert body["forecast"]["median_mase"] > 0
    assert body["simulation"]["comparisons"]


def test_products_filter_sort_paginate(client):
    r = client.get("/api/v1/products", params={"abc": "A", "sort": "revenue", "order": "desc", "page_size": 5})
    body = r.json()
    assert r.status_code == 200
    assert all(i["abc"] == "A" for i in body["items"])
    revenues = [i["revenue"] for i in body["items"]]
    assert revenues == sorted(revenues, reverse=True)
    assert len(body["items"]) <= 5
    assert client.get("/api/v1/products", params={"abc": "Q"}).status_code == 422


def test_product_detail(client):
    sku = client.get("/api/v1/products", params={"page_size": 1}).json()["items"][0]["sku"]
    body = client.get(f"/api/v1/products/{sku}").json()
    assert body["product"]["sku"] == sku
    assert len(body["forecast"]) == 14
    assert sum(m["selected"] for m in body["backtest"]) == 1
    assert len(body["history"]) == 180
    assert client.get("/api/v1/products/NOPE").status_code == 404


def test_classification_and_forecast_summary(client):
    body = client.get("/api/v1/classification").json()
    assert len(body["items"]) == 24
    assert body["pareto"][-1]["revenue_share"] == pytest.approx(1.0)
    fs = client.get("/api/v1/forecasts/summary").json()
    assert fs["run"]["summary"]["selected"]["weighted_wape"] >= 0


def test_run_custom_simulation(client):
    r = client.post(
        "/api/v1/simulations",
        json={
            "replications": 3,
            "holdout_days": 90,
            "policies": [{"name": "U", "service_levels": {"*": 0.9}}, {"name": "ABC", "service_levels": {"A": 0.99}}],
        },
    )
    assert r.status_code == 201, r.text
    assert [p["name"] for p in r.json()["results"]["policies"]] == ["U", "ABC"]
    assert client.get("/api/v1/simulations/latest").json()["id"] == r.json()["id"]


@pytest.mark.parametrize(
    "bad",
    [
        {"policies": [{"name": "x", "service_levels": {"*": 1.5}}, {"name": "y", "service_levels": {"*": 0.9}}]},
        {"policies": [{"name": "x", "service_levels": {"Q": 0.9}}, {"name": "y", "service_levels": {"*": 0.9}}]},
        {"replications": 0},
    ],
)
def test_simulation_validation(client, bad):
    assert client.post("/api/v1/simulations", json=bad).status_code == 422


def test_import_endpoint_reports_errors(client):
    r = client.post("/api/v1/imports/sales", files={"file": ("s.csv", b"date,sku\n2026-01-01,X\n", "text/csv")})
    assert r.status_code == 422
    assert "missing required column" in r.json()["detail"]["errors"][0]
    assert client.get("/api/v1/imports/templates/sales").status_code == 200


def test_jobs_endpoint(client):
    from app import jobs

    job_id = jobs.submit("classify", wait=True)
    body = client.get(f"/api/v1/jobs/{job_id}").json()
    assert body["status"] == "success"
    assert "Classified" in body["message"]
    assert client.post("/api/v1/jobs", json={"job_type": "nope"}).status_code == 422


def test_assistant_endpoint(client):
    status = client.get("/api/v1/assistant/status").json()
    assert status["mode"] == "offline"
    r = client.post("/api/v1/assistant/ask", json={"question": "Which products will run out next week?"})
    assert r.status_code == 200
    assert r.json()["tool_calls"][0]["name"] == "stockout_risk"
    assert client.post("/api/v1/assistant/ask", json={"question": ""}).status_code == 422
