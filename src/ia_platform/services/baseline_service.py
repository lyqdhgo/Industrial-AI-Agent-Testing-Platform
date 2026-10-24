"""基线与回归治理服务。"""

from __future__ import annotations

from uuid import uuid4

from ia_platform.core.models import (
    BaselineRecord,
    RegressionReport,
    RunRecord,
    RunStatus,
    utc_now,
)
from ia_platform.evaluation.regression import compare_runs
from ia_platform.services.repository import Repository


class BaselineServiceError(RuntimeError):
    pass


class BaselineService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def create_baseline(self, run_id: str, name: str | None = None) -> BaselineRecord:
        run = self.repository.get_run(run_id)
        if run is None:
            raise BaselineServiceError(f"运行不存在：{run_id}")
        if run.status != RunStatus.COMPLETED:
            raise BaselineServiceError("只有已完成的运行才能建立基线")
        if not run.case_results:
            raise BaselineServiceError("运行没有用例结果，不能建立基线")
        baseline = BaselineRecord(
            id=f"baseline-{utc_now().strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:6]}",
            name=name or f"{run.name} 基线",
            run_id=run.id,
            agent_version=run.agent_version,
            created_at=utc_now(),
            seed_set=list(run.seed_set),
            case_set_hash=run.domain_hashes.case_set_hash,
            domain_hash=run.domain_hashes.domain_hash,
            interlock_hash=run.domain_hashes.interlock_hash,
            results=list(run.case_results),
        )
        self.repository.save_baseline(baseline)
        return baseline

    def compare(
        self,
        candidate_run_id: str,
        baseline_id: str | None = None,
    ) -> RegressionReport:
        candidate = self._require_run(candidate_run_id)
        baseline = (
            self.repository.get_baseline(baseline_id)
            if baseline_id
            else self.repository.latest_baseline()
        )
        if baseline is None:
            raise BaselineServiceError("没有可用基线，请先创建基线")
        report = compare_runs(baseline, candidate)
        self.repository.save_regression(report)
        return report

    def latest_baseline(self) -> BaselineRecord | None:
        return self.repository.latest_baseline()

    def list_regressions(self, limit: int = 50) -> list[RegressionReport]:
        return self.repository.list_regressions(limit=limit)

    def _require_run(self, run_id: str) -> RunRecord:
        run = self.repository.get_run(run_id)
        if run is None:
            raise BaselineServiceError(f"运行不存在：{run_id}")
        return run
