"""版本差异比较包。

提供 `VersionDiffer` 用于比较两个 ``ProjectResult`` 并生成 ``VersionDiff`` 报告。
"""

from .differ import VersionDiffer
from .models import CabinetDiff, DiffItem, VersionDiff

__all__ = ["CabinetDiff", "DiffItem", "VersionDiff", "VersionDiffer"]
