"""轻量物理单位校验。

平台只接受显式单位，不做隐式换算。接入真实工艺时如需换算，应在边界适配层完成，
并将换算依据写入 artifact。内部变量使用带单位后缀的命名（deg_c、mpa、tph、pct、s）。
"""

from __future__ import annotations

from collections.abc import Iterable

UNIT_ALIASES: dict[str, str] = {
    "°c": "degC",
    "degc": "degC",
    "c": "degC",
    "mpa": "MPa",
    "kpa": "kPa",
    "t/h": "t/h",
    "tph": "t/h",
    "%": "%",
    "percent": "%",
    "s": "s",
    "sec": "s",
    "seconds": "s",
    "degc/s": "degC/s",
    "mpa/s": "MPa/s",
    "t/h/%": "t/h/%",
    "mpa/degc": "MPa/degC",
    "mpa/(t/h)": "MPa/(t/h)",
}

KNOWN_UNITS: frozenset[str] = frozenset(
    {
        "degC",
        "kPa",
        "MPa",
        "t/h",
        "%",
        "s",
        "degC/s",
        "MPa/s",
        "t/h/%",
        "MPa/degC",
        "MPa/(t/h)",
    }
)


def canonical_unit(unit: str) -> str:
    """把常见单位写法归一成平台规范单位。"""
    normalized = UNIT_ALIASES.get(unit.strip().lower())
    if normalized is None:
        if unit in KNOWN_UNITS:
            return unit
        raise ValueError(f"未知单位：{unit!r}")
    return normalized


def ensure_unit(actual: str, expected: str, context: str) -> None:
    """单位不一致必须立即失败，禁止静默按裸数字比较。"""
    actual_canonical = canonical_unit(actual)
    expected_canonical = canonical_unit(expected)
    if actual_canonical != expected_canonical:
        raise ValueError(
            f"{context} 单位不一致：期望 {expected_canonical}，实际 {actual_canonical}"
        )


def all_units(units: Iterable[str]) -> frozenset[str]:
    return frozenset(canonical_unit(unit) for unit in units)


def is_sentinel_value(value: float, measurement_low: float, measurement_high: float) -> bool:
    """识别常见仪表哨兵值。超量程数据在入模前必须判无效。"""
    if value != value:  # NaN
        return True
    if value in {-9999.0, 9999.0, -999.0, 999.0, -32768.0, 32767.0}:
        return True
    return value < measurement_low or value > measurement_high
