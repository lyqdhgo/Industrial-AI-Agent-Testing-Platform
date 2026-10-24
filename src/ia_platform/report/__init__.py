"""测试报告生成。"""

from __future__ import annotations

from ia_platform.report.generator import render_report, write_report
from ia_platform.report.service import ReportService, ReportServiceError

__all__ = [
    "ReportService",
    "ReportServiceError",
    "render_report",
    "write_report",
]
