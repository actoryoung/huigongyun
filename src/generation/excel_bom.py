"""Excel 特定的 BOM 与机柜提取辅助工具。

该提取器期望 `ProjectDocument` 的 `metadata['sheets']` 字段包含结构化行
（由 Excel 解析器产生的中间表示）。提取器返回包含 `cabinets` 和
`bom_lines` 的 `ProjectResult`。
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from ..indexing.cabinets import CabinetIndexBuilder
from ..models import BomLine, MaterialRecord, ProjectDocument, ProjectResult, SourceRef


class ExcelCabinetAndBomExtractor:
    """Build cabinet and BOM records from parsed Excel sheet metadata."""

    CABINET_KEYS = ("柜号", "cabinet_no", "柜位", "柜体", "柜名", "设备位号")
    CABINET_TYPE_KEYS = ("柜型", "cabinet_type", "类型")
    RATED_CURRENT_KEYS = ("额定电流", "电流", "In", "额定电流(A)")
    QUANTITY_KEYS = ("数量", "qty", "数量(台)", "件数")
    MATERIAL_NAME_KEYS = ("物料名称", "元器件名称", "名称", "元件名称", "设备名称", "物料", "品名")
    SPEC_KEYS = ("规格型号", "型号及规格", "规格", "型号", "型号规格", "spec")
    UNIT_KEYS = ("单位", "unit")
    BRAND_KEYS = ("品牌", "厂家", "生产厂家", "manufacturer")
    LONG_LEAD_TIME_KEYS = ("长交期", "长交期", "长交期标记", "交期提示", "lead_time", "lead_time_flag")
    PRICE_SHEET_HINTS = ("价格表", "报价表", "单价表", "价格清单")

    def extract(self, document: ProjectDocument) -> ProjectResult:
        """从 `ProjectDocument` 的 `sheets` 中提取机柜与 BOM 行。

        算法要点：
          - 跳过价格表（`_is_price_sheet`）；
          - 遍历每个数据记录，尝试解析机柜号与物料名称；
          - 构造 `MaterialRecord` 并基于行信息生成 `BomLine`（包含来源与置信度）；
          - 使用 `CabinetIndexBuilder` 收集机柜级元数据并把其结果赋回 `ProjectResult`。
        """

        result = ProjectResult(project=document)
        sheets = document.metadata.get("sheets", []) if isinstance(document.metadata, dict) else []

        cabinet_result = CabinetIndexBuilder().build(document)
        bom_lines: list[BomLine] = []

        for sheet in sheets:
            sheet_name = str(sheet.get("name", "sheet"))
            if self._is_price_sheet(sheet_name, sheet):
                continue
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
                    long_lead_time=self._parse_bool(self._first_value(record, self.LONG_LEAD_TIME_KEYS)),
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

    def _parse_bool(self, value: Any) -> bool:
        if value in (None, ""):
            return False
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        return text in {"1", "true", "yes", "y", "是", "长交期", "有", "需确认", "x"}

    def _is_price_sheet(self, sheet_name: str, sheet: dict[str, Any]) -> bool:
        lower_name = sheet_name.lower()
        if any(hint in sheet_name for hint in self.PRICE_SHEET_HINTS):
            return True
        if any(hint in lower_name for hint in {"price", "pricing", "quote"}):
            return True
        headers = {str(header).strip() for header in sheet.get("headers", [])}
        return any(key in headers for key in {"单价", "unit_price", "价格"})


class ExcelBomAggregator:
    """Aggregate BOM lines into a project-level summary."""
    def generate(self, result: ProjectResult) -> ProjectResult:
        """将 `bom_lines` 聚合为 `summary` 列表。

        聚合逻辑：以 `(normalized_name, normalized_spec, brand)` 为 key 聚合，
        对数量求和，置信度取最大值，若任一组成项有 `long_lead_time`，则保留该标记。
        返回修改后的 `ProjectResult`（在 `summary` 字段写入聚合结果）。
        """

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
