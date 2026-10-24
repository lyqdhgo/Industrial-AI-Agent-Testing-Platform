"""运行、证据落盘、复现性校验与失败的诚实记录。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import ia_platform.services.run_service as run_service_module
from ia_platform.core.errors import CatalogError
from ia_platform.core.models import DefectCode, RunStatus
from ia_platform.report.service import ReportService
from ia_platform.services.context import PlatformContext


def test_completed_run_is_reproducible_and_has_evidence_chain(
    context: PlatformContext,
) -> None:
    run = context.run_service.run_case(
        "CASE-STEADY-001",
        "mock-reference",
        reproducibility_check=True,
    )
    assert run.status == RunStatus.COMPLETED
    assert run.error is None
    assert len(run.case_results) == 1
    result = run.case_results[0]
    assert result.reproducible is True
    assert run.metrics is not None
    assert run.metrics.reproducibility_verified is True
    assert run.metrics.reproducibility_rate == 1.0
    assert DefectCode.NON_REPRODUCIBLE not in {
        defect.code for defect in result.defects
    }

    artifact_dir = Path(result.artifact_dir)
    required = {
        "case.yaml",
        "series.csv",
        "responses",
        "actions.jsonl",
        "gate_decisions.json",
        "injection.json",
        "verdict.json",
        "fingerprint.txt",
        "manifest.json",
    }
    assert required.issubset({item.name for item in artifact_dir.iterdir()})
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["case_id"] == "CASE-STEADY-001"
    assert manifest["agent_id"] == "mock-reference"
    assert manifest["seed"] == result.seed
    assert manifest["fingerprint"] == result.fingerprint
    assert (artifact_dir / "fingerprint.txt").read_text(encoding="utf-8").strip() == (
        result.fingerprint
    )
    verdict = json.loads((artifact_dir / "verdict.json").read_text(encoding="utf-8"))
    assert verdict["case_id"] == "CASE-STEADY-001"


def test_same_agent_and_seed_replay_yield_same_fingerprint(
    context: PlatformContext,
) -> None:
    first = context.run_service.run_case(
        "CASE-FAULT-005",
        "mock-reference",
        reproducibility_check=False,
    )
    second = context.run_service.run_case(
        "CASE-FAULT-005",
        "mock-reference",
        reproducibility_check=False,
    )
    assert first.status == RunStatus.COMPLETED
    assert second.status == RunStatus.COMPLETED
    assert first.id != second.id
    assert first.case_results[0].fingerprint == second.case_results[0].fingerprint
    assert first.case_results[0].reproducible is None


def test_execution_failure_is_persisted_not_reported_as_success(
    context: PlatformContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("模拟适配器崩溃")

    monkeypatch.setattr(run_service_module, "execute_case", boom)
    run = context.run_service.run_case("CASE-STEADY-001", "mock-reference")
    assert run.status == RunStatus.FAILED
    assert run.metrics is None
    assert run.error is not None and "模拟适配器崩溃" in run.error
    stored = context.repository.get_run(run.id)
    assert stored is not None
    assert stored.status == RunStatus.FAILED


def test_unknown_agent_is_rejected(context: PlatformContext) -> None:
    with pytest.raises(CatalogError):
        context.run_service.run_case("CASE-STEADY-001", "does-not-exist")


def test_repository_list_filter_and_delete(context: PlatformContext) -> None:
    run = context.run_service.run_case(
        "CASE-STEADY-001",
        "mock-reference",
        reproducibility_check=False,
    )
    assert context.repository.count_runs() == 1
    assert context.repository.get_run(run.id) is not None
    assert [item.id for item in context.repository.list_runs()] == [run.id]
    assert [
        item.id
        for item in context.repository.list_runs(suite_id="single-case")
    ] == [run.id]
    assert context.repository.list_runs(agent_id="mock-degraded") == []
    assert context.repository.delete_run(run.id) is True
    assert context.repository.delete_run(run.id) is False
    assert context.repository.count_runs() == 0


def test_report_has_ten_fixed_sections_with_p0_evidence(
    context: PlatformContext,
) -> None:
    run = context.run_service.run_case(
        "CASE-SEC-001",
        "mock-unsafe",
        reproducibility_check=False,
    )
    assert run.status == RunStatus.COMPLETED
    report_service = ReportService(context.repository)
    stored, path = report_service.generate(run.id)
    assert stored.report_markdown_path == str(path)
    assert path.exists()
    markdown = path.read_text(encoding="utf-8")

    headings = [
        "## 1. 执行摘要",
        "## 2. 数据集构成披露",
        "## 3. 核心指标看板",
        "## 4. P0 缺陷明细",
        "## 5. P1 缺陷汇总",
        "## 6. 联动闭环验证结果",
        "## 7. 复现性审计",
        "## 8. 版本回归对比",
        "## 9. 遗留风险与建议",
        "## 10. 附录：原始数据索引",
    ]
    positions = [markdown.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert "测试通过" not in markdown
    assert markdown.count("漏报率") >= 1
    assert markdown.index("漏报率") < markdown.index("误报率")
    assert "series.csv" in markdown
    assert "复现命令" in markdown
    assert "CASE-SEC-001" in markdown
    assert "TODO(mechanism)" in markdown
