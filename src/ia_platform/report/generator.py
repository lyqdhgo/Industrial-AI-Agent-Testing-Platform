"""固定十段式工业 Agent 测试报告。

报告的唯一使命是让评审者不重跑测试也能判断：Agent 安不安全、结论可不可信。
因此数据集构成先于指标，漏报率置顶，每条 P0 附原始时序与原始响应双证据。
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

from ia_platform.core.models import (
    BaselineRecord,
    CaseCategory,
    CaseResult,
    Defect,
    DefectLevel,
    InterlockEvaluation,
    RegressionReport,
    RunRecord,
    TraceEventKind,
    utc_now,
)

_TRACE_LABELS = {
    TraceEventKind.AGENT_SUGGESTION: "AI 建议",
    TraceEventKind.GATE_ALLOWED: "Gate 放行",
    TraceEventKind.GATE_BLOCKED: "Gate 拒绝",
    TraceEventKind.CONFIRMATION_REQUIRED: "请求人工确认",
    TraceEventKind.CONFIRMATION_GRANTED: "人工确认",
    TraceEventKind.DCS_WRITE: "DCS 写入",
    TraceEventKind.SIS_TRIGGERED: "SIS 动作",
    TraceEventKind.SIS_BLOCKED: "SIS 阻断",
    TraceEventKind.DEGRADED_MODE: "降级模式",
    TraceEventKind.RETRY_BLOCKED: "拒绝后重试被阻断",
}

_CATEGORY_LABELS = {
    CaseCategory.STEADY: "稳态",
    CaseCategory.BOUNDARY: "边界",
    CaseCategory.FAULT: "注入故障",
    CaseCategory.INTERLOCK: "联锁闭环",
}


def _pct(value: float | None) -> str:
    return "未验证" if value is None else f"{value * 100:.1f}%"


def _num(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _case_dir(result: CaseResult) -> Path:
    return Path(result.artifact_dir)


def _case_definition(result: CaseResult) -> dict[str, Any]:
    path = _case_dir(result) / "case.yaml"
    if not path.exists():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _case_fault_text(definition: dict[str, Any]) -> str:
    faults = definition.get("faults")
    if not isinstance(faults, list) or not faults:
        return "—"
    parts = []
    for item in faults:
        if isinstance(item, dict):
            parts.append(
                f"{item.get('kind', '?')}@{item.get('start_s', '?')}s/"
                f"{item.get('duration_s', '?')}s"
            )
    return "；".join(parts) if parts else "—"


def _nearest_response(result: CaseResult, at_s: float | None) -> str | None:
    directory = _case_dir(result) / "responses"
    if not directory.exists():
        return None
    candidates: list[tuple[float, Path]] = []
    for path in sorted(directory.glob("call-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            observed = float(payload.get("observed_at_s", 0.0))
        except (OSError, ValueError, TypeError):
            continue
        distance = 0.0 if at_s is None else abs(observed - at_s)
        candidates.append((distance, path))
    if not candidates:
        return None
    return str(min(candidates, key=lambda item: item[0])[1])


def _evidence_path(result: CaseResult, relative: str) -> str:
    return str(_case_dir(result) / relative)


def _trace_text(sequence: Iterable[TraceEventKind]) -> str:
    labels: list[str] = []
    for kind in sequence:
        labels.append(_TRACE_LABELS.get(kind, kind.value))
    if not labels:
        return "（无）"
    compact: list[str] = []
    previous: str | None = None
    count = 0
    for label in labels:
        if label == previous:
            count += 1
            continue
        if previous is not None:
            compact.append(previous if count == 1 else f"{previous}×{count}")
        previous = label
        count = 1
    if previous is not None:
        compact.append(previous if count == 1 else f"{previous}×{count}")
    return " → ".join(compact)


def _defect_location(defect: Defect) -> str:
    if defect.occurred_at_s is None:
        return "全窗口"
    return f"t={defect.occurred_at_s:.0f}s"


def _regression_rows_for(
    regression: RegressionReport | None, case_id: str
) -> list[str]:
    if regression is None:
        return []
    texts: list[str] = []
    for row in regression.severe_regressions:
        if row.case_id == case_id:
            texts.append(f"严重回归：{row.metric}（{row.detail}）")
    for row in regression.unexpected_changes:
        if row.case_id == case_id:
            texts.append(f"非预期变化：{row.metric}（{row.detail}）")
    return texts


class _ReportBuilder:
    def __init__(
        self,
        run: RunRecord,
        baseline: BaselineRecord | None,
        regression: RegressionReport | None,
    ) -> None:
        self.run = run
        self.baseline = baseline
        self.regression = regression
        self.metrics = run.metrics
        self.results = list(run.case_results)
        self.p0 = [
            defect
            for result in self.results
            for defect in result.defects
            if defect.level == DefectLevel.P0
        ]
        self.p1 = [
            defect
            for result in self.results
            for defect in result.defects
            if defect.level == DefectLevel.P1
        ]

    def build(self) -> str:
        lines: list[str] = [
            "# 工业 Agent 安全测试报告",
            "",
            f"- 运行：`{self.run.id}`｜{self.run.name}",
            f"- Agent：{self.run.agent_name}（`{self.run.agent_id}`，"
            f"版本 `{self.run.agent_version}`）",
            f"- 套件：`{self.run.suite_id}`｜种子集合：{self.run.seed_set or '未记录'}",
            f"- 运行时间：{self.run.started_at.isoformat() if self.run.started_at else '—'}",
            "- 数据域：`demo_reactor` 合成演示域；不是真实装置工程数据，不能替代现场验收。",
            "",
        ]
        lines.extend(self.section_summary())
        lines.extend(self.section_dataset())
        lines.extend(self.section_metrics())
        lines.extend(self.section_p0())
        lines.extend(self.section_p1())
        lines.extend(self.section_interlocks())
        lines.extend(self.section_reproducibility())
        lines.extend(self.section_regression())
        lines.extend(self.section_risks())
        lines.extend(self.section_appendix())
        return "\n".join(lines).rstrip() + "\n"

    # 1 -----------------------------------------------------------------
    def section_summary(self) -> list[str]:
        lines = ["## 1. 执行摘要", ""]
        metrics = self.metrics
        if metrics is None:
            safety = "未验证 —— 本轮没有指标快照，不能据此判断安全性。"
        elif metrics.defects_p0 > 0:
            codes = "、".join(sorted({item.code.value for item in self.p0}))
            safety = f"不可上线 —— 存在 {metrics.defects_p0} 项 P0 缺陷（{codes}）。"
        elif metrics.dataset.imbalanced:
            safety = (
                "当前用例集下未发现 P0；但注入故障用例仅占 "
                f"{metrics.dataset.fault_ratio + metrics.dataset.interlock_ratio:.1%}"
                "（低于 30%），结论置信度不足，不可据此上线。"
            )
        else:
            safety = (
                "当前用例集下未发现阻断性 P0；是否可上线仍取决于第 9 节遗留风险与未验证项。"
            )
        if metrics is None:
            unauthorized = "未验证 —— 缺少指标快照。"
        elif metrics.unauthorized_attempts > 0:
            unauthorized = (
                f"发现 {metrics.unauthorized_attempts} 次越权/越界尝试，"
                "SafetyGate 判定与证据见第 4 节。"
            )
        else:
            unauthorized = "未发现越权下发尝试。"
        if metrics is None:
            loop = "未验证 —— 缺少指标快照。"
        elif metrics.interlock_expected:
            trace_mismatch = sum(
                1 for item in self.results if item.action_trace_match is False
            )
            loop = (
                f"预期联锁 {metrics.interlock_expected} 条，正确触发 "
                f"{metrics.interlock_correct} 条，漏触发 {metrics.interlock_missed} 条；"
                f"动作序列不一致 {trace_mismatch} 例。"
            )
        else:
            loop = "本轮未包含预期联锁动作。"
        if metrics is None or not metrics.reproducibility_verified:
            repro = "未验证 —— 本轮未完成同 seed 复跑指纹比对。"
        else:
            repro = f"同 seed 复跑 {_pct(metrics.reproducibility_rate)} 一致。"
        lines.extend(
            [
                f"- **安全结论**：{safety}",
                f"- **越权情况**：{unauthorized}",
                f"- **闭环链路**：{loop}",
                f"- **复现性**：{repro}",
                "",
            ]
        )
        return lines

    # 2 -----------------------------------------------------------------
    def section_dataset(self) -> list[str]:
        lines = ["## 2. 数据集构成披露", ""]
        metrics = self.metrics
        if metrics is None:
            lines.extend(["本轮没有指标快照，无法披露数据集构成。", ""])
            return lines
        dataset = metrics.dataset
        lines.extend(
            [
                "| 类别 | 用例数 | 占比 |",
                "|---|---:|---:|",
                f"| 稳态 | {dataset.steady_cases} | {dataset.steady_ratio:.1%} |",
                f"| 边界 | {dataset.boundary_cases} | {dataset.boundary_ratio:.1%} |",
                f"| 注入故障 | {dataset.fault_cases} | {dataset.fault_ratio:.1%} |",
                f"| 联锁闭环 | {dataset.interlock_cases} | {dataset.interlock_ratio:.1%} |",
                f"| **合计** | **{dataset.total_cases}** | **100.0%** |",
                "",
            ]
        )
        if dataset.warning:
            lines.extend([f"> **数据集警示**：{dataset.warning}", ""])
        rows = [
            "| 用例 | 类别 | 来源 | 注入 | 标签 |",
            "|---|---|---|---|---|",
        ]
        for result in self.results:
            definition = _case_definition(result)
            category = _CATEGORY_LABELS.get(result.category, result.category.value)
            source = definition.get("source", "未记录")
            provenance = str(definition.get("provenance", "未记录")).replace("|", "\\|")
            tags = ", ".join(str(item) for item in definition.get("tags", [])) or "—"
            rows.append(
                f"| `{result.case_id}` | {category} | {source} | "
                f"{_case_fault_text(definition)} | {tags} |"
            )
        lines.extend(rows)
        lines.extend(
            [
                "",
                "> 数据来源追踪：每个用例的 `source` 与 `provenance` 同时写入 "
                "`case.yaml`；本轮来源均为合成仿真或演示机理数据，"
                "不得标注为真实历史数据。",
                "",
                "| 用例 | 数据来源说明 |",
                "|---|---|",
            ]
        )
        for result in self.results:
            definition = _case_definition(result)
            provenance = str(definition.get("provenance", "未记录")).replace("|", "\\|")
            lines.append(f"| `{result.case_id}` | {provenance} |")
        lines.append("")
        return lines

    # 3 -----------------------------------------------------------------
    def section_metrics(self) -> list[str]:
        lines = ["## 3. 核心指标看板", ""]
        metrics = self.metrics
        if metrics is None:
            lines.extend(["本轮缺少指标快照。", ""])
            return lines
        lines.extend(
            [
                "### P0 区（阻断性）",
                "",
                "| 指标 | 数值 | 说明 |",
                "|---|---:|---|",
                f"| **漏报率** | **{_pct(metrics.miss_rate)}** | "
                f"{metrics.missed_faults}/{metrics.injected_faults} 条注入故障未检出（首指标） |",
                f"| 越权尝试 | {metrics.unauthorized_attempts} | "
                "含越界参数、旁路请求与拒绝后重试 |",
                f"| 联锁漏触发 | {metrics.interlock_missed} | "
                f"预期 {metrics.interlock_expected} 条，正确 {metrics.interlock_correct} 条 |",
                f"| 参数越界 | {metrics.unsafe_setpoint_events} | 触发安全限或仪表量程的设定值 |",
                f"| P0 缺陷 | {metrics.defects_p0} | 逐条见第 4 节 |",
                "",
                "### 其它指标（不得前置替代漏报率）",
                "",
                "| 指标 | 数值 |",
                "|---|---:|",
                f"| 误报率 | {_pct(metrics.false_alarm_rate)}（{metrics.false_alarm_count}/"
                f"{metrics.judgment_opportunities}） |",
                f"| 高危时段误报 | {metrics.high_risk_false_alarms} |",
                f"| 参数合规率 | {_pct(metrics.setpoint_compliance_rate)} |",
                f"| 诊断时延 P50 / P90 / P99 | {_num(metrics.detection_latency.p50_s)}s / "
                f"{_num(metrics.detection_latency.p90_s)}s / "
                f"{_num(metrics.detection_latency.p99_s)}s |",
                f"| 最大诊断时延 | {_num(metrics.detection_latency.max_s)}s |",
                f"| 复现一致性 | {_pct(metrics.reproducibility_rate)} |",
                f"| P1 / P2 缺陷 | {metrics.defects_p1} / {metrics.defects_p2} |",
                "",
                "数据集构成："
                f"故障 {metrics.dataset.fault_ratio:.1%} / "
                f"稳态 {metrics.dataset.steady_ratio:.1%} / "
                f"边界 {metrics.dataset.boundary_ratio:.1%} / "
                f"闭环 {metrics.dataset.interlock_ratio:.1%}"
                + ("  ⚠ 失衡" if metrics.dataset.imbalanced else ""),
                "",
                "> 不以“通过率”作为主指标：通过率会掩盖数据集失衡与漏报风险。",
                "",
            ]
        )
        return lines

    # 4 -----------------------------------------------------------------
    def section_p0(self) -> list[str]:
        lines = ["## 4. P0 缺陷明细", ""]
        if not self.p0:
            lines.extend(
                [
                    "本轮未发现 P0 缺陷。",
                    "",
                    "> 这不等于可上线：仍需结合第 2 节数据集构成、第 7 节复现性"
                    "与第 9 节遗留风险判定。",
                    "",
                ]
            )
            return lines
        by_id = {result.case_id: result for result in self.results}
        for index, defect in enumerate(self.p0, start=1):
            result = by_id.get(defect.case_id)
            lines.append(
                f"### [P0-{index:03d}] {defect.case_id} {defect.title}"
            )
            lines.append("")
            lines.append(f"- **等级**：P0 / `{defect.code.value}`")
            case_line = f"- **用例**：`{defect.case_id}`｜位置：{_defect_location(defect)}"
            if result is not None:
                case_line += f"｜seed={result.seed}"
            lines.append(case_line)
            lines.append(f"- **期望**：{defect.expected}")
            lines.append(f"- **实际**：{defect.actual}")
            if defect.detail:
                lines.append(f"- **判定依据**：{defect.detail}")
            lines.append("- **证据链**：")
            if result is None:
                lines.append("  - 用例结果缺失，无法定位证据。")
            else:
                series = _evidence_path(result, "series.csv")
                response = _nearest_response(result, defect.occurred_at_s)
                verdict = _evidence_path(result, "verdict.json")
                gate = _evidence_path(result, "gate_decisions.json")
                lines.append(f"  - 原始时序：`{series}`")
                lines.append(
                    f"  - 模型原始响应：`{response}`"
                    if response
                    else "  - 模型原始响应：缺失（证据不完整）"
                )
                lines.append(f"  - 判定过程：`{verdict}`")
                lines.append(f"  - 门禁决策：`{gate}`")
                for path in defect.evidence_paths:
                    lines.append(f"  - 附加证据：`{path}`")
            lines.append(
                f"- **机理依据**：{defect.mechanism_basis or '未填写；按 TODO(mechanism) 披露'}"
            )
            lines.append(
                f"- **复现命令**：`{defect.repro_command or '未提供'}`"
            )
            impacts = _regression_rows_for(self.regression, defect.case_id)
            lines.append(
                "- **关联回归影响**："
                + ("；".join(impacts) if impacts else "未提供基线对比或未见严重回归")
            )
            lines.append("")
        return lines

    # 5 -----------------------------------------------------------------
    def section_p1(self) -> list[str]:
        lines = ["## 5. P1 缺陷汇总", ""]
        if not self.p1:
            lines.extend(["本轮未发现 P1 缺陷。", ""])
            return lines
        lines.extend(
            [
                "| 用例 | 代码 | 标题 | 发生时刻 | 证据 |",
                "|---|---|---|---:|---|",
            ]
        )
        for defect in self.p1:
            evidence = (
                f"`{defect.evidence_paths[0]}`" if defect.evidence_paths else "见用例证据目录"
            )
            occurred = "—" if defect.occurred_at_s is None else f"{defect.occurred_at_s:.0f}s"
            lines.append(
                f"| `{defect.case_id}` | `{defect.code.value}` | {defect.title} | "
                f"{occurred} | {evidence} |"
            )
        lines.extend(["", "P1 不阻断发布，但须在遗留风险中登记并跟踪。", ""])
        return lines

    # 6 -----------------------------------------------------------------
    def section_interlocks(self) -> list[str]:
        lines = ["## 6. 联动闭环验证结果", ""]
        rows = [
            result
            for result in self.results
            if result.interlock_evaluations
            or result.expected_action_trace
            or result.actual_action_trace
            or result.category == CaseCategory.INTERLOCK
        ]
        if not rows:
            lines.extend(["本轮没有联锁或安全门禁动作轨迹。", ""])
            return lines
        lines.extend(
            [
                "### 6.1 动作序列对照",
                "",
                "| 用例 | 期望序列 | 实际序列 | 判定 |",
                "|---|---|---|---|",
            ]
        )
        for result in rows:
            expected = _trace_text(result.expected_action_trace)
            actual = _trace_text(result.actual_action_trace)
            if result.action_trace_match is None:
                verdict = "未声明"
            elif result.action_trace_match:
                verdict = "一致"
            else:
                verdict = "不一致"
            lines.append(
                f"| `{result.case_id}` | {expected} | {actual} | {verdict} |"
            )
        lines.extend(["", "### 6.2 联锁规则判定", ""])
        interlock_rows: list[tuple[str, InterlockEvaluation]] = [
            (result.case_id, evaluation)
            for result in self.results
            for evaluation in result.interlock_evaluations
        ]
        if not interlock_rows:
            lines.extend(["本轮未被测用例声明联锁规则。", ""])
            return lines
        lines.extend(
            [
                "| 用例 | 规则 | 应触发 | 实际触发 | 触发时刻 | 误动作 |",
                "|---|---|---|---|---:|---|",
            ]
        )
        for case_id, evaluation in interlock_rows:
            triggered = "是" if evaluation.triggered else "否"
            expected = "是" if evaluation.should_trigger else "否"
            false_trip = "是" if evaluation.false_trip else "否"
            trigger_t = (
                "—" if evaluation.trigger_t_s is None else f"{evaluation.trigger_t_s:.0f}s"
            )
            lines.append(
                f"| `{case_id}` | `{evaluation.rule_id}` | {expected} | {triggered} | "
                f"{trigger_t} | {false_trip} |"
            )
        lines.append("")
        return lines

    # 7 -----------------------------------------------------------------
    def section_reproducibility(self) -> list[str]:
        lines = ["## 7. 复现性审计", ""]
        metrics = self.metrics
        if metrics is None or not metrics.reproducibility_verified:
            lines.extend(
                [
                    "**复现性本轮未验证**：未完成同 seed 复跑指纹比对。",
                    "",
                    "未验证不是通过。任何安全结论都必须注明该限制。",
                    "",
                ]
            )
            return lines
        lines.extend(
            [
                f"- 同 seed 复跑一致率：**{_pct(metrics.reproducibility_rate)}**",
                "- 固定规则：相同用例、Agent、协议与 seed；"
                "比较结构化结论指纹，不比较自然语言措辞。",
                "",
            ]
        )
        failed = [result for result in self.results if result.reproducible is False]
        if failed:
            lines.extend(["| 不可复现用例 | 指纹 | 缺陷 |", "|---|---|---|"])
            for result in failed:
                lines.append(
                    f"| `{result.case_id}` | `{result.fingerprint[:24]}…` | 已记 "
                    f"{'P0' if result.has_p0 else 'P1'} 缺陷 |"
                )
            lines.append("")
        else:
            lines.extend(["所有完成复跑比对的用例指纹一致。", ""])
        lines.extend(
            [
                "| 用例 | seed | 指纹（前 24 位） | 复跑一致 |",
                "|---|---:|---|---|",
            ]
        )
        for result in self.results:
            matched = (
                "未验证"
                if result.reproducible is None
                else ("是" if result.reproducible else "否")
            )
            lines.append(
                f"| `{result.case_id}` | {result.seed} | `{result.fingerprint[:24]}…` | {matched} |"
            )
        lines.append("")
        return lines

    # 8 -----------------------------------------------------------------
    def section_regression(self) -> list[str]:
        lines = ["## 8. 版本回归对比", ""]
        if self.regression is None:
            if self.baseline is not None:
                lines.extend(
                    [
                        f"本轮已加载基线 `{self.baseline.id}`，但未执行候选版本对比。",
                        "",
                    ]
                )
            else:
                lines.extend(["本轮未提供基线，版本回归未验证。", ""])
            return lines
        report = self.regression
        lines.extend(
            [
                f"- 基线：`{report.baseline_id}`（运行 `{report.baseline_run_id}`）",
                f"- 候选运行：`{report.candidate_run_id}`",
                f"- 可比性：{'可比' if report.comparable else '不可比'}",
            ]
        )
        if report.fingerprint_match_rate is not None:
            lines.append(f"- 指纹一致率：{_pct(report.fingerprint_match_rate)}")
        if report.latency_ratio is not None:
            lines.append(f"- 时延比值：{report.latency_ratio:.2f}×")
        lines.append("")
        if not report.comparable:
            lines.extend(["### 阻断项", ""])
            for blocker in report.blockers:
                lines.append(f"- {blocker}")
            lines.extend(
                [
                    "",
                    "> 三个哈希任一变化即拒绝比较；不得把不可比报告解释为“没有回归”。",
                    "",
                ]
            )
            return lines
        lines.extend(["### 8.1 严重回归（置顶）", ""])
        if report.severe_regressions:
            lines.extend(
                [
                    "| 用例 | 指标 | 基线 | 候选 | 说明 |",
                    "|---|---|---|---|---|",
                ]
            )
            for row in report.severe_regressions:
                lines.append(
                    f"| `{row.case_id}` | {row.metric} | {row.baseline} | "
                    f"{row.current} | {row.detail} |"
                )
        else:
            lines.append("未发现严重回归。")
        lines.extend(["", "### 8.2 非预期变化", ""])
        if report.unexpected_changes:
            lines.extend(
                [
                    "| 用例 | 指标 | 基线 | 候选 | 说明 |",
                    "|---|---|---|---|---|",
                ]
            )
            for row in report.unexpected_changes:
                lines.append(
                    f"| `{row.case_id}` | {row.metric} | {row.baseline} | "
                    f"{row.current} | {row.detail} |"
                )
        else:
            lines.append("无非预期变化。")
        lines.extend(["", "### 8.3 改进项", ""])
        if report.improvements:
            for row in report.improvements:
                lines.append(
                    f"- `{row.case_id}`｜{row.metric}：{row.baseline} → "
                    f"{row.current}（{row.detail}）"
                )
        else:
            lines.append("无改进项。")
        lines.append("")
        return lines

    # 9 -----------------------------------------------------------------
    def section_risks(self) -> list[str]:
        lines = ["## 9. 遗留风险与建议", ""]
        risks: list[str] = []
        if self.metrics is not None and self.metrics.dataset.imbalanced:
            risks.append(
                f"数据集失衡：注入故障/联锁占比 "
                f"{self.metrics.dataset.fault_ratio + self.metrics.dataset.interlock_ratio:.1%}，"
                "即使漏报率为 0 也不能得出准入结论；必须补充故障与联锁场景。"
            )
        if self.metrics is None or not self.metrics.reproducibility_verified:
            risks.append("复现性未验证：结论不能用于版本准入；需在具备条件时复跑并比对指纹。")
        if self.metrics is not None and (self.metrics.reproducibility_rate or 0.0) < 1.0:
            risks.append("存在不可复现用例：须定位非确定性来源并重测。")
        risks.extend(
            [
                "数据域为合成演示：`domain/demo_reactor` 的阈值、时间常数与故障幅值均为演示假设，"
                "不是真实装置工程数据；不得据此签发安全认证。",
                "联锁验证在平台内独立引擎完成，未接入真实 SIS；现场逻辑、旁路管理、"
                "SOE 时序与 SIS 响应时间仍需在 FAT/SAT 阶段验证。",
                "未覆盖长周期漂移、多故障叠加、真实网络时延分布、DCS 扫描周期差异与操作员失误链。",
                "机理依据缺失项以 `TODO(mechanism)` 标注，"
                "详见 `domain/demo_reactor/ASSUMPTIONS.md`。",
                "外部 HTTP Agent、鉴权轮换与跨网络部署未在本轮验证。",
            ]
        )
        lines.extend([f"- {item}" for item in risks])
        lines.append("")
        if self.p0:
            lines.append(
                "**建议**：先修复全部 P0 并重建基线，再按同一用例集复测；"
                "P0 清零前不得发布。"
            )
        elif self.metrics is not None and self.metrics.dataset.imbalanced:
            lines.append("**建议**：先补充故障/联锁用例并复测，再讨论准入。")
        else:
            lines.append("**建议**：完成第 9 节未验证项后，再由安全负责人做准入判定。")
        lines.append("")
        return lines

    # 10 ----------------------------------------------------------------
    def section_appendix(self) -> list[str]:
        lines = ["## 10. 附录：原始数据索引", ""]
        lines.extend(
            [
                "| 用例 | 证据目录 | 指纹 | 关键文件 |",
                "|---|---|---|---|",
            ]
        )
        for result in self.results:
            directory = _case_dir(result)
            key_files = []
            for name in (
                "case.yaml",
                "series.csv",
                "verdict.json",
                "gate_decisions.json",
                "injection.json",
                "manifest.json",
            ):
                if (directory / name).exists():
                    key_files.append(f"`{name}`")
            lines.append(
                f"| `{result.case_id}` | `{directory}` | `{result.fingerprint[:16]}…` | "
                f"{', '.join(key_files) or '缺失'} |"
            )
        lines.extend(
            [
                "",
                "### 运行元数据",
                "",
                f"- 运行 ID：`{self.run.id}`",
                f"- 用例集哈希：`{self.run.domain_hashes.case_set_hash}`",
                f"- 领域包哈希：`{self.run.domain_hashes.domain_hash}`",
                f"- 联锁表哈希：`{self.run.domain_hashes.interlock_hash}`",
                f"- 报告生成时间：{utc_now().isoformat()}",
                "",
                "> 每个用例目录均应包含 `case.yaml`、`series.csv`、`responses/`、"
                "`actions.jsonl`、`gate_decisions.json`、`injection.json`、`verdict.json`、"
                "`fingerprint.txt` 与 `manifest.json`。缺一即视为证据链不完整。",
                "",
            ]
        )
        return lines


def render_report(
    run: RunRecord,
    *,
    baseline: BaselineRecord | None = None,
    regression: RegressionReport | None = None,
) -> str:
    return _ReportBuilder(run, baseline, regression).build()


def write_report(
    run: RunRecord,
    *,
    baseline: BaselineRecord | None = None,
    regression: RegressionReport | None = None,
    path: Path | None = None,
) -> Path:
    target = path or (
        Path(run.case_results[0].artifact_dir).parent / "report.md"
        if run.case_results
        else Path("report.md")
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        render_report(run, baseline=baseline, regression=regression),
        encoding="utf-8",
    )
    return target
