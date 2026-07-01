"""AuxMaterialInjector 集成测试 — 完整链路验证。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.adapters.default import DefaultBomGenerator, DefaultCabinetExtractor, DefaultMaterialNormalizer, DefaultProjectParser
from src.generation.rules import AuxMaterialInjector
from src.models import BomLine, MaterialRecord


FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures"


class TestFullPipeline:
    """完整链路集成测试。"""

    def test_full_pipeline_with_aux_materials(self):
        """DefaultBomGenerator 完整链路产出含规则注入物料。"""
        fixture = str(FIXTURE_DIR / "aux_material_test.xlsx")
        doc = DefaultProjectParser().parse(fixture)
        result = DefaultCabinetExtractor().extract(doc)

        assert len(result.cabinets) >= 3

        # 注入辅材
        result = AuxMaterialInjector().inject(result)

        # 验证注入
        rule_lines = [l for l in result.bom_lines if l.derived_from == "规则推算"]
        assert len(rule_lines) > 0, "Should have rule-injected materials"

        # 验证具体物料
        names = [l.material.name for l in rule_lines]
        assert "框架断路器" in names or "N排" in names or "隔离开关" in names

    def test_normalization_fills_brand_for_rule_materials(self):
        """注入物料经归一化后品牌被填充。"""
        fixture = str(FIXTURE_DIR / "aux_material_test.xlsx")
        doc = DefaultProjectParser().parse(fixture)
        result = DefaultCabinetExtractor().extract(doc)
        result = AuxMaterialInjector().inject(result)
        result = DefaultMaterialNormalizer().normalize(result)

        rule_lines = [l for l in result.bom_lines if l.derived_from == "规则推算"]
        assert len(rule_lines) > 0, "Should have rule lines after normalization"

        at_least_one_has_brand = any(
            l.material.normalized_brand and l.material.normalized_brand != "pending"
            for l in rule_lines
        )
        # 归一化后品牌应被填充（国产柜体 → 国产品牌映射）
        assert at_least_one_has_brand, "At least one injected material should get brand after normalization"

    def test_pending_quantity_generates_validation_issue(self):
        """pending_quantity 标记物料在导出时有提示。"""
        fixture = str(FIXTURE_DIR / "aux_material_test.xlsx")
        doc = DefaultProjectParser().parse(fixture)
        result = DefaultCabinetExtractor().extract(doc)

        # 创建一个无 dimensions 的柜体（占位符无法解析）
        from src.models import CabinetRecord
        result.cabinets.append(CabinetRecord(
            cabinet_no="PEND01", cabinet_type="配电箱",
            grounding_mode="TN-S", dimensions=None, circuit_count=None,
        ))
        result = AuxMaterialInjector().inject(result)

        pending_lines = [
            l for l in result.bom_lines
            if l.cabinet_no == "PEND01" and "pending" in (l.material.remarks or "").lower()
        ]
        assert len(pending_lines) > 0, "Should have pending lines for unresolvable placeholders"

    def test_no_regression_project_b_pattern(self):
        """验证三层注入不影响已有柜体结果（项目 B 模式）。"""
        # 无 cabinet_type/grounding/inbound 的柜体不应注入任何物料
        from src.models import CabinetRecord, ProjectDocument, ProjectResult
        doc = ProjectDocument(project_name="test")
        result = ProjectResult(project=doc, cabinets=[
            CabinetRecord(cabinet_no="NO-RULES-01"),
            CabinetRecord(cabinet_no="NO-RULES-02"),
        ])

        before_count = len(result.bom_lines)
        result = AuxMaterialInjector().inject(result)

        assert len(result.bom_lines) == before_count, (
            "Cabinets without type/grounding/inbound should not get injected materials"
        )

    def test_aggregator_works_with_rule_materials(self):
        """聚合器正确处理注入物料。"""
        fixture = str(FIXTURE_DIR / "aux_material_test.xlsx")
        doc = DefaultProjectParser().parse(fixture)
        result = DefaultCabinetExtractor().extract(doc)
        result = AuxMaterialInjector().inject(result)
        result = DefaultBomGenerator().generate(result)

        assert len(result.summary) > 0
        assert all(isinstance(m, MaterialRecord) for m in result.summary)
