"""报告生成与运行记录回写服务。"""

from __future__ import annotations

from pathlib import Path

from ia_platform.core.models import BaselineRecord, RegressionReport, RunRecord
from ia_platform.report.generator import write_report
from ia_platform.services.repository import Repository


class ReportServiceError(RuntimeError):
    pass


class ReportService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def generate(
        self,
        run_id: str,
        *,
        baseline_id: str | None = None,
        regression_id: str | None = None,
        path: Path | None = None,
    ) -> tuple[RunRecord, Path]:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ReportServiceError(f"运行不存在：{run_id}")
        baseline: BaselineRecord | None = (
            self.repository.get_baseline(baseline_id) if baseline_id else None
        )
        if baseline_id and baseline is None:
            raise ReportServiceError(f"基线不存在：{baseline_id}")
        regression: RegressionReport | None = (
            self.repository.get_regression(regression_id) if regression_id else None
        )
        if regression_id and regression is None:
            raise ReportServiceError(f"回归报告不存在：{regression_id}")
        target = path or self.default_path(run)
        written = write_report(
            run, baseline=baseline, regression=regression, path=target
        )
        updated = run.model_copy(update={"report_markdown_path": str(written)})
        self.repository.save_run(updated)
        return updated, written

    @staticmethod
    def default_path(run: RunRecord) -> Path:
        if run.case_results:
            return Path(run.case_results[0].artifact_dir).parent / "report.md"
        return Path("artifacts") / "runs" / run.id / "report.md"
