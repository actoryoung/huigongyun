"""从技术说明/配置文档中抽取结构化约束。

`TechnicalConstraintExtractor` 从 Word 解析器产出的段落文本中识别并抽取
技术约束（品牌要求、柜型配置、防护等级、接地方式、进出线方式等），
返回结构化的约束字典供校验引擎和柜体/BOM 生成使用。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ExtractedConstraint:
    """从文档中抽取的单条技术约束。"""

    constraint_type: str  # brand, cabinet_type, ip_rating, grounding, etc.
    value: str
    source_text: str  # 原始匹配文本片段
    confidence: float = 0.8


@dataclass(slots=True)
class ConstraintResult:
    """从一份文档中抽取的所有约束集合。"""

    constraints: list[ExtractedConstraint] = field(default_factory=list)
    cabinet_type: str | None = None
    cabinet_count: int | None = None
    ip_rating: str | None = None
    dimensions: str | None = None
    grounding_mode: str | None = None
    inbound_outbound: str | None = None
    maintenance: str | None = None
    busbar_spec: str | None = None
    frame_breaker: str | None = None
    mccb: str | None = None
    meter_incomer: str | None = None
    meter_feeder: str | None = None
    reactive_comp: str | None = None
    surge_protection: str | None = None
    ats_config: str | None = None
    generator_switch: str | None = None
    specified_brands: list[str] = field(default_factory=list)


class TechnicalConstraintExtractor:
    """从技术说明文本中抽取结构化约束。

    使用正则模式 + 关键词词典匹配，逐段扫描并聚合结果。
    所有抽取结果都保留原始文本片段以便追溯。
    """

    # 正则模式：每个模式匹配一种约束类型
    PATTERNS: list[tuple[str, str]] = [
        # (constraint_type, regex_pattern)
        ("cabinet_type", r"柜[体型]采[用购](?:[^，,；;。.\n]+)"),
        ("cabinet_type", r"柜[体型]配置[：:]\s*(.+?)(?:[；;，,]|$)"),
        ("dimensions", r"柜体尺寸[：:]\s*(.+?)(?:[；;]|$)"),
        ("dimensions", r"高度(\d{3,4})\s*mm.*?深度(\d{3,4})\s*mm"),
        ("ip_rating", r"防护等[级][：:]*\s*(IP\d+X?)"),
        ("ip_rating", r"(IP\d{1,2}X?)"),
        ("grounding", r"接[地零]方[式][：:]*\s*(TN[-\s]?[CSS]|TT|IT)"),
        ("grounding", r"(TN[-\s]?[CSS]|TT|IT)\s*系统"),
        ("grounding", r"接[地零][：:]*\s*(TN[-\s]?[CSS]|TT|IT)"),
        ("inbound_outbound", r"进出[线缆].*?方式[：:]*\s*(.+?)(?:[；;，,]|$)"),
        ("inbound_outbound", r"(上进[下出侧]|下进[上出]|母[线排].*?进)"),
        ("busbar", r"铜排.*?规格[：:]*\s*(.+?)(?:[；;]|$)"),
        ("busbar", r"母线.*?规格[：:]*\s*(.+?)(?:[；;]|$)"),
        ("frame_breaker", r"框架.*?断路器.*?[：:]*\s*(.+?)(?:[；;]|$)"),
        ("mccb", r"塑壳.*?断路器.*?[：:]*\s*(.+?)(?:[；;]|$)"),
        ("meter", r"仪表.*?[：:]*\s*(.+?)(?:[；;]|$)"),
        ("reactive_comp", r"(?:无功|补偿|SVG).*?[：:]*\s*(.+?)(?:[；;]|$)"),
        ("surge", r"(?:浪涌|SPD).*?[：:]*\s*(.+?)(?:[；;]|$)"),
        ("ats", r"(?:进线.*?母联|ATMT|ATS|切换).*?[：:]*\s*(.+?)(?:[；;]|$)"),
        ("generator", r"(?:市电.*?柴发|发电机.*?切换|WTS).*?[：:]*\s*(.+?)(?:[；;]|$)"),
        ("brand", r"(?:采用|指定|选用)([^\s，,；;。.\n]{2,10}(?:系列|产品|品牌))"),
        ("brand", r"(施耐德|ABB|西门子|正泰|德力西|良信|天正|常熟|人民电器)"),
    ]

    # 品牌关键词（用于从品牌相关文本中抽取）
    BRAND_KEYWORDS = [
        "施耐德", "Schneider", "ABB", "西门子", "Siemens",
        "正泰", "CHINT", "德力西", "Delixi", "良信", "Nader",
        "天正", "常熟", "人民电器",
    ]

    def extract(self, paragraphs: list[str]) -> ConstraintResult:
        """从段落列表中抽取所有约束。

        Args:
            paragraphs: 从 Word 文档中提取的段落文本列表。

        Returns:
            包含所有抽取出的约束的 `ConstraintResult`。
        """
        result = ConstraintResult()

        for para in paragraphs:
            if not para or not para.strip():
                continue
            text = para.strip()
            self._extract_from_text(text, result)

        # Post-process: collect specified brands
        result.specified_brands = list(dict.fromkeys(
            c.value for c in result.constraints if c.constraint_type == "brand"
        ))

        return result

    def _extract_from_text(self, text: str, result: ConstraintResult) -> None:
        """对单段文本应用所有模式并聚合结果。"""
        for ctype, pattern in self.PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                value = match if isinstance(match, str) else match[0]
                value = value.strip().rstrip("；;，,。.")
                if not value or len(value) < 2:
                    continue
                constraint = ExtractedConstraint(
                    constraint_type=ctype,
                    value=value,
                    source_text=text[:120],
                )
                result.constraints.append(constraint)
                self._apply_to_fields(ctype, value, result)

    def _apply_to_fields(self, ctype: str, value: str, result: ConstraintResult) -> None:
        """将抽取到的约束值填入 ConstraintResult 的对应字段。

        对每种类型取首次匹配的值（后续匹配不覆盖）。
        """
        field_map: dict[str, str] = {
            "cabinet_type": "cabinet_type",
            "dimensions": "dimensions",
            "ip_rating": "ip_rating",
            "grounding": "grounding_mode",
            "inbound_outbound": "inbound_outbound",
            "busbar": "busbar_spec",
            "frame_breaker": "frame_breaker",
            "mccb": "mccb",
            "meter": "meter_incomer",
            "reactive_comp": "reactive_comp",
            "surge": "surge_protection",
            "ats": "ats_config",
            "generator": "generator_switch",
        }
        field_name = field_map.get(ctype)
        if field_name and getattr(result, field_name) is None:
            setattr(result, field_name, value)
        # Extend meter: first match = incomer, second = feeder
        if ctype == "meter" and result.meter_incomer and result.meter_feeder is None:
            if value != result.meter_incomer:
                result.meter_feeder = value

    def extract_from_document(self, document_metadata: dict[str, Any]) -> ConstraintResult:
        """从 Word `ProjectDocument.metadata` 中抽取约束。

        这是便捷方法，直接接收 Word 解析器产出的 metadata dict。
        """
        paragraphs = document_metadata.get("paragraphs", [])
        if isinstance(paragraphs, list):
            para_texts = [p if isinstance(p, str) else str(p) for p in paragraphs]
        else:
            para_texts = []
        return self.extract(para_texts)

    def to_validation_rules(self, result: ConstraintResult) -> dict[str, Any]:
        """将抽取的约束转换为校验引擎可用的规则字典。

        返回的字典可以直接合并到 `ProjectDocument.metadata` 的 `constraints` 字段。
        """
        rules: dict[str, Any] = {}
        if result.cabinet_type:
            rules["expected_cabinet_type"] = result.cabinet_type
        if result.ip_rating:
            rules["expected_ip_rating"] = result.ip_rating
        if result.grounding_mode:
            rules["expected_grounding_mode"] = result.grounding_mode
        if result.specified_brands:
            rules["preferred_brands"] = result.specified_brands
        if result.busbar_spec:
            rules["busbar_specification"] = result.busbar_spec
        return rules
