"""Huigongyun MVP 的数据模型定义。

本模块定义流水线中使用的轻量传输和领域对象：`ProjectDocument`、
`CabinetRecord`、`MaterialRecord`、`BomLine`、`ProjectResult` 及辅助类型。
这些 dataclass 用于内存编排、导出为 JSON，以及持久化存储。

I/O 说明：
    - `ProjectDocument` 表示解析后的输入结构（项目名称、文件列表及元数据）。
    - `ProjectResult` 为流水线输出，包含 cabinets、bom_lines、summary、
        quote_lines、issues，以及将工件映射到本地路径或 presigned URL 的 `outputs` 字段。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SourceRef:
    file_name: str
    file_type: str
    page_no: int | None = None
    sheet_name: str | None = None
    row_no: int | None = None
    column_name: str | None = None
    excerpt: str | None = None
    confidence: float | None = None


@dataclass(slots=True)
class CabinetRecord:
    """表示从输入中提取出的单个机柜候选项。

    字段说明：
      - `cabinet_no`：机柜标识
      - `sources`：来源引用（`SourceRef` 列表），用于可追溯性
    """
    cabinet_no: str
    cabinet_type: str | None = None
    rated_current: str | None = None
    dimensions: str | None = None
    circuit_count: int | None = None
    quantity: int = 1
    inbound_outbound: str | None = None
    grounding_mode: str | None = None
    sources: list[SourceRef] = field(default_factory=list)
    confidence: float = 0.0
    remarks: str | None = None


@dataclass(slots=True)
class MaterialRecord:
    """表示 BOM 行中的单个物料/元件候选。

    该记录设计为冗长以同时携带原始与归一化值、定价线索与来源信息，
    以便审计与追溯。
    """
    name: str
    spec: str | None = None
    unit: str | None = None
    quantity: float = 0.0
    brand: str | None = None
    manufacturer: str | None = None
    normalized_name: str | None = None
    normalized_spec: str | None = None
    source: SourceRef | None = None
    confidence: float = 0.0
    long_lead_time: bool = False
    unit_price: float | None = None
    price_source: str | None = None
    price_confidence: float = 0.0
    subtotal: float | None = None
    price_missing: bool = False
    remarks: str | None = None


@dataclass(slots=True)
class BomLine:
    cabinet_no: str
    material: MaterialRecord
    derived_from: str = "unknown"
    risk_tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ProjectDocument:
    project_name: str
    files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ValidationIssue:
    issue_type: str
    severity: str
    message: str
    cabinet_no: str | None = None
    material_name: str | None = None
    source: SourceRef | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class UserEdit:
    scope: str
    target: str
    field_name: str
    old_value: str | None
    new_value: str | None
    note: str | None = None


@dataclass(slots=True)
class QuoteLine:
    cabinet_no: str
    material_name: str
    spec: str | None = None
    unit: str | None = None
    quantity: float = 0.0
    brand: str | None = None
    unit_price: float | None = None
    subtotal: float | None = None
    price_source: str | None = None
    price_confidence: float = 0.0
    price_missing: bool = False
    remarks: str | None = None


@dataclass(slots=True)
class ProjectResult:
    """流水线输出容器。

    `outputs` 将如 'json'、'excel' 等工件键映射到本地文件路径，或在
    上传到对象存储后返回的 presigned URL。
    """
    project: ProjectDocument
    cabinets: list[CabinetRecord] = field(default_factory=list)
    bom_lines: list[BomLine] = field(default_factory=list)
    summary: list[MaterialRecord] = field(default_factory=list)
    quote_lines: list[QuoteLine] = field(default_factory=list)
    quote_totals: dict[str, Any] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)
    user_edits: list[UserEdit] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)
