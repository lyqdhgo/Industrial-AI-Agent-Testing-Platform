"""演示数据初始化。

启动后自动生成基准、退化回归与安全门禁三组运行，确保看板无需手工造数即可
展示漏报、误报、越权、联锁与复现性证据。所有数据均来自确定性 mock Agent。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from ia_platform.config import Settings
from ia_platform.core.catalog import PlatformCatalog
from ia_platform.core.models import DomainPack, RunRecord, RunStatus
from ia_platform.report.service import ReportService
from ia_platform.services.baseline_service import BaselineService
from ia_platform.services.repository import Repository
from ia_platform.services.run_service import RunService

logger = logging.getLogger(__name__)
_SEED_LOCK = threading.Lock()


@dataclass
class SeedResult:
    runs: list[RunRecord] = field(default_factory=list)
    baseline_id: str | None = None
    regression_id: str | None = None
    skipped: bool = False


class SeedService:
    def __init__(
        self,
        settings: Settings,
        catalog: PlatformCatalog,
        domain: DomainPack,
        repository: Repository,
        run_service: RunService,
        baseline_service: BaselineService,
        report_service: ReportService,
    ) -> None:
        self.settings = settings
        self.catalog = catalog
        self.domain = domain
        self.repository = repository
        self.run_service = run_service
        self.baseline_service = baseline_service
        self.report_service = report_service

    def seed(self, *, force: bool = False) -> SeedResult:
        with _SEED_LOCK:
            if self.repository.count_runs() > 0 and not force:
                logger.info("数据库已有运行记录，跳过演示数据初始化")
                return SeedResult(skipped=True)
            if force:
                self.repository.clear_all()

            result = SeedResult()
            logger.info("开始生成基准套件演示运行（参考与退化 Agent）")
            baseline_runs = self.run_service.run_suite(
                "suite-baseline", ["mock-reference", "mock-degraded"]
            )
            result.runs.extend(baseline_runs)
            baseline_run = next(
                (run for run in baseline_runs if run.agent_id == "mock-reference"),
                None,
            )
            degraded = next(
                (run for run in baseline_runs if run.agent_id == "mock-degraded"),
                None,
            )
            if baseline_run is None or baseline_run.status != RunStatus.COMPLETED:
                raise RuntimeError("基准运行未完成，无法建立基线")
            baseline = self.baseline_service.create_baseline(
                baseline_run.id, name="演示基准 v0.1.0"
            )
            result.baseline_id = baseline.id
            self._write_report(baseline_run.id)
            if degraded is not None and degraded.status == RunStatus.COMPLETED:
                regression = self.baseline_service.compare(
                    degraded.id, baseline_id=baseline.id
                )
                result.regression_id = regression.id
                self._write_report(
                    degraded.id,
                    baseline_id=baseline.id,
                    regression_id=regression.id,
                )
            elif degraded is not None:
                self._write_report(degraded.id)

            logger.info("开始生成安全门禁负向演示运行")
            safety_runs = self.run_service.run_suite("suite-safety-guard")
            result.runs.extend(safety_runs)
            for run in safety_runs:
                self._write_report(run.id)

            logger.info("演示数据初始化完成：%s 个运行", len(result.runs))
            return result

    @staticmethod
    def _completed(runs: list[RunRecord]) -> RunRecord:
        for run in runs:
            if run.status == RunStatus.COMPLETED:
                return run
        if runs:
            return runs[0]
        raise RuntimeError("套件没有产生运行记录")

    def _write_report(
        self,
        run_id: str,
        *,
        baseline_id: str | None = None,
        regression_id: str | None = None,
    ) -> None:
        try:
            self.report_service.generate(
                run_id, baseline_id=baseline_id, regression_id=regression_id
            )
        except Exception:
            logger.exception("生成报告失败：%s", run_id)
