"""辅材规则注入器 — 基于柜型/接地/进出线三层规则注入辅材 BomLine。

``AuxMaterialInjector`` 在每个柜体上独立工作，从 ``bom_rules.json``
查表并将匹配的物料作为 ``BomLine`` 注入，标记 ``derived_from = "规则推算"``。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..models import BomLine, CabinetRecord, MaterialRecord, ProjectResult, SourceRef

logger = logging.getLogger(__name__)

# ── 内置回退规则 ──────────────────────────────────────────────────────

_FALLBACK_RULES: dict[str, Any] = {
    "cabinet_type_templates": {
        "进线柜": {
            "materials": [
                {"name": "框架断路器", "spec": "按额定电流", "unit": "台", "quantity": "按额定电流"},
                {"name": "测量电流互感器", "spec": "按额定电流", "unit": "只", "quantity": 4},
                {"name": "多功能表", "spec": None, "unit": "只", "quantity": 1},
                {"name": "浪涌保护器", "spec": None, "unit": "套", "quantity": 1},
            ],
        },
        "母联柜": {
            "materials": [
                {"name": "框架断路器", "spec": "按额定电流", "unit": "台", "quantity": "按额定电流"},
                {"name": "测量电流互感器", "spec": "按额定电流", "unit": "只", "quantity": 4},
                {"name": "多功能表", "spec": None, "unit": "只", "quantity": 1},
            ],
        },
        "出线柜": {
            "materials": [
                {"name": "塑壳断路器", "spec": "按回路配置", "unit": "台", "quantity": "按回路数"},
                {"name": "接触器", "spec": "按回路配置", "unit": "台", "quantity": "按回路数"},
                {"name": "热继电器", "spec": "按回路配置", "unit": "只", "quantity": "按回路数"},
            ],
        },
        "补偿柜": {
            "materials": [
                {"name": "隔离开关", "spec": "按补偿容量", "unit": "台", "quantity": 1},
                {"name": "电容器", "spec": "按补偿容量", "unit": "台", "quantity": "按补偿容量"},
                {"name": "电抗器", "spec": "按补偿容量", "unit": "台", "quantity": "按补偿容量"},
                {"name": "晶闸管投切开关", "spec": "按补偿容量", "unit": "台", "quantity": "按补偿容量"},
            ],
        },
        "ATS柜": {
            "materials": [
                {"name": "双电源开关", "spec": "按额定电流", "unit": "台", "quantity": 1},
                {"name": "塑壳断路器", "spec": "按额定电流", "unit": "台", "quantity": 2},
            ],
        },
    },
    "grounding_materials": {
        "TN-S": [
            {"name": "N排", "spec": None, "unit": "米", "quantity": "按柜宽"},
            {"name": "PE排", "spec": None, "unit": "米", "quantity": "按柜宽"},
        ],
        "TN-C": [
            {"name": "PEN排", "spec": None, "unit": "米", "quantity": "按柜宽"},
        ],
        "TT": [
            {"name": "PE排", "spec": None, "unit": "米", "quantity": "按柜宽"},
            {"name": "漏电保护器", "spec": "按额定电流", "unit": "只", "quantity": 1},
        ],
        "IT": [
            {"name": "PE排", "spec": None, "unit": "米", "quantity": "按柜宽"},
            {"name": "绝缘监测装置", "spec": None, "unit": "台", "quantity": 1},
        ],
    },
    "inbound_outbound_materials": {
        "电缆上进": [
            {"name": "电缆夹具", "spec": None, "unit": "套", "quantity": "按回路数"},
        ],
        "电缆下进": [
            {"name": "电缆夹具", "spec": None, "unit": "套", "quantity": "按回路数"},
        ],
        "母线槽进线": [
            {"name": "过渡母排", "spec": None, "unit": "套", "quantity": 1},
            {"name": "母线连接件", "spec": None, "unit": "套", "quantity": 1},
        ],
        "背靠背拼柜": [
            {"name": "拼柜连接母排", "spec": None, "unit": "套", "quantity": 1},
            {"name": "拼柜螺栓", "spec": None, "unit": "套", "quantity": 1},
        ],
    },
    "normalization_aliases": {
        "cabinet_type": {
            "进线柜": ["进线柜", "馈线柜", "出线柜", "电源进线柜"],
            "母联柜": ["母联柜", "联络柜"],
            "补偿柜": ["补偿柜", "电容器柜", "无功补偿柜", "SVG柜"],
            "ATS柜": ["ATS柜", "双电源柜", "互投柜"],
        },
        "grounding": {
            "TN-S": ["TN-S", "TN-S 系统", "TNS", "tn-s", "tns"],
            "TN-C": ["TN-C", "TN-C 系统", "TNC", "tn-c", "tnc"],
            "TN-C-S": ["TN-C-S", "TN-C-S 系统", "TNCS", "tn-c-s", "tncs"],
            "TT": ["TT", "TT 系统", "tt"],
            "IT": ["IT", "IT 系统", "it"],
        },
        "inbound_outbound": {
            "电缆上进": ["电缆上进", "上进", "上进上出", "上进线"],
            "电缆下进": ["电缆下进", "下进", "下进下出", "下进线"],
            "母线槽进线": ["母线槽进线", "母线进线", "母线接入", "母线槽接入"],
            "背靠背拼柜": ["背靠背拼柜", "拼柜", "背靠背", "并柜"],
        },
    },
}


class AuxMaterialInjector:
    """基于柜型/接地/进出线三层规则注入辅材 BomLine。

    在每个柜体上独立工作，从规则表查表并将匹配的物料标记
    ``derived_from = "规则推算"`` 注入到 ``ProjectResult.bom_lines``。

    Args:
        rules_path: bom_rules.json 路径，None 使用默认路径。
    """

    def __init__(self, rules_path: str | None = None) -> None:
        self._rules = self._load_rules(rules_path)

    # ── 规则加载 ───────────────────────────────────────────────────

    def _load_rules(self, rules_path: str | None) -> dict[str, Any]:
        if rules_path is None:
            rules_path = str(Path(__file__).parent / "dictionaries" / "bom_rules.json")
        try:
            path = Path(rules_path)
            if path.exists():
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                return self._normalize_rules(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load bom_rules.json (%s), using fallback", exc)
        return self._normalize_rules(_FALLBACK_RULES)

    @staticmethod
    def _normalize_rules(data: dict[str, Any]) -> dict[str, Any]:
        return {
            "cabinet_type_templates": data.get("cabinet_type_templates", {}),
            "grounding_materials": data.get("grounding_materials", {}),
            "inbound_outbound_materials": data.get("inbound_outbound_materials", {}),
            "normalization_aliases": data.get("normalization_aliases", {}),
        }

    # ── 归一化 ─────────────────────────────────────────────────────

    def _normalize_cabinet_type(self, type_str: str | None) -> str | None:
        """柜型别名归一化：馈线柜/出线柜→进线柜，电容器柜→补偿柜 等。"""
        if not type_str:
            return None
        aliases = self._rules.get("normalization_aliases", {}).get("cabinet_type", {})
        type_clean = type_str.strip()
        for canonical, variants in aliases.items():
            if type_clean in variants:
                return canonical
        return None

    def _normalize_grounding(self, mode_str: str | None) -> str | None:
        """接地方式归一化：TNS→TN-S, tn-s→TN-S 等。"""
        if not mode_str:
            return None
        aliases = self._rules.get("normalization_aliases", {}).get("grounding", {})
        mode_clean = mode_str.strip()
        for canonical, variants in aliases.items():
            if mode_clean in variants:
                return canonical
        return None

    def _normalize_inbound(self, mode_str: str | None) -> str | None:
        """进出线方式归一化：上进→电缆上进，母线接入→母线槽进线 等。"""
        if not mode_str:
            return None
        aliases = self._rules.get("normalization_aliases", {}).get("inbound_outbound", {})
        mode_clean = mode_str.strip()
        for canonical, variants in aliases.items():
            if mode_clean in variants:
                return canonical
        return None

    # ── 公共入口 ───────────────────────────────────────────────────

    def inject(self, result: ProjectResult) -> ProjectResult:
        """遍历 cabinets 逐柜注入辅材 BomLine。"""
        for cabinet in result.cabinets:
            new_lines: list[BomLine] = []
            new_lines += self._apply_cabinet_type(cabinet)
            new_lines += self._apply_grounding(cabinet)
            new_lines += self._apply_inbound(cabinet)
            result.bom_lines.extend(new_lines)
        return result

    # ── 单层注入 ───────────────────────────────────────────────────

    def _apply_cabinet_type(self, cabinet: CabinetRecord) -> list[BomLine]:
        """根据柜型注入模板物料。"""
        key = self._normalize_cabinet_type(cabinet.cabinet_type)
        if key is None:
            return []
        template = self._rules["cabinet_type_templates"].get(key)
        if template is None:
            return []
        return self._materials_to_bom_lines(template["materials"], cabinet, f"柜型:{key}")

    def _apply_grounding(self, cabinet: CabinetRecord) -> list[BomLine]:
        """根据接地方式注入追加物料。"""
        key = self._normalize_grounding(cabinet.grounding_mode)
        if key is None:
            return []
        materials = self._rules["grounding_materials"].get(key, [])
        if not materials:
            return []
        return self._materials_to_bom_lines(materials, cabinet, f"接地:{key}")

    def _apply_inbound(self, cabinet: CabinetRecord) -> list[BomLine]:
        """根据进出线方式注入辅材。"""
        key = self._normalize_inbound(cabinet.inbound_outbound)
        if key is None:
            return []
        materials = self._rules["inbound_outbound_materials"].get(key, [])
        if not materials:
            return []
        return self._materials_to_bom_lines(materials, cabinet, f"进出线:{key}")

    # ── 辅助方法 ───────────────────────────────────────────────────

    def _materials_to_bom_lines(
        self, materials: list[dict[str, Any]], cabinet: CabinetRecord, rule_label: str
    ) -> list[BomLine]:
        """将规则物料字典列表转换为 BomLine 列表。"""
        lines: list[BomLine] = []
        for mat in materials:
            material = MaterialRecord(
                name=mat["name"],
                spec=mat.get("spec"),
                unit=mat.get("unit"),
                quantity=mat.get("quantity", 1) if isinstance(mat.get("quantity"), (int, float)) else 0.0,
                source=SourceRef(file_name="bom_rules", file_type="rule", excerpt=rule_label),
                confidence=0.7,
                remarks=rule_label,
            )
            lines.append(BomLine(
                cabinet_no=cabinet.cabinet_no,
                material=material,
                derived_from="规则推算",
            ))
        return lines
