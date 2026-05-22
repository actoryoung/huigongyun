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
class ProjectResult:
    project: ProjectDocument
    cabinets: list[CabinetRecord] = field(default_factory=list)
    bom_lines: list[BomLine] = field(default_factory=list)
    summary: list[MaterialRecord] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    user_edits: list[UserEdit] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)
