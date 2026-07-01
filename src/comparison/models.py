"""版本差异比较的数据模型。

本模块定义 `VersionDiffer` 输出的轻量传输对象：
`VersionDiff`、`DiffItem` 和 `CabinetDiff`。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DiffItem:
    """单条差异项 — BOM 行或汇总物料的增/删/改。

    字段说明：
      - `change_type`: "added" | "removed" | "changed"
      - `key`: 复合标识键（如 "(K1,断路器,MCCB-250A,施耐德)"）
      - `old_value`: 旧版本数据 dict（仅 removed/changed）
      - `new_value`: 新版本数据 dict（仅 added/changed）
      - `field_changes`: 字段级变更 {field_name: (old, new)}（仅 changed）
    """

    change_type: str
    key: str
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    field_changes: dict[str, tuple[Any, Any]] | None = None


@dataclass(slots=True)
class CabinetDiff:
    """柜体级差异项。

    柜体按 `cabinet_no` 标识。字段级变更记录在 `field_changes` 中。
    """

    cabinet_no: str
    change_type: str  # "added" | "removed" | "changed"
    old: dict[str, Any] | None = None
    new: dict[str, Any] | None = None
    field_changes: dict[str, tuple[Any, Any]] | None = None


@dataclass(slots=True)
class VersionDiff:
    """完整版本差异报告。

    `metrics` 记录版本间的高级指标对比（如柜体数、BOM 行数、总价）。
    """

    old_version_label: str
    new_version_label: str
    old_metrics: dict[str, Any] = field(default_factory=dict)
    new_metrics: dict[str, Any] = field(default_factory=dict)
    cabinet_changes: list[CabinetDiff] = field(default_factory=list)
    bom_changes: list[DiffItem] = field(default_factory=list)
    summary_changes: list[DiffItem] = field(default_factory=list)
    quote_changes: list[DiffItem] = field(default_factory=list)
    metadata_changes: dict[str, Any] = field(default_factory=dict)
