from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from ..indexing.cabinets import CabinetIndexBuilder
from ..models import BomLine, MaterialRecord, ProjectDocument, ProjectResult, SourceRef


class ExcelCabinetAndBomExtractor:
    """Build cabinet and BOM records from parsed Excel sheet metadata."""

    CABINET_KEYS = ("柜号", "cabinet_no", "柜位", "柜体", "柜名")
    CABINET_TYPE_KEYS = ("柜型", "cabinet_type", "类型")
    RATED_CURRENT_KEYS = ("额定电流", "电流", "In", "额定电流(A)")
    QUANTITY_KEYS = ("数量", "qty", "数量(台)", "件数")
    MATERIAL_NAME_KEYS = ("物料名称", "名称", "元件名称", "设备名称", "物料", "品名")
    SPEC_KEYS = ("规格型号", "规格", "型号", "型号规格", "spec")
    UNIT_KEYS = ("单位", "unit")
    BRAND_KEYS = ("品牌", "厂家", "生产厂家", "manufacturer")

    def extract(self, document: ProjectDocument) -> ProjectResult:
        result = ProjectResult(project=document)
        sheets = document.metadata.get("sheets", []) if isinstance(document.metadata, dict) else []

        cabinet_result = CabinetIndexBuilder().build(document)
        bom_lines: list[BomLine] = []

        for sheet in sheets:
            sheet_name = str(sheet.get("name", "sheet"))
            for record in sheet.get("records", []):
                if not isinstance(record, dict):
                    continue

                row_no = int(record.get("_row_no", 0) or 0)
                cabinet_no = self._first_text(record, self.CABINET_KEYS) or "UNASSIGNED"

                material_name = self._first_text(record, self.MATERIAL_NAME_KEYS)
                if not material_name:
                    continue

                material = MaterialRecord(
                    name=material_name,
                    spec=self._first_text(record, self.SPEC_KEYS),
                    unit=self._first_text(record, self.UNIT_KEYS),
                    quantity=self._parse_quantity(self._first_value(record, self.QUANTITY_KEYS), default=1),
                    brand=self._first_text(record, self.BRAND_KEYS),
                    manufacturer=self._first_text(record, self.BRAND_KEYS),
                    source=self._build_source(document, sheet_name, row_no, record),
                    confidence=0.7,
                )
                bom_lines.append(
                    BomLine(
                        cabinet_no=cabinet_no,
                        material=material,
                        derived_from=f"excel:{sheet_name}:{row_no}",
                        risk_tags=self._build_risk_tags(material),
                    )
                )

        result.cabinets = cabinet_result.cabinets
        result.bom_lines = bom_lines
        if cabinet_result.notes:
            result.project.metadata = {
                **result.project.metadata,
                "cabinet_index_notes": cabinet_result.notes,
                "cabinet_index_unresolved_rows": cabinet_result.unresolved_rows,
            }
        return result

    def _build_source(self, document: ProjectDocument, sheet_name: str, row_no: int, record: dict[str, Any]) -> SourceRef:
        file_name = Path(document.files[0]).name if document.files else document.project_name
        excerpt = self._first_text(record, self.MATERIAL_NAME_KEYS) or self._first_text(record, self.CABINET_KEYS)
        return SourceRef(
            file_name=file_name,
            file_type="excel",
            sheet_name=sheet_name,
            row_no=row_no,
            excerpt=excerpt,
            confidence=0.7,
        )

    def _build_risk_tags(self, material: MaterialRecord) -> list[str]:
        risk_tags: list[str] = []
        if not material.name:
            risk_tags.append("missing_name")
        if not material.quantity:
            risk_tags.append("missing_quantity")
        return risk_tags

    def _first_value(self, record: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            value = record.get(key)
            if value not in (None, ""):
                return value
        return None

    def _first_text(self, record: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        value = self._first_value(record, keys)
        if value in (None, ""):
            return None
        text = str(value).strip()
        return text or None

    def _parse_quantity(self, value: Any, default: float = 1) -> float:
        if value in (None, ""):
            return float(default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)


class ExcelBomAggregator:
    """Aggregate BOM lines into a project-level summary."""

    def generate(self, result: ProjectResult) -> ProjectResult:
        summary_map: dict[tuple[str, str, str], MaterialRecord] = {}

        for bom_line in result.bom_lines:
            material = bom_line.material
            normalized_name = material.normalized_name or material.name
            normalized_spec = material.normalized_spec or material.spec or ""
            brand = material.brand or material.manufacturer or ""
            key = (normalized_name, normalized_spec, brand)

            summary = summary_map.get(key)
            if summary is None:
                summary = MaterialRecord(
                    name=material.name,
                    spec=material.spec,
                    unit=material.unit,
                    quantity=0.0,
                    brand=material.brand,
                    manufacturer=material.manufacturer,
                    normalized_name=normalized_name,
                    normalized_spec=normalized_spec,
                    confidence=material.confidence,
                    long_lead_time=material.long_lead_time,
                    remarks="aggregated from BOM lines",
                )
                summary_map[key] = summary

            summary.quantity += material.quantity
            summary.confidence = max(summary.confidence, material.confidence)
            summary.long_lead_time = summary.long_lead_time or material.long_lead_time

        result.summary = list(summary_map.values())
        return result
