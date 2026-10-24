"""故障注入器。

故障只能作用于两条通路之一：
1. 真实过程状态（超温、超压、卡涩的物理后果）；
2. 测量/传输通道（漂移、断线、网络抖动）。
任何注入都不得直接篡改 Agent 响应或期望结果。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from ia_platform.core.errors import DomainConfigurationError
from ia_platform.core.models import (
    DomainPack,
    FaultKind,
    FaultPlan,
    SampleQuality,
    TestCase,
)
from ia_platform.simulation.rng import rng_for


class InjectionChannel(StrEnum):
    PROCESS = "process"
    MEASUREMENT = "measurement"
    NETWORK = "network"


@dataclass(frozen=True)
class MeasurementEffect:
    offset: float = 0.0
    force_bad: bool = False
    freeze: bool = False


@dataclass(frozen=True)
class DeliveryEffect:
    delay_s: float = 0.0
    delivered: bool = True
    quality: SampleQuality = SampleQuality.GOOD


@dataclass
class StepEffect:
    temperature_delta_deg_c: float = 0.0
    pressure_delta_mpa: float = 0.0
    valve_stuck: bool = False


class FaultInjector(Protocol):
    plan: FaultPlan

    @property
    def channel(self) -> InjectionChannel: ...

    def active(self, t_s: float) -> bool: ...

    def update(self, t_s: float, dt_s: float) -> StepEffect: ...

    def measurement(
        self, t_s: float, tag: str, true_value: float, raw_measured: float
    ) -> MeasurementEffect: ...

    def delivery(self, t_s: float, tag: str, sample_index: int) -> DeliveryEffect: ...

    def artifact(self) -> dict[str, object]: ...


def _param(plan: FaultPlan, key: str) -> float:
    try:
        return plan.params[key].value
    except KeyError as exc:
        raise DomainConfigurationError(f"故障 {plan.kind} 缺少参数 {key}") from exc


def _param_unit(plan: FaultPlan, key: str) -> str:
    try:
        return plan.params[key].unit
    except KeyError as exc:
        raise DomainConfigurationError(f"故障 {plan.kind} 缺少参数 {key}") from exc


@dataclass
class _BaseInjector:
    plan: FaultPlan
    seed: int

    @property
    def channel(self) -> InjectionChannel:  # pragma: no cover - dataclass 覆盖
        return InjectionChannel.PROCESS

    def active(self, t_s: float) -> bool:
        return self.plan.start_s <= t_s < self.plan.end_s

    def update(self, t_s: float, dt_s: float) -> StepEffect:
        return StepEffect()

    def measurement(
        self, t_s: float, tag: str, true_value: float, raw_measured: float
    ) -> MeasurementEffect:
        return MeasurementEffect()

    def delivery(self, t_s: float, tag: str, sample_index: int) -> DeliveryEffect:
        return DeliveryEffect()

    def artifact(self) -> dict[str, object]:
        return {
            "kind": self.plan.kind.value,
            "target_tag": self.plan.target_tag,
            "start_s": self.plan.start_s,
            "duration_s": self.plan.duration_s,
            "seed": self.seed,
            "params": {
                key: {"value": value.value, "unit": value.unit}
                for key, value in self.plan.params.items()
            },
        }


@dataclass
class SuperTemperatureInjector(_BaseInjector):
    injected_deg_c: float = 0.0

    @property
    def channel(self) -> InjectionChannel:
        return InjectionChannel.PROCESS

    def update(self, t_s: float, dt_s: float) -> StepEffect:
        if not self.active(t_s) or self.plan.target_tag != "TI-203":
            return StepEffect()
        max_rate = _param(self.plan, "max_rate")
        magnitude = _param(self.plan, "magnitude")
        remaining = magnitude - self.injected_deg_c
        delta = min(max(max_rate, 0.0) * dt_s, max(remaining, 0.0))
        self.injected_deg_c += delta
        return StepEffect(temperature_delta_deg_c=delta)

    def artifact(self) -> dict[str, object]:
        value = super().artifact()
        value["injected_total"] = {"value": self.injected_deg_c, "unit": "degC"}
        return value


@dataclass
class OverPressureInjector(_BaseInjector):
    injected_mpa: float = 0.0

    @property
    def channel(self) -> InjectionChannel:
        return InjectionChannel.PROCESS

    def update(self, t_s: float, dt_s: float) -> StepEffect:
        if not self.active(t_s) or self.plan.target_tag != "PI-203":
            return StepEffect()
        max_rate = _param(self.plan, "max_rate")
        magnitude = _param(self.plan, "magnitude")
        remaining = magnitude - self.injected_mpa
        delta = min(max(max_rate, 0.0) * dt_s, max(remaining, 0.0))
        self.injected_mpa += delta
        return StepEffect(pressure_delta_mpa=delta)

    def artifact(self) -> dict[str, object]:
        value = super().artifact()
        value["injected_total"] = {"value": self.injected_mpa, "unit": "MPa"}
        return value


@dataclass
class SensorDriftInjector(_BaseInjector):
    offset: float = 0.0
    repaired: bool = False

    @property
    def channel(self) -> InjectionChannel:
        return InjectionChannel.MEASUREMENT

    def update(self, t_s: float, dt_s: float) -> StepEffect:
        if self.active(t_s):
            rate = _param(self.plan, "rate")
            magnitude = _param(self.plan, "magnitude")
            sign = 1.0 if magnitude >= 0 else -1.0
            remaining = max(abs(magnitude) - abs(self.offset), 0.0)
            delta = min(abs(rate) * dt_s, remaining)
            self.offset += sign * delta
        elif self.offset != 0.0:
            # 故障窗口结束后模拟仪表检修，偏移快速衰减到 0，便于验证恢复段。
            self.offset *= math.exp(-dt_s / 5.0)
            if abs(self.offset) < 1e-6:
                self.offset = 0.0
                self.repaired = True
        return StepEffect()

    def measurement(
        self, t_s: float, tag: str, true_value: float, raw_measured: float
    ) -> MeasurementEffect:
        if tag != self.plan.target_tag:
            return MeasurementEffect()
        return MeasurementEffect(offset=self.offset)

    def artifact(self) -> dict[str, object]:
        value = super().artifact()
        value["current_offset"] = {
            "value": self.offset,
            "unit": _param_unit(self.plan, "magnitude"),
        }
        return value


@dataclass
class ValveStickingInjector(_BaseInjector):
    locked_valve_pct: float | None = None

    @property
    def channel(self) -> InjectionChannel:
        return InjectionChannel.PROCESS

    def update(self, t_s: float, dt_s: float) -> StepEffect:
        return StepEffect(valve_stuck=self.active(t_s))

    def artifact(self) -> dict[str, object]:
        value = super().artifact()
        value["locked_valve_pct"] = self.locked_valve_pct
        return value


@dataclass
class SensorDisconnectInjector(_BaseInjector):
    frozen_value: float | None = None
    last_good_measurement: float | None = None

    @property
    def channel(self) -> InjectionChannel:
        return InjectionChannel.MEASUREMENT

    def update(self, t_s: float, dt_s: float) -> StepEffect:
        if not self.active(t_s):
            self.frozen_value = None
        return StepEffect()

    def measurement(
        self, t_s: float, tag: str, true_value: float, raw_measured: float
    ) -> MeasurementEffect:
        if tag != self.plan.target_tag or not self.active(t_s):
            return MeasurementEffect()
        if self.frozen_value is None:
            self.frozen_value = (
                self.last_good_measurement
                if self.last_good_measurement is not None
                else raw_measured
            )
        return MeasurementEffect(force_bad=True, freeze=True)

    def observe_measurement(self, tag: str, value: float) -> None:
        if tag == self.plan.target_tag and not self.active(0.0) and self.frozen_value is None:
            self.last_good_measurement = value

    def artifact(self) -> dict[str, object]:
        value = super().artifact()
        value["frozen_value"] = self.frozen_value
        value["quality_forced"] = "bad"
        return value


@dataclass
class NetworkJitterInjector(_BaseInjector):
    delivery_count: int = 0
    _rngs: dict[str, random.Random] = field(default_factory=dict)

    @property
    def channel(self) -> InjectionChannel:
        return InjectionChannel.NETWORK

    def _rng(self, tag: str) -> random.Random:
        if tag not in self._rngs:
            self._rngs[tag] = rng_for(self.seed, tag, "delivery")
        return self._rngs[tag]

    def delivery(self, t_s: float, tag: str, sample_index: int) -> DeliveryEffect:
        if tag != self.plan.target_tag or not self.active(t_s):
            return DeliveryEffect()
        rng = self._rng(tag)
        self.delivery_count += 1
        drop_rate = max(0.0, min(100.0, _param(self.plan, "drop_rate"))) / 100.0
        reorder_rate = max(0.0, min(100.0, _param(self.plan, "reorder_rate"))) / 100.0
        delay = max(0.0, _param(self.plan, "delay"))
        draw = rng.random()
        if draw < drop_rate:
            return DeliveryEffect(
                delay_s=delay,
                delivered=False,
                quality=SampleQuality.UNCERTAIN,
            )
        delay_factor = 0.5 + rng.random()
        extra_delay = delay * delay_factor
        if rng.random() < reorder_rate:
            extra_delay += max(2.0, delay * 0.35)
        quality = SampleQuality.UNCERTAIN if extra_delay > 1e-9 else SampleQuality.GOOD
        return DeliveryEffect(delay_s=extra_delay, delivered=True, quality=quality)

    def artifact(self) -> dict[str, object]:
        value = super().artifact()
        value["delivery_count"] = self.delivery_count
        return value


class FaultInjectionEngine:
    """聚合当前用例的所有注入器，并隔离各故障的物理通道。"""

    def __init__(self, case: TestCase, domain: DomainPack, seed: int) -> None:
        self.case = case
        self.domain = domain
        self.seed = seed
        self.injectors = [self._build(plan) for plan in case.faults]
        self._measurement_observers = [
            item for item in self.injectors if isinstance(item, SensorDisconnectInjector)
        ]

    def _build(self, plan: FaultPlan) -> FaultInjector:
        seed = rng_for(self.seed, self.case.id, plan.kind.value, plan.seed_offset).randrange(
            0, 2**32
        )
        if plan.kind == FaultKind.SUPER_TEMPERATURE:
            return SuperTemperatureInjector(plan=plan, seed=seed)
        if plan.kind == FaultKind.OVER_PRESSURE:
            return OverPressureInjector(plan=plan, seed=seed)
        if plan.kind == FaultKind.SENSOR_DRIFT:
            return SensorDriftInjector(plan=plan, seed=seed)
        if plan.kind == FaultKind.VALVE_STICKING:
            return ValveStickingInjector(plan=plan, seed=seed)
        if plan.kind == FaultKind.SENSOR_DISCONNECT:
            return SensorDisconnectInjector(plan=plan, seed=seed)
        if plan.kind == FaultKind.NETWORK_JITTER:
            return NetworkJitterInjector(plan=plan, seed=seed)
        raise DomainConfigurationError(f"缺少故障注入实现：{plan.kind}")

    def update(self, t_s: float, dt_s: float) -> StepEffect:
        aggregate = StepEffect()
        for injector in self.injectors:
            effect = injector.update(t_s, dt_s)
            aggregate.temperature_delta_deg_c += effect.temperature_delta_deg_c
            aggregate.pressure_delta_mpa += effect.pressure_delta_mpa
            aggregate.valve_stuck = aggregate.valve_stuck or effect.valve_stuck
        return aggregate

    def temperature_offset(self, t_s: float) -> float:
        """热失控对温度平衡点的累计偏移，而不是对测量值的瞬时篡改。"""
        return sum(
            injector.injected_deg_c
            for injector in self.injectors
            if isinstance(injector, SuperTemperatureInjector) and injector.active(t_s)
        )

    def pressure_offset(self, t_s: float) -> float:
        """压力累积源对压力平衡点的累计偏移。"""
        return sum(
            injector.injected_mpa
            for injector in self.injectors
            if isinstance(injector, OverPressureInjector) and injector.active(t_s)
        )

    def measurement(
        self, t_s: float, tag: str, true_value: float, raw_measured: float
    ) -> tuple[float | None, SampleQuality]:
        offset = 0.0
        quality = SampleQuality.GOOD
        freeze_value: float | None = None
        for injector in self.injectors:
            effect = injector.measurement(t_s, tag, true_value, raw_measured)
            offset += effect.offset
            if effect.force_bad:
                quality = SampleQuality.BAD
            if effect.freeze:
                typed = injector
                if isinstance(typed, SensorDisconnectInjector):
                    freeze_value = typed.frozen_value
        value = freeze_value if freeze_value is not None else raw_measured + offset
        return value, quality

    def remember_good_measurement(self, t_s: float, tag: str, value: float) -> None:
        for injector in self._measurement_observers:
            # 每个断线注入器只能记忆自己目标位号的末值；早期实现把最后一个
            # 位号（LV-201）的测量值当成 TI-203 的冻结值，恢复后造成假超温。
            if tag == injector.plan.target_tag and not injector.active(t_s):
                injector.last_good_measurement = value

    def delivery(self, t_s: float, tag: str, sample_index: int) -> DeliveryEffect:
        effect = DeliveryEffect()
        for injector in self.injectors:
            item = injector.delivery(t_s, tag, sample_index)
            if item.delay_s > effect.delay_s:
                effect = DeliveryEffect(
                    delay_s=item.delay_s,
                    delivered=item.delivered and effect.delivered,
                    quality=item.quality
                    if item.quality == SampleQuality.UNCERTAIN
                    else effect.quality,
                )
        return effect

    def valve_locked_position(self) -> float | None:
        for injector in self.injectors:
            if isinstance(injector, ValveStickingInjector):
                return injector.locked_valve_pct
        return None

    def lock_valve_if_needed(self, t_s: float, valve_pct: float) -> None:
        """阀杆卡涩在故障起始时刻锁住当前阀位。"""
        for injector in self.injectors:
            if (
                isinstance(injector, ValveStickingInjector)
                and injector.active(t_s)
                and injector.locked_valve_pct is None
            ):
                injector.locked_valve_pct = valve_pct

    def valve_sticking_plan(self) -> FaultPlan | None:
        for injector in self.injectors:
            if isinstance(injector, ValveStickingInjector):
                return injector.plan
        return None

    def active_faults(self, t_s: float) -> list[FaultPlan]:
        return [injector.plan for injector in self.injectors if injector.active(t_s)]

    def artifacts(self) -> list[dict[str, object]]:
        return [injector.artifact() for injector in self.injectors]
