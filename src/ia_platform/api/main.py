"""FastAPI 后端。

接口只暴露证据与判定，不提供任何联锁修改、旁路或 DCS 直写入口。所有运行均走
RunService 的确定性执行链；前端拿到的指标与报告均来自同一份落盘证据。
"""

from __future__ import annotations

import csv
import json
import logging
import math
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from ia_platform.config import Settings
from ia_platform.core.errors import IatpError
from ia_platform.core.models import (
    BaselineRecord,
    CaseResult,
    DefectLevel,
    RegressionReport,
    RunRecord,
    RunStatus,
)
from ia_platform.report.service import ReportServiceError
from ia_platform.services.baseline_service import BaselineServiceError
from ia_platform.services.context import PlatformContext
from ia_platform.services.run_service import RunServiceError

logger = logging.getLogger(__name__)

_PROJECT_DISCLAIMER = (
    "演示域为合成机理数据，不代表真实装置工程数据；不得据此签发安全认证。"
)


# ---------------------------------------------------------------------------
# 请求契约
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    suite_id: str
    agent_ids: list[str] | None = None
    name: str | None = None
    seed: int | None = Field(default=None, ge=0)
    reproducibility_check: bool | None = None


class CaseRunRequest(BaseModel):
    agent_id: str
    seed: int | None = Field(default=None, ge=0)
    reproducibility_check: bool | None = None


class BaselineRequest(BaseModel):
    run_id: str
    name: str | None = None


class RegressionRequest(BaseModel):
    candidate_run_id: str
    baseline_id: str | None = None


class ReportRequest(BaseModel):
    baseline_id: str | None = None
    regression_id: str | None = None


# ---------------------------------------------------------------------------
# 序列化辅助
# ---------------------------------------------------------------------------


def _dt(value: Any) -> str | None:
    return None if value is None else value.isoformat()


def _case_brief(result: CaseResult) -> dict[str, Any]:
    p0 = sum(1 for item in result.defects if item.level == DefectLevel.P0)
    p1 = sum(1 for item in result.defects if item.level == DefectLevel.P1)
    return {
        "case_id": result.case_id,
        "case_name": result.case_name,
        "category": result.category.value,
        "detected": result.detected,
        "correct_type": result.correct_type,
        "latency_s": result.latency_s,
        "false_alarms": result.false_alarms,
        "high_risk_false_alarms": result.high_risk_false_alarms,
        "unsafe_setpoints": result.unsafe_setpoints,
        "unauthorized_attempts": result.unauthorized_attempts,
        "p0": p0,
        "p1": p1,
        "fingerprint": result.fingerprint,
        "reproducible": result.reproducible,
        "action_trace_match": result.action_trace_match,
        "artifact_dir": result.artifact_dir,
    }


def _run_summary(run: RunRecord) -> dict[str, Any]:
    return {
        "id": run.id,
        "name": run.name,
        "suite_id": run.suite_id,
        "agent_id": run.agent_id,
        "agent_name": run.agent_name,
        "agent_version": run.agent_version,
        "seed": run.seed,
        "seed_set": run.seed_set,
        "status": run.status.value,
        "created_at": _dt(run.created_at),
        "started_at": _dt(run.started_at),
        "finished_at": _dt(run.finished_at),
        "case_count": len(run.case_ids),
        "metrics": None
        if run.metrics is None
        else run.metrics.model_dump(mode="json"),
        "cases": [_case_brief(item) for item in run.case_results],
        "report_available": bool(
            run.report_markdown_path
            and Path(run.report_markdown_path).exists()
        ),
        "error": run.error,
        "reproducibility_unverified": run.reproducibility_unverified,
        "domain_hashes": run.domain_hashes.model_dump(mode="json"),
    }


def _baseline_summary(baseline: BaselineRecord) -> dict[str, Any]:
    p0 = sum(
        1
        for result in baseline.results
        for defect in result.defects
        if defect.level == DefectLevel.P0
    )
    return {
        "id": baseline.id,
        "name": baseline.name,
        "run_id": baseline.run_id,
        "agent_version": baseline.agent_version,
        "created_at": _dt(baseline.created_at),
        "seed_set": baseline.seed_set,
        "case_set_hash": baseline.case_set_hash,
        "domain_hash": baseline.domain_hash,
        "interlock_hash": baseline.interlock_hash,
        "case_count": len(baseline.results),
        "p0": p0,
    }


def _regression_dict(report: RegressionReport) -> dict[str, Any]:
    return report.model_dump(mode="json")


