"""用例、Agent 与套件目录加载。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter, ValidationError

from ia_platform.config import Settings
from ia_platform.core.errors import CatalogError
from ia_platform.core.hashing import content_hash
from ia_platform.core.models import (
    AgentDefinition,
    CaseSuite,
    ControlKind,
    DomainPack,
    FaultPlan,
    TestCase,
)
from ia_platform.core.units import ensure_unit


@dataclass(frozen=True)
class PlatformCatalog:
    cases: dict[str, TestCase]
    agents: dict[str, AgentDefinition]
    suites: dict[str, CaseSuite]
    case_set_hash: str
    warnings: tuple[str, ...]

    def get_case(self, case_id: str) -> TestCase:
        try:
            return self.cases[case_id]
        except KeyError as exc:
            raise CatalogError(f"未知用例 {case_id}") from exc

    def get_agent(self, agent_id: str) -> AgentDefinition:
        try:
            return self.agents[agent_id]
        except KeyError as exc:
            raise CatalogError(f"未知 Agent {agent_id}") from exc

    def get_suite(self, suite_id: str) -> CaseSuite:
        try:
            return self.suites[suite_id]
        except KeyError as exc:
            raise CatalogError(f"未知套件 {suite_id}") from exc


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        raise CatalogError(f"文件不存在：{path}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CatalogError(f"{path} YAML 解析失败：{exc}") from exc


def load_catalog(settings: Settings, domain: DomainPack) -> PlatformCatalog:
    cases = _load_cases(settings.cases_dir, domain)
    agents = _load_agents(settings.agents_file, domain)
    suites = _load_suites(settings.suites_dir, cases, agents)
    warnings = tuple(domain.assumptions)

    payload = [case.model_dump(mode="json") for case in cases.values()]
    case_set_hash = content_hash(payload)
    return PlatformCatalog(
        cases=cases,
        agents=agents,
        suites=suites,
        case_set_hash=case_set_hash,
        warnings=warnings,
    )


def _load_cases(cases_dir: Path, domain: DomainPack) -> dict[str, TestCase]:
    if not cases_dir.exists():
        raise CatalogError(f"用例目录不存在：{cases_dir}")
    files = sorted(cases_dir.glob("*.yaml")) + sorted(cases_dir.glob("*.yml"))
    if not files:
        raise CatalogError(f"用例目录为空：{cases_dir}")

    result: dict[str, TestCase] = {}
    for path in files:
        raw = _load_yaml(path)
        raw_cases = raw.get("cases") if isinstance(raw, dict) else raw
        if not isinstance(raw_cases, list):
            raise CatalogError(f"{path} 必须包含 cases 列表")
        try:
            loaded = TypeAdapter(list[TestCase]).validate_python(raw_cases)
        except ValidationError as exc:
            raise CatalogError(f"{path} 用例校验失败：{exc}") from exc
        for case in loaded:
            if case.id in result:
                raise CatalogError(f"重复用例 ID：{case.id}")
            normalized = _normalize_case(case, domain)
            result[normalized.id] = normalized
    return result


def _normalize_case(case: TestCase, domain: DomainPack) -> TestCase:
    normalized_faults: list[FaultPlan] = []
    seen_faults: set[tuple[str, str]] = set()
    for fault in case.faults:
        key = (fault.kind.value, fault.target_tag)
        if key in seen_faults:
            raise CatalogError(f"{case.id} 重复注入相同故障 {key}")
        seen_faults.add(key)

        definition = domain.faults.get(fault.kind)
        if definition is None:
            raise CatalogError(f"{case.id} 使用未知故障 {fault.kind}")
        if fault.target_tag not in definition.targetable_tags:
            raise CatalogError(f"{case.id} 的故障 {fault.kind} 不能注入到 {fault.target_tag}")
        if fault.target_tag not in domain.sensors:
            raise CatalogError(f"{case.id} 指向未知测点 {fault.target_tag}")

        params = dict(fault.params)
        for param_key, default in definition.defaults.items():
            if param_key not in params:
                params[param_key] = default
        for param_key, param_value in params.items():
            if param_key not in definition.defaults:
                raise CatalogError(f"{case.id} 故障参数 {param_key} 不在故障库定义中")
            expected_unit = definition.defaults[param_key].unit
            ensure_unit(
                param_value.unit,
                expected_unit,
                f"{case.id}.{fault.kind}.{param_key}",
            )
        normalized_faults.append(fault.model_copy(update={"params": params}))

    for condition in case.initial_conditions:
        if condition.tag not in domain.sensors:
            raise CatalogError(f"{case.id} 初始条件指向未知测点 {condition.tag}")
        sensor = domain.sensor(condition.tag)
        ensure_unit(condition.unit, sensor.unit, f"{case.id} 初始条件 {condition.tag}")
        if not (
            sensor.instrument_range.low <= condition.value <= sensor.instrument_range.high
        ):
            raise CatalogError(f"{case.id} 初始条件 {condition.tag} 超出仪表量程")

    expected = case.expected
    if expected.fault_type is not None and expected.fault_type not in domain.faults:
        raise CatalogError(f"{case.id} 期望故障 {expected.fault_type} 不在故障库中")
    if expected.target_tag is not None and expected.target_tag not in domain.sensors:
        raise CatalogError(f"{case.id} 期望位号 {expected.target_tag} 未知")

    return case.model_copy(update={"faults": normalized_faults})


def _load_agents(path: Path, domain: DomainPack) -> dict[str, AgentDefinition]:
    raw = _load_yaml(path)
    raw_agents = raw.get("agents") if isinstance(raw, dict) else raw
    if not isinstance(raw_agents, list):
        raise CatalogError(f"{path} 必须包含 agents 列表")
    try:
        agents = TypeAdapter(list[AgentDefinition]).validate_python(raw_agents)
    except ValidationError as exc:
        raise CatalogError(f"{path} Agent 校验失败：{exc}") from exc
    result: dict[str, AgentDefinition] = {}
    for agent in agents:
        if agent.id in result:
            raise CatalogError(f"重复 Agent ID：{agent.id}")
        unknown_tags = set(agent.permissions.allowed_tags) - set(domain.sensors)
        if unknown_tags:
            raise CatalogError(f"{agent.id} 权限包含未知测点：{sorted(unknown_tags)}")
        unknown_high_risk = set(agent.permissions.high_risk_tags) - set(
            agent.permissions.allowed_tags
        )
        if unknown_high_risk:
            raise CatalogError(f"{agent.id} 的高危测点必须同时被允许：{sorted(unknown_high_risk)}")
        if ControlKind.SET_SETPOINT not in agent.permissions.allowed_control_kinds:
            raise CatalogError(f"{agent.id} 必须具备 set_setpoint 权限才能执行闭环用例")
        result[agent.id] = agent
    return result


def _load_suites(
    suites_dir: Path,
    cases: dict[str, TestCase],
    agents: dict[str, AgentDefinition],
) -> dict[str, CaseSuite]:
    if not suites_dir.exists():
        raise CatalogError(f"套件目录不存在：{suites_dir}")
    files = sorted(suites_dir.glob("*.yaml")) + sorted(suites_dir.glob("*.yml"))
    if not files:
        raise CatalogError(f"套件目录为空：{suites_dir}")
    result: dict[str, CaseSuite] = {}
    for path in files:
        raw = _load_yaml(path)
        raw_suites = raw.get("suites") if isinstance(raw, dict) else raw
        if not isinstance(raw_suites, list):
            raise CatalogError(f"{path} 必须包含 suites 列表")
        try:
            suites = TypeAdapter(list[CaseSuite]).validate_python(raw_suites)
        except ValidationError as exc:
            raise CatalogError(f"{path} 套件校验失败：{exc}") from exc
        for suite in suites:
            if suite.id in result:
                raise CatalogError(f"重复套件 ID：{suite.id}")
            missing_cases = set(suite.case_ids) - set(cases)
            if missing_cases:
                raise CatalogError(f"{suite.id} 引用未知用例：{sorted(missing_cases)}")
            missing_agents = set(suite.agent_ids) - set(agents)
            if missing_agents:
                raise CatalogError(f"{suite.id} 引用未知 Agent：{sorted(missing_agents)}")
            result[suite.id] = suite
    return result
