"""FastAPI 证据查看接口与安全路径检查。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from ia_platform.api.main import create_app
from ia_platform.services.context import PlatformContext


def _client(context: PlatformContext) -> TestClient:
    app = create_app(
        settings=context.settings,
        context=context,
        auto_seed=False,
    )
    return TestClient(app)


def test_health_meta_and_empty_dashboard(context: PlatformContext) -> None:
    with _client(context) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert health.json()["runs"] == 0

        meta = client.get("/api/meta")
        assert meta.status_code == 200
        payload = meta.json()
        assert payload["domain"]["pack_id"] == "demo-reactor"
        assert len(payload["sensors"]) == 4
        assert len(payload["interlocks"]) == 2
        assert payload["cases"]
        assert payload["agents"]
        assert payload["suites"]
        assert payload["domain"]["hashes"]["interlock_hash"]

        dashboard = client.get("/api/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["hero_run"] is None
        assert dashboard.json()["p0_defects"] == []
        assert dashboard.json()["seed_running"] is True

        assert client.get("/api/interlocks").status_code == 404


def test_run_evidence_report_baseline_and_regression_endpoints(
    context: PlatformContext,
) -> None:
    with _client(context) as client:
        created = client.post(
            "/api/runs",
            json={"suite_id": "suite-smoke", "name": "API 冒烟"},
        )
        assert created.status_code == 201, created.text
        items = created.json()["items"]
        assert len(items) == 1
        run = items[0]
        run_id = run["id"]
        assert run["status"] == "completed"
        assert run["case_count"] == 2
        case_id = run["cases"][0]["case_id"]
        assert run["metrics"]["reproducibility_verified"] is False

        listing = client.get("/api/runs", params={"suite_id": "suite-smoke"})
        assert listing.status_code == 200
        assert listing.json()["total"] == 1
        assert listing.json()["items"][0]["id"] == run_id

        detail = client.get(f"/api/runs/{run_id}")
        assert detail.status_code == 200
        assert detail.json()["id"] == run_id
        assert len(detail.json()["case_results"]) == 2
        assert detail.json()["case_meta"][case_id]["id"] == case_id

        case_detail = client.get(f"/api/runs/{run_id}/cases/{case_id}")
        assert case_detail.status_code == 200
        assert case_detail.json()["result"]["case_id"] == case_id
        assert "series.csv" in case_detail.json()["files"]

        series = client.get(
            f"/api/runs/{run_id}/cases/{case_id}/series",
            params={"tag": "TI-203", "max_points": 10},
        )
        assert series.status_code == 200
        series_payload = series.json()
        assert series_payload["tag"] == "TI-203"
        assert len(series_payload["points"]) <= 11
        assert series_payload["downsampled"] is True
        assert series_payload["total_before_downsample"] > 10
        assert client.get(
            f"/api/runs/{run_id}/cases/{case_id}/series",
            params={"tag": "XX-999"},
        ).status_code == 404

        responses = client.get(f"/api/runs/{run_id}/cases/{case_id}/responses")
        assert responses.status_code == 200
        response_items = responses.json()["items"]
        assert response_items
        first_index = response_items[0]["index"]
        raw = client.get(
            f"/api/runs/{run_id}/cases/{case_id}/responses/{first_index}"
        )
        assert raw.status_code == 200
        assert raw.json()["response"]["status"]
        assert raw.json()["fingerprint"]

        artifact = client.get(
            f"/api/runs/{run_id}/cases/{case_id}/artifact",
            params={"path": "verdict.json"},
        )
        assert artifact.status_code == 200
        assert artifact.headers["content-type"].startswith("application/json")
        traversal = client.get(
            f"/api/runs/{run_id}/cases/{case_id}/artifact",
            params={"path": "../../../../etc/passwd"},
        )
        assert traversal.status_code == 400

        generated = client.post(f"/api/runs/{run_id}/report")
        assert generated.status_code == 200, generated.text
        assert "## 1. 执行摘要" in generated.json()["markdown"]
        report = client.get(f"/api/runs/{run_id}/report")
        assert report.status_code == 200
        assert "## 10. 附录：原始数据索引" in report.json()["markdown"]
        report_file = client.get(f"/api/runs/{run_id}/report.md")
        assert report_file.status_code == 200
        assert "text/markdown" in report_file.headers["content-type"]

        baseline = client.post(
            "/api/baselines",
            json={"run_id": run_id, "name": "API 基线"},
        )
        assert baseline.status_code == 201, baseline.text
        baseline_id = baseline.json()["id"]
        assert baseline.json()["case_count"] == 2
        assert client.get("/api/baselines").json()["items"]
        baseline_detail = client.get(f"/api/baselines/{baseline_id}")
        assert baseline_detail.status_code == 200
        assert len(baseline_detail.json()["results"]) == 2

        regression = client.post(
            "/api/regressions",
            json={"candidate_run_id": run_id, "baseline_id": baseline_id},
        )
        assert regression.status_code == 201, regression.text
        regression_payload = regression.json()
        assert regression_payload["comparable"] is True
        assert regression_payload["fingerprint_match_rate"] == 1.0
        assert regression_payload["severe_regressions"] == []
        assert client.get("/api/regressions").json()["items"]
        assert (
            client.get(f"/api/regressions/{regression_payload['id']}").status_code
            == 200
        )

        dashboard = client.get("/api/dashboard").json()
        assert dashboard["hero_run"]["id"] == run_id
        assert dashboard["latest_baseline"]["id"] == baseline_id
        assert dashboard["latest_regression"]["id"] == regression_payload["id"]
        assert dashboard["catalog"]["case_count"] == len(
            client.get("/api/cases").json()
        )

        assert client.get("/api/runs/not-found").status_code == 404
        assert client.get("/api/baselines/not-found").status_code == 404
        assert client.get("/api/regressions/not-found").status_code == 404


def test_invalid_run_request_is_a_4xx_response(context: PlatformContext) -> None:
    with _client(context) as client:
        response = client.post("/api/runs", json={"suite_id": "suite-missing"})
        assert response.status_code == 400
        assert "未知套件" in response.json()["detail"]
        invalid = client.post(
            "/api/runs/case/CASE-STEADY-001",
            json={"agent_id": "missing-agent"},
        )
        assert invalid.status_code == 400
