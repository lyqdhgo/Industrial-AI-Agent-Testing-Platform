"""domain/ 数据包加载、交叉校验与资产哈希。

任何缺失工艺依据的字段都以异常终止，禁止代码内默认值悄悄兜底。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from ia_platform.core.errors import DomainConfigurationError
from ia_platform.core.hashing import content_hash
from ia_platform.core.models import (
    DataSource,
    DomainHashes,
    DomainPack,
    FaultDefinition,
    FaultKind,
    InterlockRule,
    ProcessBounds,
    ProcessModelDefinition,
    SensorSpec,
    Timebase,
)
from ia_platform.core.units import ensure_unit

_REQUIRED_FILES = (
    "mechanisms.json",
    "process_bounds.json",
    "faults.json",
    "interlocks.json",
    "process_model.json",
)


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise DomainConfigurationError(
            f"缺少工艺依据文件 {path}。请先由工艺/安全工程师提供依据，禁止在代码内自拟阈值。"
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DomainConfigurationError(f"{path} 不是合法 JSON：{exc}") from exc


def _validate(adapter: TypeAdapter[Any], raw: Any, label: str) -> Any:
    try:
        return adapter.validate_python(raw)
    except ValidationError as exc:
        raise DomainConfigurationError(f"{label} 校验失败：{exc}") from exc


def load_domain(domain_dir: Path) -> DomainPack:
    """加载一个完整 domain pack，并生成用于基线的两个稳定哈希。"""
    missing = [name for name in _REQUIRED_FILES if not (domain_dir / name).exists()]
    if missing:
        raise DomainConfigurationError(
            f"domain pack {domain_dir} 缺少必需文件：{', '.join(missing)}；"
            "必须先提供机理定义、工艺边界、故障库与联锁表。"
        )

    mechanisms_raw = _read_json(domain_dir / "mechanisms.json")
    bounds_raw = _read_json(domain_dir / "process_bounds.json")
    faults_raw = _read_json(domain_dir / "faults.json")
    interlocks_raw = _read_json(domain_dir / "interlocks.json")
    model_raw = _read_json(domain_dir / "process_model.json")

    sensor_list = _validate(TypeAdapter(list[SensorSpec]), mechanisms_raw["sensors"], "sensors")
    sensors = {item.tag: item for item in sensor_list}
    if len(sensors) != len(sensor_list):
        raise DomainConfigurationError("mechanisms.json 存在重复测点 tag")

    bounds_list = _validate(
        TypeAdapter(list[ProcessBounds]), bounds_raw["bounds"], "process_bounds"
    )
    bounds = {item.tag: item for item in bounds_list}
    if len(bounds) != len(bounds_list):
        raise DomainConfigurationError("process_bounds.json 存在重复测点 tag")

    fault_list = _validate(TypeAdapter(list[FaultDefinition]), faults_raw["faults"], "faults")
    faults = {item.fault_id: item for item in fault_list}
    if len(faults) != len(fault_list):
        raise DomainConfigurationError("faults.json 存在重复 fault_id")

    interlocks = _validate(
        TypeAdapter(list[InterlockRule]), interlocks_raw["rules"], "interlocks"
    )
    process_model = _validate(
        TypeAdapter(ProcessModelDefinition), model_raw, "process_model"
    )
    timebase = _validate(TypeAdapter(Timebase), mechanisms_raw["timebase"], "timebase")

    if not interlocks:
        raise DomainConfigurationError("联锁表为空；无联锁定义不得进行安全结论判定")
    _cross_validate(sensors, bounds, faults, interlocks, process_model)

    pack_id = str(mechanisms_raw["pack_id"])
    for label, raw in (
        ("process_bounds", bounds_raw),
        ("faults", faults_raw),
        ("process_model", model_raw),
    ):
        if str(raw.get("pack_id")) != pack_id:
            raise DomainConfigurationError(f"{label}.pack_id 与 mechanisms.json 不一致")

    domain_hash = content_hash(
        {
            "mechanisms": mechanisms_raw,
            "process_bounds": bounds_raw,
            "faults": faults_raw,
            "process_model": model_raw,
        }
    )
    # 与 InterlockEngine 使用同一规范化规则序列，避免"展示用 file hash"和
    # "运行时表 hash"不一致导致平台误报联锁表被篡改。
    interlock_hash = content_hash([rule.model_dump(mode="json") for rule in interlocks])
    source_hashes = DomainHashes(domain_hash=domain_hash, interlock_hash=interlock_hash)

    assumptions = [
        str(mechanisms_raw.get("disclaimer", "")),
        *[str(note) for note in bounds_raw.get("notes", [])],
        *[str(note) for note in interlocks_raw.get("notes", [])],
        str(process_model.disclaimer),
    ]
    assumptions = [item for item in assumptions if item]
    if any("TODO(mechanism)" in item for item in assumptions):
        assumptions.append(
            "工艺依据不完整：存在 TODO(mechanism) 标记，报告不得据此作出可上线结论。"
        )

    return DomainPack(
        pack_id=pack_id,
        asset_id=str(mechanisms_raw["asset_id"]),
        asset_name=str(mechanisms_raw["asset_name"]),
        disclaimer=str(mechanisms_raw["disclaimer"]),
        provenance=DataSource.MECHANISTIC,
        timebase=timebase,
        sensors=sensors,
        bounds=bounds,
        faults=faults,
        interlocks=interlocks,
        process_model=process_model,
        assumptions=assumptions,
        hashes=source_hashes,
    )


def _cross_validate(
    sensors: dict[str, SensorSpec],
    bounds: dict[str, ProcessBounds],
    faults: dict[FaultKind, FaultDefinition],
    interlocks: list[InterlockRule],
    process_model: ProcessModelDefinition,
) -> None:
    if set(sensors) != set(bounds):
        missing_bounds = sorted(set(sensors) - set(bounds))
        orphan_bounds = sorted(set(bounds) - set(sensors))
        if missing_bounds:
            raise DomainConfigurationError(f"测点缺少 process_bounds：{missing_bounds}")
        raise DomainConfigurationError(f"process_bounds 存在未知测点：{orphan_bounds}")

    for tag, sensor in sensors.items():
        bound = bounds[tag]
        ensure_unit(sensor.instrument_range.unit, sensor.unit, f"{tag} 量程单位")
        ensure_unit(bound.safe_limits.unit, sensor.unit, f"{tag} 安全边界单位")
        if not (
            sensor.instrument_range.low <= bound.safe_limits.low
            < bound.safe_limits.high
            <= sensor.instrument_range.high
        ):
            raise DomainConfigurationError(f"{tag} safe_limits 必须位于仪表量程内")
        if (
            bound.trip_limits.high is not None
            and bound.trip_limits.high > sensor.instrument_range.high
        ):
            raise DomainConfigurationError(f"{tag} 联锁阈值超出仪表量程")

    for fault in faults.values():
        for tag in fault.targetable_tags:
            if tag not in sensors:
                raise DomainConfigurationError(f"故障 {fault.fault_id} 指向未知测点 {tag}")
        for key, value in fault.defaults.items():
            if not isinstance(value.unit, str) or not value.unit:
                raise DomainConfigurationError(f"故障 {fault.fault_id}.{key} 缺少单位")

    baseline_tags = {item.tag for item in process_model.baseline.setpoints}
    if not baseline_tags.issubset(sensors):
        raise DomainConfigurationError("process_model baseline 包含未知测点")

    for rule in interlocks:
        if rule.tag not in sensors:
            raise DomainConfigurationError(f"联锁 {rule.id} 指向未知测点 {rule.tag}")
        bound = bounds[rule.tag]
        if rule.trip_limit.high is not None:
            if bound.trip_limits.high is None:
                raise DomainConfigurationError(
                    f"联锁 {rule.id} 未在 process_bounds 声明 trip_limits"
                )
            if abs(bound.trip_limits.high - rule.trip_limit.high) > 1e-9:
                raise DomainConfigurationError(
                    f"联锁 {rule.id} 阈值与 process_bounds.trip_limits 不一致，平台拒绝启动"
                )
        if rule.action not in process_model.trip_responses:
            raise DomainConfigurationError(f"联锁 {rule.id} 动作缺少被控对象响应模型")
