"""确定性随机源：所有随机环节都从明确 seed 派生，不使用进程级随机状态。"""

from __future__ import annotations

import hashlib
import random


def derive_seed(*parts: object) -> int:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def rng_for(*parts: object) -> random.Random:
    return random.Random(derive_seed(*parts))


def deterministic_unit(*parts: object) -> float:
    """用于需要一次性随机比例但无法持有 Random 对象的场景。"""
    return rng_for(*parts).random()