def _case_definition(case: Any) -> dict[str, Any]:
    return {
        "id": case.id,
        "name": case.name,
        "description": case.description,
        "category": case.category.value,
        "source": case.source.value,
        "provenance": case.provenance,
        "seed": case.seed,
        "duration_s": case.duration_s,
        "decision_interval_s": case.decision_interval_s,
        "history_window_s": case.history_window_s,
        "tags": case.tags,
        "timeline": [item.model_dump(mode="json") for item in case.timeline],
        "initial_conditions": [
            item.model_dump(mode="json") for item in case.initial_conditions
        ],
        "faults": [
            {
                "kind": fault.kind.value,
                "target_tag": fault.target_tag,
                "start_s": fault.start_s,
                "duration_s": fault.duration_s,
                "params": {
                    key: item.model_dump(mode="json")
                    for key, item in fault.params.items()
                },
            }
            for fault in case.faults
        ],
        "expected": case.expected.model_dump(mode="json"),
        "operator": case.operator.model_dump(mode="json"),
    }


def _meta(ctx: PlatformContext) -> dict[str, Any]:
    domain = ctx.domain
    sensors = []
    for tag, sensor in domain.sensors.items():
        bound = domain.bounds_for(tag)
        sensors.append(
            {
                "tag": tag,
                "name": sensor.name,
                "kind": sensor.kind,
                "unit": sensor.unit,
                "range": {
                    "low": sensor.instrument_range.low,
                    "high": sensor.instrument_range.high,
                    "unit": sensor.instrument_range.unit,
                },
                "sample_interval_s": sensor.sample_interval_s,
                "safe_limits": bound.safe_limits.model_dump(mode="json"),
                "recommended_band": bound.recommended_band.model_dump(mode="json"),
                "trip_limits": bound.trip_limits.model_dump(mode="json"),
                "mechanism_basis": bound.mechanism_basis,
            }
        )
    cases = [
        _case_definition(ctx.catalog.cases[key])
        for key in sorted(ctx.catalog.cases)
    ]
    agents = [
        ctx.catalog.agents[key].model_dump(mode="json")
        for key in sorted(ctx.catalog.agents)
    ]
    suites = [
        {
            "id": suite.id,
            "name": suite.name,
            "description": suite.description,
            "case_ids": suite.case_ids,
            "agent_ids": suite.agent_ids,
        }
        for suite in ctx.catalog.suites.values()
    ]
    interlocks = [
        {
            "id": rule.id,
            "tag": rule.tag,
            "name": rule.name,
            "condition": rule.condition,
            "trip_limit": rule.trip_limit.model_dump(mode="json"),
            "action": rule.action.value,
            "layer": rule.layer.value,
            "bypassable": rule.bypassable,
            "note": rule.note,
        }
        for rule in domain.interlocks
    ]
    return {
        "domain": {
            "pack_id": domain.pack_id,
            "asset_id": domain.asset_id,
            "asset_name": domain.asset_name,
            "disclaimer": domain.disclaimer,
            "provenance": domain.provenance.value,
            "hashes": domain.hashes.model_dump(mode="json"),
            "assumptions": domain.assumptions,
            "timebase": domain.timebase.model_dump(mode="json"),
        },
        "sensors": sensors,
        "interlocks": interlocks,
        "cases": cases,
        "agents": agents,
        "suites": suites,
        "case_set_hash": ctx.catalog.case_set_hash,
        "platform_disclaimer": _PROJECT_DISCLAIMER,
    }


def _artifact_dir(run: RunRecord, case_id: str) -> Path:
    for result in run.case_results:
        if result.case_id == case_id:
            root = Path(result.artifact_dir).resolve()
            if not root.exists():
                raise HTTPException(status_code=404, detail="证据目录不存在")
            return root
    raise HTTPException(status_code=404, detail="用例不在该运行中")


def _safe_artifact_file(root: Path, relative: str) -> Path:
    if not relative or relative.startswith(("/", "\\")):
        raise HTTPException(status_code=400, detail="非法证据路径")
    target = (root / relative).resolve()
    if root != target and root not in target.parents:
        raise HTTPException(status_code=400, detail="证据路径越界")
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"证据文件不存在：{relative}")
    return target


def _read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"证据文件损坏：{path.name}") from exc


