"""确定性被控对象与仪表通道仿真。

仿真器只描述"被控对象如何响应"，不实现工业控制策略，也不读取被测 Agent 的结论。
SIS 由独立联锁引擎驱动，仿真器仅执行其动作后果。
"""

from __future__ import annotations

import math
from collections import deque
from datetime import UTC, datetime, timedelta

from ia_platform.core.models import (
    AgentObservation,
    ControlKind,
    DomainPack,
    InterlockAction,
    SampleQuality,
    SensorContext,
    TaggedValue,
    TelemetryRecord,
    TelemetrySample,
    TestCase,
)
from ia_platform.core.units import ensure_unit
from ia_platform.simulation.faults import FaultInjectionEngine
from ia_platform.simulation.rng import rng_for

SIM_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


class ProcessSimulator:
    def __init__(self, case: TestCase, domain: DomainPack, seed: int) -> None:
        self.case = case
        self.domain = domain
        self.seed = seed
        self.step_s = domain.timebase.simulation_step_s
        self.records: list[TelemetryRecord] = []
        self.stimulus_events: list[dict[str, object]] = []
        self.sis_feed_tripped = False
        self.sis_relief_open = False

        baseline = {
            item.tag: item.value for item in domain.process_model.baseline.setpoints
        }
        setpoints = dict(baseline)
        initial_conditions = {item.tag: item.value for item in case.initial_conditions}
        for tag, value in initial_conditions.items():
            setpoints[tag] = value

        self.setpoints: dict[str, float] = {
            tag: setpoints[tag] for tag in ("TI-203", "PI-203", "FI-201")
        }
        self.true_values: dict[str, float] = {
            "TI-203": initial_conditions.get("TI-203", baseline["TI-203"]),
            "PI-203": initial_conditions.get("PI-203", baseline["PI-203"]),
            "FI-201": initial_conditions.get("FI-201", baseline["FI-201"]),
        }
        self.valve_command_pct = self._valve_from_flow(self.true_values["FI-201"])
        self.valve_actual_pct = self.valve_command_pct
        self.true_values["LV-201"] = self.valve_actual_pct

        self.faults = FaultInjectionEngine(case, domain, seed)
        self._noise_rngs = {tag: rng_for(seed, case.id, tag, "noise") for tag in domain.sensors}
        self._sample_index = {tag: 0 for tag in domain.sensors}
        self._last_sample_t = {tag: -1e9 for tag in domain.sensors}
        self._valve_stimulus_applied = False

        self._dead_steps: dict[str, int] = {}
        self._target_queues: dict[str, deque[float]] = {}
        for tag, sensor in domain.sensors.items():
            steps = max(1, math.ceil(sensor.dynamics.dead_time_s / self.step_s))
            self._dead_steps[tag] = steps
            initial_target = self._initial_target(tag)
            self._target_queues[tag] = deque([initial_target] * steps, maxlen=steps)

        self._emit_samples(0.0)

    # ------------------------------------------------------------------
    # 过程响应
    # ------------------------------------------------------------------

    def _initial_target(self, tag: str) -> float:
        if tag == "TI-203":
            return self.setpoints[tag]
        if tag == "PI-203":
            return self.setpoints[tag]
        if tag == "FI-201":
            return self.setpoints[tag]
        return self._valve_from_flow(self.setpoints["FI-201"])

    def _valve_from_flow(self, flow_tph: float) -> float:
        relation = self.domain.process_model.relations.valve_flow
        gain = relation.flow_gain.value
        zero = relation.flow_at_zero.value
        return max(0.0, min(100.0, (flow_tph - zero) / gain))

    def _flow_from_valve(self, valve_pct: float) -> float:
        relation = self.domain.process_model.relations.valve_flow
        return relation.flow_at_zero.value + relation.flow_gain.value * valve_pct

    def _oscillation(self, t_s: float, tag: str) -> float:
        osc = self.domain.process_model.normal_oscillation
        if tag == "TI-203":
            phase = 2.0 * math.pi * t_s / osc.temperature_period_s
            return osc.temperature_amplitude.value * math.sin(phase)
        if tag == "PI-203":
            phase = 2.0 * math.pi * t_s / osc.pressure_period_s
            return osc.pressure_amplitude.value * math.sin(phase)
        if tag == "FI-201":
            phase = 2.0 * math.pi * t_s / osc.flow_period_s
            return osc.flow_amplitude.value * math.sin(phase)
        return 0.0

    def _pressure_target(self, t_s: float) -> float:
        coupling = self.domain.process_model.relations.pressure_coupling
        temp_dev = self.true_values["TI-203"] - coupling.temperature_reference.value
        flow_dev = self.true_values["FI-201"] - coupling.flow_reference.value
        return (
            self.setpoints["PI-203"]
            + coupling.temperature_gain.value * temp_dev
            + coupling.flow_gain.value * flow_dev
            + self._oscillation(t_s, "PI-203")
        )

    def _delayed(self, tag: str, target: float) -> float:
        queue = self._target_queues[tag]
        queue.append(target)
        return queue[0]

    def _follow(self, current: float, target: float, tau_s: float, dt_s: float) -> float:
        alpha = 1.0 - math.exp(-dt_s / max(tau_s, 1e-9))
        return current + (target - current) * alpha

    def _activate_valve_stimulus(self, t_s: float) -> None:
        if self._valve_stimulus_applied:
            return
        plan = self.faults.valve_sticking_plan()
        if plan is None or not (plan.start_s <= t_s < plan.end_s):
            return
        flow_step = plan.params["flow_step"].value
        updated = min(100.0, max(0.0, self.setpoints["FI-201"] + flow_step))
        self.setpoints["FI-201"] = updated
        self._valve_stimulus_applied = True
        self.stimulus_events.append(
            {
                "t_s": t_s,
                "tag": "FI-201",
                "value": updated,
                "unit": "t/h",
                "source": "simulator_test_stimulus",
                "reason": "负荷阶跃测试激励（非 Agent 指令），用于暴露阀杆卡涩",
            }
        )

    def step(self, t_s: float, dt_s: float | None = None) -> None:
        dt = dt_s if dt_s is not None else self.step_s
        self._activate_valve_stimulus(t_s)
        effect = self.faults.update(t_s, dt)
        if effect.valve_stuck:
            self.faults.lock_valve_if_needed(t_s, self.valve_actual_pct)

        model = self.domain.process_model
        sim = model.simulation

        # 故障源改变热/压力平衡点，再由一阶惯性把真实状态带向新平衡点。
        # 不直接改测量值，也不制造瞬时阶跃。
        temp_target = (
            self.setpoints["TI-203"]
            + self._oscillation(t_s, "TI-203")
            + self.faults.temperature_offset(t_s)
        )
        if self.sis_feed_tripped:
            temp_target = min(temp_target, self.domain.bounds_for("TI-203").safe_limits.low)
        pressure_target = self._pressure_target(t_s) + self.faults.pressure_offset(t_s)
        valve_target = 0.0 if self.sis_feed_tripped else self._valve_from_flow(
            self.setpoints["FI-201"]
        )

        temp_target_delayed = self._delayed("TI-203", temp_target)
        pressure_target_delayed = self._delayed("PI-203", pressure_target)
        valve_target_delayed = self._delayed("LV-201", valve_target)

        self.true_values["TI-203"] = self._follow(
            self.true_values["TI-203"],
            temp_target_delayed,
            self.domain.sensor("TI-203").dynamics.time_constant_s,
            dt,
        )
        self.true_values["PI-203"] = self._follow(
            self.true_values["PI-203"],
            pressure_target_delayed,
            sim.pressure_follow_time_constant_s,
            dt,
        )

        if effect.valve_stuck:
            locked = self.faults.valve_locked_position()
            if locked is not None:
                self.valve_actual_pct = locked
        else:
            self.valve_actual_pct = self._follow(
                self.valve_actual_pct,
                valve_target_delayed,
                sim.valve_follow_time_constant_s,
                dt,
            )
        self.true_values["LV-201"] = self.valve_actual_pct
        self.valve_command_pct = valve_target

        flow_physical_target = self._flow_from_valve(self.valve_actual_pct)
        # 实际流量由阀位物理关系决定；流量设定值用于评价需求满足度。
        self.true_values["FI-201"] = self._follow(
            self.true_values["FI-201"],
            flow_physical_target,
            sim.flow_follow_time_constant_s,
            dt,
        )

        if self.sis_relief_open:
            relief = model.trip_responses[InterlockAction.OPEN_PRESSURE_RELIEF]
            if relief.pressure_relief_rate is not None:
                # 泄压阀在压力回落到正常设定值后回座，避免把压力抽到物理零值。
                if self.true_values["PI-203"] > self.setpoints["PI-203"]:
                    self.true_values["PI-203"] -= relief.pressure_relief_rate.value * dt
                else:
                    self.sis_relief_open = False

        self._clamp_true_values()
        self._emit_samples(t_s)

    def _clamp_true_values(self) -> None:
        for tag in ("TI-203", "PI-203", "FI-201", "LV-201"):
            sensor = self.domain.sensor(tag)
            self.true_values[tag] = min(
                sensor.instrument_range.high,
                max(sensor.instrument_range.low, self.true_values[tag]),
            )

    def _emit_samples(self, t_s: float) -> None:
        for tag, sensor in self.domain.sensors.items():
            last = self._last_sample_t[tag]
            if last >= 0 and t_s - last < sensor.sample_interval_s - 1e-9:
                continue
            if last < 0 and t_s != 0.0:
                continue
            self._last_sample_t[tag] = t_s
            self._sample_index[tag] += 1
            true_value = self.true_values[tag]
            noise = self._noise_rngs[tag].gauss(0.0, sensor.noise.sigma)
            raw_measured = true_value + noise
            self.faults.remember_good_measurement(t_s, tag, raw_measured)
            measured, quality = self.faults.measurement(t_s, tag, true_value, raw_measured)
            delivery = self.faults.delivery(t_s, tag, self._sample_index[tag])
            if not delivery.delivered or (
                delivery.quality == SampleQuality.UNCERTAIN
                and quality == SampleQuality.GOOD
            ):
                quality = SampleQuality.UNCERTAIN
            command_value, command_unit = self._command_for(tag)
            self.records.append(
                TelemetryRecord(
                    t_s=t_s,
                    tag=tag,
                    unit=sensor.unit,
                    true_value=true_value,
                    measured_value=measured,
                    received_s=t_s + delivery.delay_s,
                    quality=quality,
                    delivered=delivery.delivered,
                    command_value=command_value,
                    command_unit=command_unit,
                )
            )

    def _command_for(self, tag: str) -> tuple[float | None, str | None]:
        if tag in {"TI-203", "PI-203", "FI-201"}:
            return self.setpoints[tag], self.domain.sensor(tag).unit
        if tag == "LV-201":
            return self.valve_command_pct, "%"
        return None, None

    # ------------------------------------------------------------------
    # SIS / DCS
    # ------------------------------------------------------------------

    def apply_sis_action(self, action: InterlockAction, t_s: float) -> None:
        model = self.domain.process_model
        response = model.trip_responses[action]
        if action == InterlockAction.TRIP_REACTOR_FEED and not self.sis_feed_tripped:
            self.sis_feed_tripped = True
            self.setpoints["FI-201"] = 0.0
            self.stimulus_events.append(
                {
                    "t_s": t_s,
                    "tag": "FI-201",
                    "value": 0.0,
                    "unit": "t/h",
                    "source": "SIS",
                    "reason": "SIS 跳车：切除进料",
                }
            )
        if action == InterlockAction.OPEN_PRESSURE_RELIEF and not self.sis_relief_open:
            self.sis_relief_open = True
        if response.close_valve_to is not None:
            self.valve_command_pct = response.close_valve_to.value

    def apply_dcs_setpoint(self, tag: str, value: float, unit: str, t_s: float) -> None:
        """只允许 SafetyGate 在放行后调用；Agent 适配层没有此入口。"""
        if tag not in self.domain.sensors:
            raise KeyError(f"未知 DCS 位号 {tag}")
        if tag not in {"TI-203", "PI-203", "FI-201", "LV-201"}:
            raise KeyError(f"DCS 不支持位号 {tag}")
        ensure_unit(unit, self.domain.sensor(tag).unit, f"DCS 写入 {tag}")
        if tag == "LV-201":
            self.valve_command_pct = value
        else:
            self.setpoints[tag] = value
        self.stimulus_events.append(
            {
                "t_s": t_s,
                "tag": tag,
                "value": value,
                "unit": unit,
                "source": "DCS_WRITE",
                "reason": "SafetyGate 放行后的 DCS 设定值写入",
            }
        )

    def dcs_setpoints(self) -> list[TaggedValue]:
        return [
            TaggedValue(tag=tag, value=self.setpoints[tag], unit=self.domain.sensor(tag).unit)
            for tag in ("TI-203", "PI-203", "FI-201")
        ]

    # ------------------------------------------------------------------
    # 观测与证据
    # ------------------------------------------------------------------

    def true_value(self, tag: str) -> float:
        return self.true_values[tag]

    def observation(self, observed_at_s: float, history_window_s: float) -> AgentObservation:
        low = observed_at_s - history_window_s
        samples: list[TelemetrySample] = []
        for record in self.records:
            if (
                record.delivered
                and record.measured_value is not None
                and record.received_s <= observed_at_s + 1e-9
                and record.t_s >= low - 1e-9
            ):
                samples.append(
                    TelemetrySample(
                        tag=record.tag,
                        t_s=record.t_s,
                        received_s=record.received_s,
                        value=record.measured_value,
                        unit=record.unit,
                        quality=record.quality,
                        command_value=record.command_value,
                        command_unit=record.command_unit,
                    )
                )
        samples.sort(key=lambda item: (item.received_s, item.tag))
        sensor_context = []
        for tag, sensor in self.domain.sensors.items():
            bound = self.domain.bounds_for(tag)
            sensor_context.append(
                SensorContext(
                    tag=tag,
                    name=sensor.name,
                    unit=sensor.unit,
                    safe_low=bound.safe_limits.low,
                    safe_high=bound.safe_limits.high,
                    recommended_low=bound.recommended_band.low,
                    recommended_high=bound.recommended_band.high,
                )
            )
        return AgentObservation(
            observation_id=f"{self.case.id}-{round(observed_at_s * 10):07d}",
            asset_id=self.domain.asset_id,
            observed_at_s=observed_at_s,
            timestamp=SIM_EPOCH + timedelta(seconds=observed_at_s),
            scenario_instruction=self.case.agent_task,
            samples=samples,
            sensor_context=sensor_context,
            dcs_setpoints=self.dcs_setpoints(),
            history_window_s=history_window_s,
        )


def is_control_kind_dcs_writable(kind: ControlKind) -> bool:
    return kind == ControlKind.SET_SETPOINT
