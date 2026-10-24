"""平台领域异常。"""

from __future__ import annotations


class IatpError(Exception):
    """平台可预期错误的基类。"""


class DomainConfigurationError(IatpError):
    """domain/ 缺失或自相矛盾。禁止用代码中的默认值悄悄兜底。"""


class CatalogError(IatpError):
    """用例、Agent 或套件目录不合法。"""


class PolicyViolation(IatpError):
    """安全硬约束被违反。"""


class ArtifactError(IatpError):
    """证据产物缺失或路径越界。"""


class BaselineIncompatibleError(IatpError):
    """基线三个指纹任一不匹配时，拒绝回归对比。"""