def _response_summary(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    response = payload.get("response") or {}
    return {
        "index": payload.get("index"),
        "observed_at_s": payload.get("observed_at_s"),
        "observation_id": payload.get("observation_id"),
        "status": response.get("status"),
        "fault_type": response.get("fault_type"),
        "target_tag": response.get("target_tag"),
        "confidence": response.get("confidence"),
        "rationale_text": response.get("rationale_text"),
        "degraded_mode": response.get("degraded_mode"),
        "setpoint_count": len(response.get("setpoints") or []),
        "control_request_count": len(response.get("control_requests") or []),
        "fingerprint": payload.get("fingerprint"),
        "latency_ms": payload.get("latency_ms"),
    }


def _read_series(root: Path, tag: str, max_points: int) -> dict[str, Any]:
    path = root / "series.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="series.csv 不存在")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("tag") != tag:
                continue
            rows.append(
                {
                    "t_s": float(row["t_s"]),
                    "true_value": float(row["true_value"]),
                    "measured_value": (
                        None
                        if row.get("measured_value") in {None, ""}
                        else float(row["measured_value"])
                    ),
                    "quality": row.get("quality"),
                    "delivered": row.get("delivered") == "true",
                    "command_value": (
                        None
                        if row.get("command_value") in {None, ""}
                        else float(row["command_value"])
                    ),
                    "received_s": float(row["received_s"]),
                    "unit": row.get("unit"),
                }
            )
    if not rows:
        raise HTTPException(status_code=404, detail=f"位号 {tag} 无时序数据")
    total_rows = len(rows)
    downsampled = False
    if total_rows > max_points:
        step = max(1, math.ceil(total_rows / max_points))
        sampled = rows[::step]
        if sampled and sampled[-1] is not rows[-1]:
            sampled.append(rows[-1])
        rows = sampled
        downsampled = True
    return {
        "tag": tag,
        "unit": rows[0]["unit"],
        "points": rows,
        "total_before_downsample": total_rows,
        "downsampled": downsampled,
        "source": "series.csv",
    }


def _latest_dashboard(ctx: PlatformContext) -> dict[str, Any]:
    runs = ctx.repository.list_runs(limit=8)
    baseline = ctx.repository.latest_baseline()
    baseline_run = (
        ctx.repository.get_run(baseline.run_id) if baseline is not None else None
    )
    chosen = baseline_run
    if chosen is None or chosen.metrics is None:
        chosen = next(
            (
                run
                for run in runs
                if run.status == RunStatus.COMPLETED and run.metrics is not None
            ),
            None,
        )
    metrics = chosen.metrics if chosen is not None else None
    p0: list[dict[str, Any]] = []
    p1: list[dict[str, Any]] = []
    if chosen is not None:
        for result in chosen.case_results:
            for defect in result.defects:
                item = {
                    "case_id": result.case_id,
                    "case_name": result.case_name,
                    "code": defect.code.value,
                    "title": defect.title,
                    "occurred_at_s": defect.occurred_at_s,
                    "detail": defect.detail,
                    "artifact_dir": result.artifact_dir,
                }
                if defect.level == DefectLevel.P0:
                    p0.append(item)
                elif defect.level == DefectLevel.P1:
                    p1.append(item)
    regressions = ctx.repository.list_regressions(limit=3)
    return {
        "runs": [_run_summary(run) for run in runs],
        "latest_baseline": _baseline_summary(baseline) if baseline else None,
        "latest_regression": _regression_dict(regressions[0])
        if regressions
        else None,
        "hero_run": _run_summary(chosen) if chosen is not None else None,
        "metrics": None if metrics is None else metrics.model_dump(mode="json"),
        "p0_defects": p0,
        "p1_defects": p1,
        "catalog": {
            "case_count": len(ctx.catalog.cases),
            "agent_count": len(ctx.catalog.agents),
            "suite_count": len(ctx.catalog.suites),
            "case_set_hash": ctx.catalog.case_set_hash,
        },
        "seed_running": ctx.repository.count_runs() == 0,
    }


# ---------------------------------------------------------------------------
# 应用工厂
# ---------------------------------------------------------------------------


def create_app(
    settings: Settings | None = None,
    *,
    context: PlatformContext | None = None,
    auto_seed: bool | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.load()
    ctx = context or PlatformContext.build(resolved_settings)
    should_seed = resolved_settings.auto_seed if auto_seed is None else auto_seed

    def seed_worker() -> None:
        try:
            ctx.seed_service.seed()
        except Exception:
            logger.exception("演示数据初始化失败")

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        if should_seed and ctx.repository.count_runs() == 0:
            threading.Thread(
                target=seed_worker, name="iatp-demo-seed", daemon=True
            ).start()
        yield

    application = FastAPI(
        title="IATP 工业 AI Agent 测试平台",
        version="0.1.0",
        description=(
            "面向工业 Agent 的确定性测试、安全门禁验证、联锁闭环与证据链平台。"
            f"{_PROJECT_DISCLAIMER}"
        ),
        lifespan=lifespan,
    )
    application.state.ctx = ctx
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "runs": ctx.repository.count_runs(),
            "auto_seed": should_seed,
            "domain": ctx.domain.pack_id,
            "version": "0.1.0",
        }

    @application.get("/api/meta")
    def meta() -> dict[str, Any]:
        return _meta(ctx)

    @application.get("/api/dashboard")
    def dashboard() -> dict[str, Any]:
        return _latest_dashboard(ctx)

    @application.get("/api/cases")
    def cases() -> list[dict[str, Any]]:
        return [
            _case_definition(ctx.catalog.cases[key])
            for key in sorted(ctx.catalog.cases)
        ]

    @application.get("/api/agents")
    def agents() -> list[dict[str, Any]]:
        return [
            ctx.catalog.agents[key].model_dump(mode="json")
            for key in sorted(ctx.catalog.agents)
        ]

    @application.get("/api/suites")
    def suites() -> list[dict[str, Any]]:
        return [
            {
                "id": suite.id,
                "name": suite.name,
                "description": suite.description,
                "case_ids": suite.case_ids,
                "agent_ids": suite.agent_ids,
            }
            for suite in ctx.catalog.suites.values()
        ]

    @application.get("/api/runs")
    def list_runs(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        suite_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        items = ctx.repository.list_runs(
            limit=limit, offset=offset, suite_id=suite_id, agent_id=agent_id
        )
        return {
            "items": [_run_summary(run) for run in items],
            "count": len(items),
            "total": ctx.repository.count_runs(),
            "limit": limit,
            "offset": offset,
        }

    @application.post("/api/runs", status_code=201)
    def create_run(payload: RunRequest) -> dict[str, Any]:
        try:
            runs = ctx.run_service.run_suite(
                payload.suite_id,
                payload.agent_ids,
                name=payload.name,
                seed_override=payload.seed,
                reproducibility_check=payload.reproducibility_check,
            )
        except (RunServiceError, IatpError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "items": [_run_summary(run) for run in runs],
            "count": len(runs),
        }

    @application.post("/api/runs/case/{case_id}", status_code=201)
    def create_case_run(case_id: str, payload: CaseRunRequest) -> dict[str, Any]:
        try:
            run = ctx.run_service.run_case(
                case_id,
                payload.agent_id,
                seed_override=payload.seed,
                reproducibility_check=payload.reproducibility_check,
            )
        except (RunServiceError, IatpError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _run_summary(run)

    @application.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        run = ctx.repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="运行不存在")
        payload = run.model_dump(mode="json")
        payload["case_meta"] = {
            result.case_id: _case_definition(ctx.catalog.get_case(result.case_id))
            if result.case_id in ctx.catalog.cases
            else None
            for result in run.case_results
        }
        payload["report_available"] = bool(
            run.report_markdown_path and Path(run.report_markdown_path).exists()
        )
        return payload

    @application.get("/api/runs/{run_id}/cases/{case_id}")
    def get_case_result(run_id: str, case_id: str) -> dict[str, Any]:
        run = ctx.repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="运行不存在")
        result = next(
            (item for item in run.case_results if item.case_id == case_id), None
        )
        if result is None:
            raise HTTPException(status_code=404, detail="用例不在该运行中")
        root = _artifact_dir(run, case_id)
        files = sorted(
            str(path.relative_to(root)).replace("\\", "/")
            for path in root.rglob("*")
            if path.is_file()
        )
        return {
            "run": _run_summary(run),
            "result": result.model_dump(mode="json"),
            "case": _case_definition(ctx.catalog.get_case(case_id))
            if case_id in ctx.catalog.cases
            else None,
            "files": files,
            "artifact_dir": str(root),
        }

    @application.get("/api/runs/{run_id}/cases/{case_id}/series")
    def get_series(
        run_id: str,
        case_id: str,
        tag: str = Query(default="TI-203"),
        max_points: int = Query(default=1500, ge=10, le=10000),
    ) -> dict[str, Any]:
        run = ctx.repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="运行不存在")
        root = _artifact_dir(run, case_id)
        return _read_series(root, tag, max_points)

    @application.get("/api/runs/{run_id}/cases/{case_id}/responses")
    def list_responses(run_id: str, case_id: str) -> dict[str, Any]:
        run = ctx.repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="运行不存在")
        root = _artifact_dir(run, case_id)
        directory = root / "responses"
        items = []
        if directory.exists():
            for path in sorted(directory.glob("call-*.json")):
                summary = _response_summary(path)
                if summary is not None:
                    items.append(summary)
        return {"items": items, "count": len(items)}

    @application.get(
        "/api/runs/{run_id}/cases/{case_id}/responses/{index}"
    )
    def get_response(run_id: str, case_id: str, index: int) -> Any:
        run = ctx.repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="运行不存在")
        root = _artifact_dir(run, case_id)
        path = _safe_artifact_file(root, f"responses/call-{index:04d}.json")
        return _read_json_file(path)

    @application.get("/api/runs/{run_id}/cases/{case_id}/artifact")
    def get_artifact(
        run_id: str,
        case_id: str,
        path: str = Query(default="verdict.json"),
    ) -> FileResponse:
        run = ctx.repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="运行不存在")
        root = _artifact_dir(run, case_id)
        target = _safe_artifact_file(root, path)
        suffix = target.suffix.lower()
        media = {
            ".json": "application/json",
            ".csv": "text/csv",
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".jsonl": "application/x-ndjson",
            ".yaml": "application/x-yaml",
            ".yml": "application/x-yaml",
        }.get(suffix, "application/octet-stream")
        return FileResponse(target, media_type=media, filename=target.name)

    @application.get("/api/runs/{run_id}/report")
    def get_report(run_id: str) -> dict[str, Any]:
        run = ctx.repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="运行不存在")
        path = (
            Path(run.report_markdown_path)
            if run.report_markdown_path
            else ctx.report_service.default_path(run)
        )
        if not path.exists():
            raise HTTPException(
                status_code=404,
                detail="报告尚未生成，可调用 POST /api/runs/{run_id}/report",
            )
        return {
            "run_id": run.id,
            "markdown": path.read_text(encoding="utf-8"),
            "path": str(path),
            "generated_at": _dt(run.finished_at),
        }

    @application.post("/api/runs/{run_id}/report")
    def create_report(
        run_id: str, payload: ReportRequest | None = None
    ) -> dict[str, Any]:
        try:
            run, path = ctx.report_service.generate(
                run_id,
                baseline_id=payload.baseline_id if payload else None,
                regression_id=payload.regression_id if payload else None,
            )
        except ReportServiceError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "run_id": run.id,
            "path": str(path),
            "markdown": path.read_text(encoding="utf-8"),
        }

    @application.get("/api/runs/{run_id}/report.md")
    def get_report_file(run_id: str) -> FileResponse:
        run = ctx.repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="运行不存在")
        path = (
            Path(run.report_markdown_path)
            if run.report_markdown_path
            else ctx.report_service.default_path(run)
        )
        if not path.exists():
            raise HTTPException(status_code=404, detail="报告尚未生成")
        return FileResponse(path, media_type="text/markdown", filename="report.md")

    @application.get("/api/baselines")
    def list_baselines() -> dict[str, Any]:
        items = ctx.repository.list_baselines(limit=100)
        return {"items": [_baseline_summary(item) for item in items]}

    @application.post("/api/baselines", status_code=201)
    def create_baseline(payload: BaselineRequest) -> dict[str, Any]:
        try:
            baseline = ctx.baseline_service.create_baseline(
                payload.run_id, payload.name
            )
        except BaselineServiceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _baseline_summary(baseline)

    @application.get("/api/baselines/{baseline_id}")
    def get_baseline(baseline_id: str) -> dict[str, Any]:
        baseline = ctx.repository.get_baseline(baseline_id)
        if baseline is None:
            raise HTTPException(status_code=404, detail="基线不存在")
        payload = _baseline_summary(baseline)
        payload["results"] = [
            result.model_dump(mode="json") for result in baseline.results
        ]
        return payload

    @application.get("/api/regressions")
    def list_regressions() -> dict[str, Any]:
        return {
            "items": [
                _regression_dict(item)
                for item in ctx.repository.list_regressions(limit=100)
            ]
        }

    @application.post("/api/regressions", status_code=201)
    def create_regression(payload: RegressionRequest) -> dict[str, Any]:
        try:
            report = ctx.baseline_service.compare(
                payload.candidate_run_id, baseline_id=payload.baseline_id
            )
        except BaselineServiceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _regression_dict(report)

    @application.get("/api/regressions/{report_id}")
    def get_regression(report_id: str) -> dict[str, Any]:
        report = ctx.repository.get_regression(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="回归报告不存在")
        return _regression_dict(report)

    @application.exception_handler(IatpError)
    async def _iatp_error(_request: Any, exc: IatpError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # 静态前端（构建后存在 dist 才启用；开发时由 Vite 提供）。
    dist = resolved_settings.project_root / "frontend" / "dist"
    if dist.exists():
        @application.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str) -> FileResponse:
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="接口不存在")
            candidate = (dist / full_path).resolve()
            root = dist.resolve()
            if candidate.is_file() and (root == candidate or root in candidate.parents):
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return application


app = create_app()
