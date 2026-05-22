from __future__ import annotations

import re

from ..models import BomLine, MaterialRecord, ProjectResult


class DefaultMaterialNormalizer:
    """Normalize material names, specs, brands, and units using a lightweight dictionary.

    The MVP keeps this layer deterministic and explainable. It intentionally leaves
    numeric sizing, cost rules, and deeper model-based matching as future hooks.
    """

    MATERIAL_ALIASES = {
        "断路器": "断路器",
        "空气开关": "断路器",
        "空开": "断路器",
        "塑壳断路器": "断路器",
        "接触器": "接触器",
        "交流接触器": "接触器",
        "热继电器": "热继电器",
        "热过载继电器": "热继电器",
        "按钮": "按钮",
        "指示灯": "指示灯",
    }

    BRAND_ALIASES = {
        "施耐德": "施耐德",
        "Schneider": "施耐德",
        "SCHNEIDER": "施耐德",
        "西门子": "西门子",
        "Siemens": "西门子",
        "SIEMENS": "西门子",
        "ABB": "ABB",
        "正泰": "正泰",
        "CHINT": "正泰",
    }

    UNIT_ALIASES = {
        "台": "台",
        "只": "只",
        "个": "个",
        "套": "套",
        "件": "件",
        "米": "米",
        "m": "米",
        "M": "米",
    }

    def normalize(self, result: ProjectResult) -> ProjectResult:
        for bom_line in result.bom_lines:
            self._normalize_material(bom_line.material)

        for material in result.summary:
            self._normalize_material(material)

        return result

    def _normalize_material(self, material: MaterialRecord) -> None:
        material.name = self._normalize_text(material.name)
        material.spec = self._normalize_spec(material.spec)
        material.unit = self._normalize_unit(material.unit)
        material.brand = self._normalize_brand(material.brand or material.manufacturer)
        material.manufacturer = material.brand or material.manufacturer
        material.normalized_name = self._normalize_material_name(material.name)
        material.normalized_spec = self._normalize_spec(material.spec)

    def _normalize_text(self, value: str | None) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        text = text.replace("\u3000", " ")
        text = re.sub(r"\s+", " ", text)
        return text

    def _normalize_material_name(self, value: str | None) -> str | None:
        if not value:
            return None
        normalized = self._normalize_text(value)
        return self.MATERIAL_ALIASES.get(normalized, normalized)

    def _normalize_brand(self, value: str | None) -> str | None:
        if not value:
            return None
        normalized = self._normalize_text(value)
        return self.BRAND_ALIASES.get(normalized, normalized)

    def _normalize_unit(self, value: str | None) -> str | None:
        if not value:
            return None
        normalized = self._normalize_text(value)
        return self.UNIT_ALIASES.get(normalized, normalized)

    def _normalize_spec(self, value: str | None) -> str | None:
        if not value:
            return None
        normalized = self._normalize_text(value)
        normalized = normalized.replace("×", "x")
        normalized = normalized.replace("＊", "*")
        normalized = re.sub(r"\s*([xX*/-])\s*", r"\1", normalized)
        normalized = re.sub(r"\s+", "", normalized)
        return normalized or None
