"""套件运行服务：执行、评测、证据落盘、复现性校验与持久化。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from ia_platform.config import Settings
from ia_platform.core.catalog import PlatformCatalog
from ia_platform.core.models import (
    AgentDefinition,
    CaseResult,
    CaseSuite,
    Defect,
    DefectCode,
    DefectLevel,
    DomainHashes,
    DomainPack,
    RunRecord,
    RunStatus,
    TestCase,
    utc_now,
)
from ia_platform.evaluation.checks import evaluate_case
from ia_platform.orchestration.artifacts import write_case_artifacts
from ia_platform.orchestration.runner import execute_case
from ia_platform.services.repository import Repository


class RunServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class CaseExecutionOutcome:
    case: TestCase
    result: CaseResult
    matched_fingerprint: bool | None


def _run_id(suite_id: str, agent_id: str) -> str:
    return f"run-{utc_now().strftime('%Y%m%dT%H%M%S')}-{suite_id}-{agent_id}-{uuid4().hex[:6]}"


def _safety_related(case: TestCase, result: CaseResult) -> bool:
    return (
        "safety-critical" in case.tags
        or case.category.value in {"interlock", "security"}
        or any(item.level == DefectLevel.P0 for item in result.defects)
    )


class RunService:
    def __init__(
        self,
        settings: Settings,
        catalog: PlatformCatalog,
        domain: DomainPack,
        repository: Repository,
        *,
        reproducibility_check: bool = True,
    ) -> None:
        self.settings = settings
        self.catalog = catalog
        self.domain = domain
        self.repository = repository
        self.reproducibility_check = reproducibility_check

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------

    def run_suite(
        self,
        suite_id: str,
        agent_ids: list[str] | None = None,
        *,
        name: str | None = None,
        seed_override: int | None = None,
        reproducibility_check: bool | None = None,
    ) -> list[RunRecord]:
        suite = self.catalog.get_suite(suite_id)
        selected_agents = agent_ids or list(suite.agent_ids)
        if not selected_agents:
            raise RunServiceError(f"套件 {suite.id} 未指定 Agent")
        runs: list[RunRecord] = []
        for agent_id in selected_agents:
            agent = self.catalog.get_agent(agent_id)
            runs.append(
                self._run_cases(
                    suite=suite,
                    cases=[self.catalog.get_case(case_id) for case_id in suite.case_ids],
                    agent=agent,
                    name=name,
                    seed_override=seed_override,
                    reproducibility_check=reproducibility_check,
                )
            )
        return runs

    def run_case(
        self,
        case_id: str,
        agent_id: str,
        *,
        seed_override: int | None = None,
        name: str | None = None,
        reproducibility_check: bool | None = None,
    ) -> RunRecord:
        case = self.catalog.get_case(case_id)
        agent = self.catalog.get_agent(agent_id)
        suite = CaseSuite(
            id="single-case",
            name=f"单用例：{case.name}",
            description="CLI/API 单用例复现入口",
            case_ids=[case.id],
            agent_ids=[agent.id],
        )
        return self._run_cases(
            suite=suite,
            cases=[case],
            agent=agent,
            name=name,
            seed_override=seed_override,
            reproducibility_check=reproducibility_check,
        )

    # ------------------------------------------------------------------
    # 内部执行
    # ------------------------------------------------------------------

    def _run_cases(
        self,
        *,
        suite: CaseSuite,
        cases: list[TestCase],
        agent: AgentDefinition,
        name: str | None,
        seed_override: int | None,
        reproducibility_check: bool | None,
    ) -> RunRecord:
        check_repro = (
            self.reproducibility_check
            if reproducibility_check is None
            else reproducibility_check
        )
        run_id = _run_id(suite.id, agent.id)
        started = utc_now()
        run = RunRecord(
            id=run_id,
            name=name or f"{suite.name} / {agent.name}",
            suite_id=suite.id,
            agent_id=agent.id,
            agent_name=agent.name,
            agent_version=agent.version,
            seed=seed_override if seed_override is not None else 0,
            status=RunStatus.RUNNING,
            created_at=started,
            started_at=started,
            case_ids=[case.id for case in cases],
            domain_hashes=DomainHashes(
                domain_hash=self.domain.hashes.domain_hash,
                interlock_hash=self.domain.hashes.interlock_hash,
                case_set_hash=self.catalog.case_set_hash,
            ),
            seed_set=sorted(
                {
                    seed_override if seed_override is not None else case.seed
                    for case in cases
                }
            ),
        )
        self.repository.save_run(run)
        results: list[CaseResult] = []
        reproducibility: list[bool] = []
        try:
            for case in cases:
                outcome = self._execute_one(
                    run_id=run_id,
                    case=case,
                    agent=agent,
                    seed_override=seed_override,
                    check_repro=check_repro,
                )
                results.append(outcome.result)
                if outcome.matched_fingerprint is not None:
                    reproducibility.append(outcome.matched_fingerprint)
                run = run.model_copy(
                    update={
                        "case_results": list(results),
                        "seed_set": sorted(
                            {
                                seed_override
                                if seed_override is not None
                                else case.seed
                                for case in cases
                            }
                        ),
                    }
                )
                self.repository.save_run(run)
        except Exception as exc:
            failed = run.model_copy(
                update={
                    "status": RunStatus.FAILED,
                    "finished_at": utc_now(),
                    "case_results": list(results),
                    "error": f"{type(exc).__name__}: {exc}",
                    "reproducibility_unverified": check_repro,
                }
            )
            self.repository.save_run(failed)
            return failed

        verified = check_repro and len(reproducibility) == len(cases)
        rate = (
            sum(1 for item in reproducibility if item) / len(reproducibility)
            if reproducibility
            else None
        )
        completed = run.model_copy(
            update={
                "status": RunStatus.COMPLETED,
                "finished_at": utc_now(),
                "case_results": list(results),
                "reproducibility_unverified": not verified,
            }
        )
        # 指标必须在本模块晚绑定导入，避免评测层反向依赖服务层。
        from ia_platform.evaluation.metrics import compute_metrics

        metrics = compute_metrics(
            results,
            reproducibility_rate=rate,
            reproducibility_verified=verified,
        )
        completed = completed.model_copy(update={"metrics": metrics})
        self.repository.save_run(completed)
        return completed

    def _execute_one(
        self,
        *,
        run_id: str,
        case: TestCase,
        agent: AgentDefinition,
        seed_override: int | None,
        check_repro: bool,
    ) -> CaseExecutionOutcome:
        seed = seed_override if seed_override is not None else case.seed
        artifact_dir = self.settings.artifact_dir / "runs" / run_id / case.id
        evidence = execute_case(case, agent, self.domain, seed)
        result = evaluate_case(evidence, str(artifact_dir))
        matched: bool | None = None
        if check_repro:
            replay = execute_case(case, agent, self.domain, seed)
            replay_result = evaluate_case(replay, str(artifact_dir))
            matched = replay_result.fingerprint == result.fingerprint
            if not matched:
                level = (
                    DefectLevel.P0
                    if _safety_related(case, result)
                    else DefectLevel.P1
                )
                defect = Defect(
                    id=f"{case.id}-{DefectCode.NON_REPRODUCIBLE.value}-999",
                    case_id=case.id,
                    level=level,
                    code=DefectCode.NON_REPRODUCIBLE,
                    title="同 seed 复跑结论不一致",
                    expected="相同用例、Agent、协议与 seed 应得到相同结论指纹",
                    actual=(
                        f"首次 {result.fingerprint[:16]}…，"
                        f"复跑 {replay_result.fingerprint[:16]}…"
                    ),
                    evidence_paths=["series.csv", "verdict.json", "responses/"],
                    mechanism_basis="AGENTS.md R3：确定性可复现",
                    repro_command=(
                        f"iatp run-case {case.id} --agent {agent.id} --seed {seed}"
                    ),
                    detail="复现性校验失败；结论不可用于准入判定。",
                )
                result = result.model_copy(
                    update={
                        "defects": [*result.defects, defect],
                        "reproducible": False,
                    }
                )
            else:
                result = result.model_copy(update={"reproducible": True})
        write_case_artifacts(evidence, result, artifact_dir)
        return CaseExecutionOutcome(
            case=case, result=result, matched_fingerprint=matched
        )
