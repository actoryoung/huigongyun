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
        "变频柜": {
            "materials": [
                {"name": "变频器", "spec": "按功率", "unit": "台", "quantity": 1},
                {"name": "输入电抗器", "spec": "按功率", "unit": "台", "quantity": 1},
                {"name": "塑壳断路器", "spec": "按功率", "unit": "台", "quantity": 1},
            ],
        },
        "MCC柜": {
            "materials": [
                {"name": "塑壳断路器", "spec": "按回路配置", "unit": "台", "quantity": "按回路数"},
                {"name": "接触器", "spec": "按回路配置", "unit": "台", "quantity": "按回路数"},
                {"name": "热继电器", "spec": "按回路配置", "unit": "只", "quantity": "按回路数"},
            ],
        },
        "配电箱": {
            "materials": [
                {"name": "微型断路器", "spec": "按回路配置", "unit": "台", "quantity": "按回路数"},
                {"name": "漏电保护器", "spec": "按回路配置", "unit": "只", "quantity": "按回路数"},
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
            "进线柜": ["进线柜", "馈线柜", "电源进线柜"],
            "出线柜": ["出线柜"],
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
        """遍历 cabinets 逐柜注入辅材 BomLine，合并去重。"""
        for cabinet in result.cabinets:
            new_lines: list[BomLine] = []
            new_lines += self._apply_cabinet_type(cabinet)
            new_lines += self._apply_grounding(cabinet)
            new_lines += self._apply_inbound(cabinet)
            self._merge_into_existing(new_lines, result.bom_lines)
        return result

    # ── 合并去重 ───────────────────────────────────────────────────

    def _merge_into_existing(self, new_lines: list[BomLine], existing: list[BomLine]) -> None:
        """将新 BomLine 合并到现有列表，同名同规格同品牌同柜号 quantity 相加。"""
        for new_line in new_lines:
            merged = False
            for exist_line in existing:
                if (
                    exist_line.cabinet_no == new_line.cabinet_no
                    and exist_line.material.name == new_line.material.name
                    and exist_line.material.spec == new_line.material.spec
                    and exist_line.material.brand == new_line.material.brand
                ):
                    exist_line.material.quantity += (new_line.material.quantity or 0)
                    merged = True
                    break
            if not merged:
                existing.append(new_line)

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
        """将规则物料字典列表转换为 BomLine 列表，解析占位符。"""
        lines: list[BomLine] = []
        for mat in materials:
            spec = self._resolve_spec(mat.get("spec"), cabinet)
            quantity, pending_qty = self._resolve_quantity(mat.get("quantity"), cabinet)

            remarks_parts = [rule_label]
            if pending_qty:
                remarks_parts.append("pending_quantity")

            material = MaterialRecord(
                name=mat["name"],
                spec=spec,
                unit=mat.get("unit"),
                quantity=quantity,
                source=SourceRef(file_name="bom_rules", file_type="rule", excerpt=rule_label),
                confidence=0.7 if not pending_qty else 0.4,
                remarks="; ".join(remarks_parts),
            )
            lines.append(BomLine(
                cabinet_no=cabinet.cabinet_no,
                material=material,
                derived_from="规则推算",
            ))
        return lines

    # ── 占位符解析 ─────────────────────────────────────────────────

    _PLACEHOLDER_SPECS = {"按额定电流", "按回路配置", "按功率", "按补偿容量"}

    @staticmethod
    def _resolve_spec(spec: str | None, cabinet: CabinetRecord) -> str | None:
        """解析 spec 占位符：按额定电流 → 从 cabinet.rated_current 推断。"""
        if spec is None or spec not in AuxMaterialInjector._PLACEHOLDER_SPECS:
            return spec
        if spec == "按额定电流" and cabinet.rated_current:
            return f"~{cabinet.rated_current}"
        return spec  # 保留占位符，待人工确认

    _NON_NUMERIC_QUANTITY = {"按柜宽", "按回路数", "按额定电流", "按补偿容量", "按功率"}

    @staticmethod
    def _resolve_quantity(quantity: Any, cabinet: CabinetRecord) -> tuple[float, bool]:
        """解析 quantity 占位符，返回 (数值, 是否pending)。"""
        if isinstance(quantity, (int, float)):
            return float(quantity), False
        if isinstance(quantity, str) and quantity in AuxMaterialInjector._NON_NUMERIC_QUANTITY:
            if quantity == "按柜宽":
                width = AuxMaterialInjector._parse_dimension_width(cabinet.dimensions)
                if width is not None:
                    return width / 1000.0, False  # mm → m
                return 0.0, True
            if quantity == "按回路数":
                if cabinet.circuit_count is not None and cabinet.circuit_count > 0:
                    return float(cabinet.circuit_count), False
                return 0.0, True
            if quantity == "按额定电流":
                if cabinet.rated_current:
                    return 1.0, False
                return 0.0, True
            if quantity in ("按补偿容量", "按功率"):
                return 0.0, True  # 需要额外输入，标记 pending
            return 0.0, True
        return float(quantity) if quantity else 0.0, False

    @staticmethod
    def _parse_dimension_width(dimensions: str | None) -> float | None:
        """从 '宽x深x高' 字符串解析宽度 (mm)，如 '800x800x2200' → 800.0。"""
        if not dimensions:
            return None
        parts = str(dimensions).replace(" ", "").lower().split("x")
        if len(parts) >= 1:
            try:
                return float(parts[0])
            except ValueError:
                pass
        return None
