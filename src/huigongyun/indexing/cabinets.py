from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import CabinetRecord, ProjectDocument, SourceRef


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

    CABINET_KEYS = ("柜号", "cabinet_no", "柜位", "柜体", "柜名")
    CABINET_TYPE_KEYS = ("柜型", "cabinet_type", "类型")
    RATED_CURRENT_KEYS = ("额定电流", "电流", "In", "额定电流(A)")
    DIMENSIONS_KEYS = ("外形尺寸", "尺寸", "柜体尺寸", "dimensions")
    WIDTH_KEYS = ("宽", "宽度", "柜宽", "width")
    HEIGHT_KEYS = ("高", "高度", "柜高", "height")
    DEPTH_KEYS = ("深", "深度", "柜深", "depth")
    CIRCUIT_COUNT_KEYS = ("回路数", "回路", "circuits", "circuit_count")
    INBOUND_OUTBOUND_KEYS = ("进出线方式", "进线方式", "出线方式", "进出线", "inbound_outbound")
    GROUNDING_MODE_KEYS = ("接地方式", "grounding_mode")
    QUANTITY_KEYS = ("数量", "qty", "数量(台)", "件数")

    def build(self, document: ProjectDocument) -> CabinetIndexResult:
        result = CabinetIndexResult()
        sheets = document.metadata.get("sheets", []) if isinstance(document.metadata, dict) else []

        cabinet_index: dict[str, CabinetRecord] = {}

        for sheet in sheets:
            sheet_name = str(sheet.get("name", "sheet"))
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

                cabinet = cabinet_index.get(cabinet_no)
                if cabinet is None:
                    cabinet = CabinetRecord(
                        cabinet_no=cabinet_no,
                        cabinet_type=self._first_text(record, self.CABINET_TYPE_KEYS),
                        rated_current=self._first_text(record, self.RATED_CURRENT_KEYS),
                        dimensions=self._first_dimension_text(record),
                        circuit_count=self._parse_optional_int(self._first_value(record, self.CIRCUIT_COUNT_KEYS)),
                        quantity=self._parse_quantity(self._first_value(record, self.QUANTITY_KEYS), default=1),
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
