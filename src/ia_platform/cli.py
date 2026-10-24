"""`iatp` 命令行入口。

命令与 API 共用 RunService / BaselineService / ReportService，不存在第二套评测逻辑。
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from ia_platform.core.models import DefectLevel, RegressionReport, RunRecord, RunStatus
from ia_platform.services.context import PlatformContext


def _print_run(run: RunRecord, *, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(run.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return
    metrics = run.metrics
    print(f"运行：{run.id}")
    print(f"名称：{run.name}")
    print(
        f"状态：{run.status.value}｜Agent：{run.agent_id} {run.agent_version}｜"
        f"套件：{run.suite_id}｜用例：{len(run.case_results)}"
    )
    if run.error:
        print(f"错误：{run.error}")
    if metrics is not None:
        print(
            f"漏报率：{metrics.miss_rate:.1%}（{metrics.missed_faults}/"
            f"{metrics.injected_faults}）｜P0：{metrics.defects_p0}｜"
            f"P1：{metrics.defects_p1}｜越权：{metrics.unauthorized_attempts}"
        )
        print(
            "复现性："
            + (
                f"{metrics.reproducibility_rate:.1%}"
                if metrics.reproducibility_verified
                and metrics.reproducibility_rate is not None
                else "未验证"
            )
        )
    if run.report_markdown_path:
        print(f"报告：{run.report_markdown_path}")
    if run.status == RunStatus.FAILED:
        print("运行失败；不得把失败视为无缺陷。")


def _run_records(records: list[RunRecord], as_json: bool) -> int:
    if as_json:
        print(
            json.dumps(
                [record.model_dump(mode="json") for record in records],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    for index, run in enumerate(records):
        if index:
            print("")
        _print_run(run)
    return 0 if all(run.status == RunStatus.COMPLETED for run in records) else 1


def _regression_text(report: RegressionReport) -> str:
    if not report.comparable:
        return "不可比：\n" + "\n".join(f"- {item}" for item in report.blockers)
    lines = [
        f"基线：{report.baseline_id}｜候选：{report.candidate_run_id}",
        f"严重回归：{len(report.severe_regressions)}｜"
        f"非预期变化：{len(report.unexpected_changes)}｜"
        f"改进：{len(report.improvements)}",
    ]
    for row in report.severe_regressions:
        lines.append(
            f"  P0 {row.case_id}｜{row.metric}：{row.baseline} → {row.current}｜{row.detail}"
        )
    for row in report.unexpected_changes:
        lines.append(
            f"  P1 {row.case_id}｜{row.metric}：{row.baseline} → {row.current}｜{row.detail}"
        )
    return "\n".join(lines)


def _build_context() -> PlatformContext:
    return PlatformContext.build()


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "ia_platform.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )
    return 0


def _cmd_run_suite(args: argparse.Namespace) -> int:
    ctx = _build_context()
    runs = ctx.run_service.run_suite(
        args.suite_id,
        args.agents or None,
        name=args.name,
        seed_override=args.seed,
        reproducibility_check=not args.no_repro,
    )
    if args.report:
        for run in runs:
            if run.status == RunStatus.COMPLETED:
                _, path = ctx.report_service.generate(run.id)
                run = ctx.repository.get_run(run.id) or run
                print(f"报告已生成：{path}")
    return _run_records(runs, args.json)


def _cmd_run_case(args: argparse.Namespace) -> int:
    ctx = _build_context()
    run = ctx.run_service.run_case(
        args.case_id,
        args.agent,
        seed_override=args.seed,
        reproducibility_check=not args.no_repro,
    )
    if args.report and run.status == RunStatus.COMPLETED:
        _, path = ctx.report_service.generate(run.id)
        print(f"报告已生成：{path}")
        run = ctx.repository.get_run(run.id) or run
    return _run_records([run], args.json)


def _cmd_seed(args: argparse.Namespace) -> int:
    ctx = _build_context()
    result = ctx.seed_service.seed(force=args.force)
    if result.skipped:
        print("已有运行记录；如需重建演示数据请使用 --force。")
        return 0
    print(f"已生成 {len(result.runs)} 个运行。")
    if result.baseline_id:
        print(f"基线：{result.baseline_id}")
    if result.regression_id:
        print(f"回归：{result.regression_id}")
    for run in result.runs:
        print(f"- {run.id}｜{run.suite_id}｜{run.agent_id}｜{run.status.value}")
    return 0


def _cmd_baseline(args: argparse.Namespace) -> int:
    ctx = _build_context()
    if args.baseline_command == "create":
        baseline = ctx.baseline_service.create_baseline(args.run_id, args.name)
        print(f"基线已创建：{baseline.id}")
        print(
            f"运行：{baseline.run_id}｜用例：{len(baseline.results)}｜"
            f"Agent 版本：{baseline.agent_version}"
        )
        return 0
    baselines = ctx.repository.list_baselines(limit=100)
    if not baselines:
        print("尚无基线。")
        return 0
    for baseline in baselines:
        p0 = sum(
            1
            for result in baseline.results
            for defect in result.defects
            if defect.level == DefectLevel.P0
        )
        print(
            f"{baseline.id}｜{baseline.name}｜run={baseline.run_id}｜"
            f"用例 {len(baseline.results)}｜P0 {p0}｜{baseline.created_at.isoformat()}"
        )
    return 0


def _cmd_regression(args: argparse.Namespace) -> int:
    ctx = _build_context()
    if args.regression_command == "compare":
        report = ctx.baseline_service.compare(
            args.candidate, baseline_id=args.baseline
        )
        print(_regression_text(report))
        return 0 if report.comparable and not report.severe_regressions else 1
    reports = ctx.repository.list_regressions(limit=100)
    if not reports:
        print("尚无回归报告。")
        return 0
    for report in reports:
        print(
            f"{report.id}｜baseline={report.baseline_id}｜candidate={report.candidate_run_id}｜"
            f"可比={report.comparable}｜严重={len(report.severe_regressions)}｜"
            f"非预期={len(report.unexpected_changes)}"
        )
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    ctx = _build_context()
    run, path = ctx.report_service.generate(
        args.run_id,
        baseline_id=args.baseline,
        regression_id=args.regression,
    )
    print(f"报告已生成：{path}")
    print(f"运行：{run.id}")
    return 0


def _cmd_runs(args: argparse.Namespace) -> int:
    ctx = _build_context()
    if args.runs_command == "list":
        runs = ctx.repository.list_runs(limit=args.limit)
        for item in runs:
            metrics = item.metrics
            miss = (
                f"{metrics.miss_rate:.1%}"
                if metrics is not None
                else "未验证"
            )
            p0 = metrics.defects_p0 if metrics is not None else "—"
            print(
                f"{item.id}｜{item.status.value}｜{item.suite_id}｜{item.agent_id}｜"
                f"漏报 {miss}｜P0 {p0}｜{item.created_at.isoformat()}"
            )
        return 0
    run = ctx.repository.get_run(args.run_id)
    if run is None:
        print(f"运行不存在：{args.run_id}", file=sys.stderr)
        return 2
    _print_run(run, as_json=args.json)
    return 0 if run.status == RunStatus.COMPLETED else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="iatp",
        description="IATP 工业 AI Agent 测试平台命令行",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="启动 API 与前端")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.add_argument("--log-level", default="info")
    serve.set_defaults(func=_cmd_serve)

    run_suite = sub.add_parser("run-suite", help="执行套件")
    run_suite.add_argument("suite_id")
    run_suite.add_argument(
        "--agent", dest="agents", action="append", default=[], help="覆盖套件 Agent，可重复"
    )
    run_suite.add_argument("--seed", type=int, default=None)
    run_suite.add_argument("--name", default=None)
    run_suite.add_argument("--no-repro", action="store_true", help="关闭同 seed 复跑核对")
    run_suite.add_argument("--report", action="store_true", help="运行后生成报告")
    run_suite.add_argument("--json", action="store_true")
    run_suite.set_defaults(func=_cmd_run_suite)

    run_case = sub.add_parser("run-case", help="执行单用例（复现命令）")
    run_case.add_argument("case_id")
    run_case.add_argument("--agent", required=True)
    run_case.add_argument("--seed", type=int, default=None)
    run_case.add_argument("--no-repro", action="store_true")
    run_case.add_argument("--report", action="store_true")
    run_case.add_argument("--json", action="store_true")
    run_case.set_defaults(func=_cmd_run_case)

    seed = sub.add_parser("seed", help="生成演示运行、基线与回归")
    seed.add_argument("--force", action="store_true", help="清空数据库后重建（不删除证据文件）")
    seed.set_defaults(func=_cmd_seed)

    baseline = sub.add_parser("baseline", help="基线管理")
    baseline_sub = baseline.add_subparsers(dest="baseline_command", required=True)
    baseline_create = baseline_sub.add_parser("create")
    baseline_create.add_argument("run_id")
    baseline_create.add_argument("--name", default=None)
    baseline_list = baseline_sub.add_parser("list")
    baseline_list.set_defaults(func=_cmd_baseline)
    baseline_create.set_defaults(func=_cmd_baseline)

    regression = sub.add_parser("regression", help="版本回归")
    regression_sub = regression.add_subparsers(dest="regression_command", required=True)
    regression_compare = regression_sub.add_parser("compare")
    regression_compare.add_argument("--candidate", required=True)
    regression_compare.add_argument("--baseline", default=None)
    regression_compare.set_defaults(func=_cmd_regression)
    regression_list = regression_sub.add_parser("list")
    regression_list.set_defaults(func=_cmd_regression)

    report = sub.add_parser("report", help="生成固定十段式报告")
    report.add_argument("run_id")
    report.add_argument("--baseline", default=None)
    report.add_argument("--regression", default=None)
    report.set_defaults(func=_cmd_report)

    runs = sub.add_parser("runs", help="运行记录")
    runs_sub = runs.add_subparsers(dest="runs_command", required=True)
    runs_list = runs_sub.add_parser("list")
    runs_list.add_argument("--limit", type=int, default=20)
    runs_list.set_defaults(func=_cmd_runs)
    runs_show = runs_sub.add_parser("show")
    runs_show.add_argument("run_id")
    runs_show.add_argument("--json", action="store_true")
    runs_show.set_defaults(func=_cmd_runs)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result: Any = args.func(args)
        return int(result) if isinstance(result, int) else 0
    except Exception as exc:
        print(f"错误：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
