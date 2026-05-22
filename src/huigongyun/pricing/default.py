from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from ..models import ProjectResult, QuoteLine


@dataclass(slots=True)
class PriceEntry:
    unit_price: float
    source: str
    confidence: float = 0.7


class DefaultQuoteGenerator:
    """Generate a minimal quote layer from BOM lines and optional price tables."""

    PRICE_SHEET_NAMES = {"价格表", "报价表", "单价表", "价格清单"}
    PRICE_NAME_KEYS = ("物料名称", "名称", "品名", "material_name")
    PRICE_SPEC_KEYS = ("规格型号", "规格", "型号", "spec")
    PRICE_BRAND_KEYS = ("品牌", "厂家", "生产厂家", "manufacturer")
    PRICE_VALUE_KEYS = ("单价", "价格", "含税单价", "unit_price")

    def generate(self, result: ProjectResult) -> ProjectResult:
        price_table = self._build_price_table(result)
        quote_lines: list[QuoteLine] = []
        cabinet_totals: dict[str, float] = defaultdict(float)
        project_total = 0.0
        missing_price_count = 0

        for bom_line in result.bom_lines:
            material = bom_line.material
            entry = self._resolve_price(material.name, material.spec, material.brand or material.manufacturer, price_table)

            unit_price = entry.unit_price if entry else None
            subtotal = round(unit_price * material.quantity, 2) if unit_price is not None else None
            price_missing = unit_price is None

            if subtotal is not None:
                cabinet_totals[bom_line.cabinet_no] += subtotal
                project_total += subtotal
            else:
                missing_price_count += 1

            material.unit_price = unit_price
            material.price_source = entry.source if entry else None
            material.price_confidence = entry.confidence if entry else 0.0
            material.subtotal = subtotal
            material.price_missing = price_missing

            quote_lines.append(
                QuoteLine(
                    cabinet_no=bom_line.cabinet_no,
                    material_name=material.name,
                    spec=material.spec,
                    unit=material.unit,
                    quantity=material.quantity,
                    brand=material.brand or material.manufacturer,
                    unit_price=unit_price,
                    subtotal=subtotal,
                    price_source=material.price_source or "missing",
                    price_confidence=material.price_confidence,
                    price_missing=price_missing,
                    remarks=material.remarks,
                )
            )

        result.quote_lines = quote_lines
        result.quote_totals = {
            "project_total": round(project_total, 2),
            "cabinet_totals": {key: round(value, 2) for key, value in cabinet_totals.items()},
            "missing_price_count": missing_price_count,
            "price_table_size": len(price_table),
        }
        return result

    def _build_price_table(self, result: ProjectResult) -> dict[tuple[str, str, str], PriceEntry]:
        table: dict[tuple[str, str, str], PriceEntry] = {}
        sheets = result.project.metadata.get("sheets", []) if isinstance(result.project.metadata, dict) else []

        for sheet in sheets:
            sheet_name = str(sheet.get("name", ""))
            if not self._is_price_sheet(sheet_name, sheet):
                continue

            headers = [str(header).strip() for header in sheet.get("headers", [])]
            for record in sheet.get("records", []) or []:
                if not isinstance(record, dict):
                    continue
                name = self._first_text(record, self.PRICE_NAME_KEYS, headers)
                if not name:
                    continue
                unit_price_value = self._first_value(record, self.PRICE_VALUE_KEYS, headers)
                unit_price = self._parse_float(unit_price_value)
                if unit_price is None:
                    continue
                spec = self._normalize_text(self._first_text(record, self.PRICE_SPEC_KEYS, headers))
                brand = self._normalize_text(self._first_text(record, self.PRICE_BRAND_KEYS, headers))
                table[self._price_key(name, spec, brand)] = PriceEntry(
                    unit_price=unit_price,
                    source=f"sheet:{sheet_name}:{record.get('_row_no', '')}",
                    confidence=0.8,
                )

        metadata_prices = result.project.metadata.get("price_table") if isinstance(result.project.metadata, dict) else None
        if isinstance(metadata_prices, list):
            for row in metadata_prices:
                if not isinstance(row, dict):
                    continue
                name = self._normalize_text(str(row.get("name") or row.get("物料名称") or ""))
                if not name:
                    continue
                unit_price = self._parse_float(row.get("unit_price") or row.get("单价"))
                if unit_price is None:
                    continue
                spec = self._normalize_text(str(row.get("spec") or row.get("规格型号") or ""))
                brand = self._normalize_text(str(row.get("brand") or row.get("品牌") or ""))
                table[self._price_key(name, spec, brand)] = PriceEntry(
                    unit_price=unit_price,
                    source="metadata:price_table",
                    confidence=0.9,
                )

        return table

    def _resolve_price(
        self,
        name: str | None,
        spec: str | None,
        brand: str | None,
        price_table: dict[tuple[str, str, str], PriceEntry],
    ) -> PriceEntry | None:
        candidates = [
            self._price_key(name, spec, brand),
            self._price_key(name, spec, None),
            self._price_key(name, None, None),
        ]
        for key in candidates:
            entry = price_table.get(key)
            if entry is not None:
                return entry
        return None

    def _is_price_sheet(self, sheet_name: str, sheet: dict[str, Any]) -> bool:
        if sheet_name in self.PRICE_SHEET_NAMES:
            return True
        lower_name = sheet_name.lower()
        if any(hint in lower_name for hint in {"price", "pricing", "quote"}):
            return True
        headers = {str(header).strip() for header in sheet.get("headers", [])}
        return any(key in headers for key in {"单价", "unit_price", "价格"})

    def _price_key(self, name: str | None, spec: str | None, brand: str | None) -> tuple[str, str, str]:
        return (self._normalize_text(name), self._normalize_spec(spec), self._normalize_text(brand))

    def _first_value(self, record: dict[str, Any], keys: tuple[str, ...], headers: list[str]) -> Any:
        for header in headers:
            if header in keys:
                value = record.get(header)
                if value not in (None, ""):
                    return value
        for key in keys:
            value = record.get(key)
            if value not in (None, ""):
                return value
        return None

    def _first_text(self, record: dict[str, Any], keys: tuple[str, ...], headers: list[str]) -> str | None:
        value = self._first_value(record, keys, headers)
        if value in (None, ""):
            return None
        text = self._normalize_text(str(value))
        return text or None

    def _parse_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _normalize_text(self, value: str | None) -> str:
        if value is None:
            return ""
        text = str(value).strip().replace("\u3000", " ")
        text = text.replace("×", "x")
        text = text.replace("＊", "*")
        return " ".join(text.split())

    def _normalize_spec(self, value: str | None) -> str:
        if value is None:
            return ""
        normalized = self._normalize_text(value)
        return normalized.replace(" ", "")
