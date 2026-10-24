"""纯评测层：只消费仿真证据与平台契约，不依赖具体仿真器实现。"""

from __future__ import annotations

from ia_platform.evaluation.checks import evaluate_case, verify_injection_mechanisms
from ia_platform.evaluation.metrics import build_dataset_composition, compute_metrics
from ia_platform.evaluation.regression import compare_runs

__all__ = [
    "build_dataset_composition",
    "compare_runs",
    "compute_metrics",
    "evaluate_case",
    "verify_injection_mechanisms",
]
