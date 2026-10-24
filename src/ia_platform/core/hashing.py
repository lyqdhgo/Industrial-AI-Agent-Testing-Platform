"""稳定哈希与结论指纹的公共工具。"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


def stable_json(value: Any) -> str:
    """生成不受字典插入顺序影响的 UTF-8 JSON。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def content_hash(value: Any) -> str:
    return sha256_text(stable_json(value))


def normalize_text_for_fingerprint(text: str) -> str:
    """归一化自然语言，避免措辞抖动造成假回归。

    数字和单位会单独结构化抽取到指纹的 setpoints / tags 字段中，因此这里剔除，
    以免“温度 220℃”和“温度 221℃”被当成不同的结论文本。
    """
    normalized = text.lower()
    normalized = re.sub(r"[-+]?\d+(?:\.\d+)?", " ", normalized)
    normalized = re.sub(r"(建议|推荐|可以|应当|需要|请|可能)", " ", normalized)
    normalized = re.sub(r"[，。！？、；：,.!?;:\s\"'`()\[\]{}<>/\\|]+", " ", normalized)
    return normalized.strip()


def sorted_values(values: Sequence[str]) -> list[str]:
    return sorted(str(item) for item in values)


def mapping_or_empty(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return value or {}
