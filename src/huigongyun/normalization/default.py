"""默认的物料归一化实现。

提供轻量、可解释的字符串清洗与别名映射。优先使用确定性映射（从外部
JSON 词典加载），并在可用时退回到 RapidFuzz 的模糊匹配以提升召回。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..models import MaterialRecord, ProjectResult

try:
    from rapidfuzz import process, fuzz  # type: ignore
    _HAS_RAPIDFUZZ = True
except Exception:
    _HAS_RAPIDFUZZ = False


def _load_dictionaries() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """从 JSON 词典文件加载物料、品牌、单位别名映射。

    返回三个别名映射字典：(material_map, brand_map, unit_map)。
    每个字典将变体名称映射到规范名称：{variant: canonical}。
    """
    dict_path = Path(__file__).parent / "dictionaries" / "materials.json"

    # 内置回退词典（当 JSON 文件不可用时使用）
    fallback_materials = {
        "断路器": "断路器", "空气开关": "断路器", "空开": "断路器",
        "塑壳断路器": "断路器", "框架断路器本体": "框架断路器",
        "接触器": "接触器", "交流接触器": "接触器",
        "热继电器": "热继电器", "热过载继电器": "热继电器", "热继": "热继电器",
        "浪涌保护器": "浪涌保护器", "SPD": "浪涌保护器",
        "双电源开关ATMT": "双电源开关", "双电源开关WTS": "双电源开关",
        "SPD断路器": "SPD断路器", "浪涌后备保护断路器": "SPD断路器",
        "断路器脱扣单元": "断路器脱扣单元", "脱扣单元": "断路器脱扣单元",
        "测量电流互感器": "测量电流互感器", "CT": "测量电流互感器",
        "多功能表": "多功能表", "电力仪表": "多功能表",
        "熔断器隔离开关": "熔断器隔离开关", "刀熔开关": "熔断器隔离开关",
        "晶闸管投切开关": "晶闸管投切开关", "投切开关": "晶闸管投切开关",
        "温湿度控制器": "温湿度控制器", "温控器": "温湿度控制器",
        "SVG": "SVG", "静止无功发生器": "SVG",
        "主母线": "主母线", "母线": "主母线", "铜排": "主母线",
        "柜体": "柜体", "机柜": "柜体",
        "SP元件": "SP元件", "智能网关": "SP元件",
        "电抗器": "电抗器", "滤波电抗器": "电抗器",
        "电容器": "电容器", "电力电容": "电容器",
        "通讯模块": "通讯模块", "通信模块": "通讯模块",
        "熔断器": "熔断器", "FUSE": "熔断器",
        "隔离开关": "隔离开关",
        "接触器": "接触器",
        "微型断路器": "微型断路器", "MCB": "微型断路器",
    }
    fallback_brands = {
        "施耐德": "施耐德", "Schneider": "施耐德", "SCHNEIDER": "施耐德",
        "施耐德电气": "施耐德", "施耐德成套": "施耐德",
        "西门子": "西门子", "Siemens": "西门子", "SIEMENS": "西门子",
        "ABB": "ABB", "abb": "ABB",
        "正泰": "正泰", "CHINT": "正泰",
        "德力西": "德力西", "Delixi": "德力西",
        "良信": "良信", "Nader": "良信",
        "国产": "国产", "国产优质": "国产", "国优产品": "国产",
        "茗熔": "茗熔", "茗熔电器": "茗熔",
        "甲供": "甲供", "甲方供货": "甲供", "业主供货": "甲供",
        "施耐德万高": "施耐德万高",
    }
    fallback_units = {
        "台": "台", "set": "台", "面": "台",
        "只": "只", "个": "只", "piece": "只",
        "套": "套", "组": "套",
        "米": "米", "m": "米", "M": "米",
        "件": "件", "条": "件", "根": "件",
    }

    try:
        if not dict_path.exists():
            return fallback_materials, fallback_brands, fallback_units

        with open(dict_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return fallback_materials, fallback_brands, fallback_units

    # Build material alias map from JSON
    mat_map: dict[str, str] = {}
    for canonical, aliases in data.get("material_aliases", {}).items():
        for alias in aliases:
            mat_map[alias] = canonical
        if canonical not in mat_map:
            mat_map[canonical] = canonical

    # Build brand alias map
    brand_map: dict[str, str] = {}
    for canonical, aliases in data.get("brand_aliases", {}).items():
        for alias in aliases:
            brand_map[alias] = canonical
        if canonical not in brand_map:
            brand_map[canonical] = canonical

    # Build unit alias map
    unit_map: dict[str, str] = {}
    for canonical, aliases in data.get("unit_aliases", {}).items():
        for alias in aliases:
            unit_map[alias] = canonical
        if canonical not in unit_map:
            unit_map[canonical] = canonical

    # Merge fallback entries (only where not already defined in JSON)
    for k, v in fallback_materials.items():
        if k not in mat_map:
            mat_map[k] = v
    for k, v in fallback_brands.items():
        if k not in brand_map:
            brand_map[k] = v
    for k, v in fallback_units.items():
        if k not in unit_map:
            unit_map[k] = v
    return mat_map, brand_map, unit_map


# 模块级加载词典
_MATERIAL_ALIASES, _BRAND_ALIASES, _UNIT_ALIASES = _load_dictionaries()


def _load_category_default_brands() -> dict[str, list[str]]:
    """从 JSON 词典加载物料类别→国产品牌默认映射。

    返回 {canonical_category: [首选品牌, 备选1, ...]}。
    JSON 中已定义的覆盖内置回退；未定义的保留回退值。
    """
    dict_path = Path(__file__).parent / "dictionaries" / "materials.json"

    # 内置回退
    fallback_categories: dict[str, list[str]] = {
        "框架断路器": ["常熟", "正泰", "人民电器"],
        "塑壳断路器": ["常熟", "正泰", "德力西"],
        "微型断路器": ["正泰", "德力西", "天正"],
        "SPD断路器": ["正泰", "天正"],
        "断路器脱扣单元": ["正泰", "常熟"],
        "双电源开关": ["正泰", "德力西"],
        "浪涌保护器": ["正泰", "良信"],
        "接触器": ["正泰", "德力西", "天正"],
        "热继电器": ["正泰", "天正"],
        "熔断器": ["茗熔", "正泰"],
        "熔断器隔离开关": ["茗熔", "正泰"],
        "隔离开关": ["正泰", "德力西"],
        "测量电流互感器": ["正泰", "德力西"],
        "多功能表": ["正泰", "天正"],
        "温湿度控制器": ["正泰"],
        "主母线": ["国产"],
        "柜体": ["国产"],
        "SVG": ["正泰"],
        "电抗器": ["正泰", "德力西"],
        "电容器": ["正泰", "德力西"],
        "晶闸管投切开关": ["正泰"],
        "通讯模块": ["正泰"],
        "SP元件": ["正泰"],
        "其他": ["国产"],
    }

    try:
        if not dict_path.exists():
            return fallback_categories
        with open(dict_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        json_categories = data.get("material_category_default_brands", {})
        if not isinstance(json_categories, dict):
            return fallback_categories
        # JSON 覆盖回退
        merged = dict(fallback_categories)
        merged.update(json_categories)
        return merged
    except Exception:
        return fallback_categories


_MATERIAL_CATEGORY_DEFAULT_BRANDS = _load_category_default_brands()

# "国产"类占位符——触发类别推断的信号，不是品牌名
_TRIGGER_BRANDS_FOR_INFERENCE = {"国产", "甲供"}


class DefaultMaterialNormalizer:
    """对物料名称、规格、品牌和单位进行轻量归一化。

    实现要点：
      - 从外部 JSON 词典加载别名映射（dictionaries/materials.json）；
      - 对 `bom_lines` 与 `summary` 中的物料调用一致的清洗与别名映射；
      - 优先使用确定性别名映射，在可用时使用 RapidFuzz 进行模糊匹配作为回退。
    """

    @property
    def MATERIAL_ALIASES(self) -> dict[str, str]:
        return _MATERIAL_ALIASES

    @property
    def BRAND_ALIASES(self) -> dict[str, str]:
        return _BRAND_ALIASES

    @property
    def UNIT_ALIASES(self) -> dict[str, str]:
        return _UNIT_ALIASES

    @property
    def MATERIAL_CATEGORY_DEFAULT_BRANDS(self) -> dict[str, list[str]]:
        return _MATERIAL_CATEGORY_DEFAULT_BRANDS

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
        """对单个 ``MaterialRecord`` 进行清洗与别名映射。

        - ``name`` / ``spec`` / ``unit`` 做基本清理
        - ``normalized_name`` / ``normalized_spec`` 做别名映射（非破坏性）
        - ``brand`` 保留原始值；``normalized_brand`` 走完整回退链
        - ``brand_source`` 标记品牌来源（explicit / inferred / pending）
        """
        material.name = self._normalize_text(material.name)
        material.spec = self._normalize_spec(material.spec)
        material.unit = self._normalize_unit(material.unit)

        # 品牌：原始值只做基本清理（不再覆写）
        raw_brand = self._normalize_text(material.brand) or None

        # manufacturer 作为备选原始值
        raw_manufacturer = self._normalize_text(material.manufacturer) or None

        # 归一化品牌：完整回退链
        material.normalized_brand, material.brand_source = (
            self._normalize_brand_with_fallback(
                raw_brand or raw_manufacturer,
                normalized_name=material.normalized_name or material.name,
            )
        )

        # manufacturer 同步到归一化结果
        material.manufacturer = raw_manufacturer or material.normalized_brand

        # 名称/规格归一化（非破坏性）
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

    def _normalize_brand_with_fallback(
        self,
        value: str | None,
        normalized_name: str = "",
    ) -> tuple[str | None, str]:
        """品牌回退链，返回 ``(normalized_brand, brand_source)``。

        回退顺序：
        1. 明确品牌（非"国产"/"甲供"等触发器）→ 别名映射→RapidFuzz
           → 成功返回 (规范名, "explicit")
        2. "国产"类占位符/空值 → 类别推断→具体国产品牌
           → 成功返回 (正泰/常熟/茗熔, "inferred")
        3. 类别推断失败 → (None, "pending")
        4. 品牌有值但全链路无法识别 → (None, "pending")
        """
        # 空值直接走推断
        if not value:
            inferred = self._infer_brand_from_category(normalized_name)
            if inferred and inferred not in _TRIGGER_BRANDS_FOR_INFERENCE:
                return inferred, "inferred"
            return None, "pending"

        # Step 1: 别名映射
        if value in self.BRAND_ALIASES:
            canonical = self.BRAND_ALIASES[value]
            # "国产"在别名字典中映射到自身——这是推断触发器，不是目标品牌
            if canonical in _TRIGGER_BRANDS_FOR_INFERENCE:
                inferred = self._infer_brand_from_category(normalized_name)
                if inferred and inferred not in _TRIGGER_BRANDS_FOR_INFERENCE:
                    return inferred, "inferred"
                return None, "pending"
            return canonical, "explicit"

        # Step 2: RapidFuzz 模糊回退
        if _HAS_RAPIDFUZZ:
            choices = list(self.BRAND_ALIASES.keys())
            match = process.extractOne(value, choices, scorer=fuzz.token_sort_ratio)
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
                    canonical = self.BRAND_ALIASES.get(key, value)
                    if canonical in _TRIGGER_BRANDS_FOR_INFERENCE:
                        inferred = self._infer_brand_from_category(normalized_name)
                        if inferred and inferred not in _TRIGGER_BRANDS_FOR_INFERENCE:
                            return inferred, "inferred"
                        return None, "pending"
                    return canonical, "explicit"

        # Step 3: 值有但无法识别 → 不做强制推断，标记 pending
        return None, "pending"

    def _infer_brand_from_category(self, normalized_name: str) -> str | None:
        """根据归一化物料名称推断推荐国产品牌。

        查找逻辑：遍历 MATERIAL_CATEGORY_DEFAULT_BRANDS，
        用类别变体（规范名+别名）对物料名称做关键词匹配。
        返回第一个匹配类别的首选品牌，或 None。
        """
        if not normalized_name:
            return None

        name_lower = normalized_name.lower()
        for canonical_category, brands in self.MATERIAL_CATEGORY_DEFAULT_BRANDS.items():
            if canonical_category.startswith("_"):
                continue  # 跳过元数据条目
            variants = self._get_category_variants(canonical_category)
            for variant in variants:
                if variant.lower() in name_lower:
                    return brands[0]  # 首选品牌

        return None

    def _get_category_variants(self, canonical_category: str) -> list[str]:
        """获取某物料类别的全部变体（含规范名本身）。

        利用 MATERIAL_ALIASES 反向查找所有映射到此规范名的变体。
        """
        variants = [canonical_category]
        for alias, canonical in self.MATERIAL_ALIASES.items():
            if canonical == canonical_category and alias != canonical_category:
                variants.append(alias)
        return variants

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
