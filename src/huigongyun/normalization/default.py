"""默认的物料归一化实现。

提供轻量、可解释的字符串清洗与别名映射。优先使用确定性映射，并在
可用时退回到 RapidFuzz 的模糊匹配以提升召回。
"""

from __future__ import annotations

import re

from ..models import BomLine, MaterialRecord, ProjectResult

try:
    from rapidfuzz import process, fuzz  # type: ignore
    _HAS_RAPIDFUZZ = True
except Exception:
    _HAS_RAPIDFUZZ = False


class DefaultMaterialNormalizer:
    """对物料名称、规格、品牌和单位进行轻量归一化。

    实现要点：
      - 对 `bom_lines` 与 `summary` 中的物料调用一致的清洗与别名映射；
      - 优先使用确定性别名映射（`MATERIAL_ALIASES` / `BRAND_ALIASES`）；
      - 在可用时使用 RapidFuzz 进行模糊匹配作为回退以提高召回。
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
        """对传入的 `ProjectResult` 就地归一化物料字段并返回相同对象。

        该函数会修改 `bom_lines` 中的 `MaterialRecord` 实例以及 `summary` 列表中的
        条目，确保后续聚合与定价阶段使用规范化后的字符串。
        """
        for bom_line in result.bom_lines:
            self._normalize_material(bom_line.material)

        for material in result.summary:
            self._normalize_material(material)

        return result

    def _normalize_material(self, material: MaterialRecord) -> None:
        """把单个 `MaterialRecord` 内的字段按规则清洗与映射。

        注意：该函数会更新 `material.normalized_name` 与 `material.normalized_spec`。
        """
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
        """把物料名称规范化到可比的字符串或别名。

        步骤：先做确定性的别名查找；若未命中且 RapidFuzz 可用，则做模糊匹配回退，
        匹配分数阈值为 85（可在未来参数化）。返回归一化后的名称字符串或 None。
        """
        if not value:
            return None
        normalized = self._normalize_text(value)
        # Exact alias match first
        if normalized in self.MATERIAL_ALIASES:
            return self.MATERIAL_ALIASES[normalized]

        # Fuzzy fallback using RapidFuzz if available
        if _HAS_RAPIDFUZZ:
            choices = list(self.MATERIAL_ALIASES.keys())
            match = process.extractOne(normalized, choices, scorer=fuzz.token_sort_ratio)
            if match:
                # match is typically (key, score, index)
                try:
                    key, score = match[0], match[1]
                except Exception:
                    key, score = match[0], 0
                try:
                    score = int(score)
                except Exception:
                    score = 0
                if score >= 85:
                    return self.MATERIAL_ALIASES.get(key, normalized)

        return normalized

    def _normalize_brand(self, value: str | None) -> str | None:
        if not value:
            return None
        normalized = self._normalize_text(value)
        if normalized in self.BRAND_ALIASES:
            return self.BRAND_ALIASES[normalized]

        if _HAS_RAPIDFUZZ:
            choices = list(self.BRAND_ALIASES.keys())
            match = process.extractOne(normalized, choices, scorer=fuzz.token_sort_ratio)
            if match:
                try:
                    key, score = match[0], match[1]
                except Exception:
                    key, score = match[0], 0
                try:
                    score = int(score)
                except Exception:
                    score = 0
                if score >= 80:
                    return self.BRAND_ALIASES.get(key, normalized)

        return normalized

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
