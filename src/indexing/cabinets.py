"""从解析后的电子表格记录构建机柜索引的辅助工具。

`CabinetIndexBuilder` 检查表格层级的记录（由 Excel 解析器产生的中间
表示），并聚合机柜级元数据及其来源信息。返回 `CabinetIndexResult`，
其中包含解析出的机柜、未解析的行与便于追溯的简短说明。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import CabinetRecord, ProjectDocument, SourceRef


def _first_non_none(*values: Any) -> Any:
    """Return the first non-None, non-empty value from the given arguments."""
    for v in values:
        if v is not None and v != "":
            return v
    return None


def _parse_float_or_default(value: Any, default: float) -> float:
    """Parse a value as float, returning default on failure."""
    if value in (None, ""):
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


@dataclass(slots=True)
class CabinetIndexResult:
    cabinets: list[CabinetRecord] = field(default_factory=list)
    unresolved_rows: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class CabinetIndexBuilder:
    """Build a cabinet list from parsed Excel records.

    The builder keeps a placeholder path for unresolved cabinet numbers so later
    stages can still carry explicit markers without guessing numeric values.
    """

    CABINET_KEYS = ("柜号", "cabinet_no", "柜位", "柜体", "柜名", "设备位号")
    CABINET_TYPE_KEYS = ("柜型", "cabinet_type", "类型")
    # 用于判断一行是否为"空柜位"（有位号但无物料数据）
    _CONTENT_KEYS = ("物料名称", "元器件名称", "名称", "元件名称", "设备名称", "物料", "品名")
    RATED_CURRENT_KEYS = ("额定电流", "电流", "In", "额定电流(A)")
    PRICE_SHEET_HINTS = ("价格表", "报价表", "单价表", "价格清单")
    DIMENSIONS_KEYS = ("外形尺寸", "尺寸", "柜体尺寸", "dimensions")
    WIDTH_KEYS = ("宽", "宽度", "柜宽", "width")
    HEIGHT_KEYS = ("高", "高度", "柜高", "height")
    DEPTH_KEYS = ("深", "深度", "柜深", "depth")
    CIRCUIT_COUNT_KEYS = ("回路数", "回路", "circuits", "circuit_count")
    INBOUND_OUTBOUND_KEYS = ("进出线方式", "进线方式", "出线方式", "进出线", "inbound_outbound")
    GROUNDING_MODE_KEYS = ("接地方式", "grounding_mode")
    QUANTITY_KEYS = ("数量", "qty", "数量(台)", "件数")

    def build(self, document: ProjectDocument) -> CabinetIndexResult:
        """从 `ProjectDocument` 的 `sheets` 构建机柜索引。

        行为概要：遍历每个 sheet（跳过价格表），根据行内机柜相关字段聚合
        `CabinetRecord`，并收集无法解析的行到 `unresolved_rows` 以便后续人工
        介入或规则改进。
        """

        result = CabinetIndexResult()
        sheets = document.metadata.get("sheets", []) if isinstance(document.metadata, dict) else []

        cabinet_index: dict[str, CabinetRecord] = {}

        for sheet in sheets:
            sheet_name = str(sheet.get("name", "sheet"))
            if self._is_price_sheet(sheet_name, sheet):
                continue

            # Pre-header metadata from the sheet (cabinet-level info like 柜型/外形尺寸)
            pre_meta: dict[str, Any] = sheet.get("pre_header_meta", {}) if isinstance(sheet, dict) else {}

            for record in sheet.get("records", []):
                if not isinstance(record, dict):
                    continue

                row_no = int(record.get("_row_no", 0) or 0)
                cabinet_no = self._first_text(record, self.CABINET_KEYS) or "UNASSIGNED"
                if cabinet_no == "UNASSIGNED":
                    result.unresolved_rows.append(
                        {
                            "sheet_name": sheet_name,
                            "row_no": row_no,
                            "reason": "missing_cabinet_no",
                            "marker": "cabinet_no:UNASSIGNED",
                        }
                    )

                # 跳过空模板行（有位号但无任何物料数据）
                if cabinet_no != "UNASSIGNED" and not self._first_text(record, self._CONTENT_KEYS):
                    continue

                cabinet = cabinet_index.get(cabinet_no)
                if cabinet is None:
                    pre_qty = pre_meta.get("quantity", 1)
                    qty_val = _first_non_none(self._first_value(record, self.QUANTITY_KEYS), pre_qty)
                    cabinet = CabinetRecord(
                        cabinet_no=cabinet_no,
                        cabinet_type=_first_non_none(self._first_text(record, self.CABINET_TYPE_KEYS), pre_meta.get("cabinet_type")),
                        rated_current=self._first_text(record, self.RATED_CURRENT_KEYS),
                        dimensions=_first_non_none(self._first_dimension_text(record), pre_meta.get("dimensions")),
                        circuit_count=self._parse_optional_int(self._first_value(record, self.CIRCUIT_COUNT_KEYS)),
                        quantity=_parse_float_or_default(qty_val, default=1),
                        inbound_outbound=self._first_text(record, self.INBOUND_OUTBOUND_KEYS),
                        grounding_mode=self._first_text(record, self.GROUNDING_MODE_KEYS),
                        confidence=0.6,
                        remarks=f"parsed from {sheet_name}",
                    )
                    cabinet.sources.append(self._build_source(document, sheet_name, row_no, record))
                    cabinet_index[cabinet_no] = cabinet
                else:
                    self._merge_fields(cabinet, record, document, sheet_name, row_no)

        result.cabinets = list(cabinet_index.values())
        if result.unresolved_rows:
            result.notes.append("unresolved_cabinet_numbers_present")
        return result

    def _merge_fields(
        self,
        cabinet: CabinetRecord,
        record: dict[str, Any],
        document: ProjectDocument,
        sheet_name: str,
        row_no: int,
    ) -> None:
        """将新的行信息合并到已存在的 `CabinetRecord`。

        合并策略：仅当目标字段为空或不可信时才更新，保留来源追溯并提高置信度。
        """
        if not cabinet.cabinet_type:
            cabinet.cabinet_type = self._first_text(record, self.CABINET_TYPE_KEYS)
        if not cabinet.rated_current:
            cabinet.rated_current = self._first_text(record, self.RATED_CURRENT_KEYS)
        if not cabinet.dimensions:
            cabinet.dimensions = self._first_dimension_text(record)
        if cabinet.circuit_count is None:
            cabinet.circuit_count = self._parse_optional_int(self._first_value(record, self.CIRCUIT_COUNT_KEYS))
        if cabinet.quantity <= 0:
            cabinet.quantity = self._parse_quantity(self._first_value(record, self.QUANTITY_KEYS), default=1)
        if not cabinet.inbound_outbound:
            cabinet.inbound_outbound = self._first_text(record, self.INBOUND_OUTBOUND_KEYS)
        if not cabinet.grounding_mode:
            cabinet.grounding_mode = self._first_text(record, self.GROUNDING_MODE_KEYS)
        cabinet.sources.append(self._build_source(document, sheet_name, row_no, record))
        cabinet.confidence = max(cabinet.confidence, 0.6)

    def _build_source(self, document: ProjectDocument, sheet_name: str, row_no: int, record: dict[str, Any]) -> SourceRef:
        file_name = Path(document.files[0]).name if document.files else document.project_name
        excerpt = self._first_text(record, self.CABINET_KEYS) or self._first_text(record, self.CABINET_TYPE_KEYS)
        return SourceRef(
            file_name=file_name,
            file_type="excel",
            sheet_name=sheet_name,
            row_no=row_no,
            excerpt=excerpt,
            confidence=0.7,
        )

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

    def _first_dimension_text(self, record: dict[str, Any]) -> str | None:
        explicit = self._first_text(record, self.DIMENSIONS_KEYS)
        if explicit:
            return explicit

        width = self._first_text(record, self.WIDTH_KEYS)
        height = self._first_text(record, self.HEIGHT_KEYS)
        depth = self._first_text(record, self.DEPTH_KEYS)
        parts = [part for part in (width, height, depth) if part]
        if len(parts) == 3:
            return "×".join(parts)
        return None

    def _parse_optional_int(self, value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            parsed = int(float(value))
        except (TypeError, ValueError):
            return None
        return parsed

    def _parse_quantity(self, value: Any, default: float = 1) -> float:
        if value in (None, ""):
            return float(default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def _is_price_sheet(self, sheet_name: str, sheet: dict[str, Any]) -> bool:
        lower_name = sheet_name.lower()
        if any(hint in sheet_name for hint in self.PRICE_SHEET_HINTS):
            return True
        if any(hint in lower_name for hint in {"price", "pricing", "quote"}):
            return True
        headers = {str(header).strip() for header in sheet.get("headers", [])}
        return any(key in headers for key in {"单价", "unit_price", "价格"})
