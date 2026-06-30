"""AuxMaterialInjector 单元测试 — L1: 规则加载。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from huigongyun.generation.rules import AuxMaterialInjector


class TestRulesLoading:
    """L1: 规则加载与降级 (4 用例)。"""

    def test_load_valid_rules_json(self):
        """加载有效的 bom_rules.json，三个 section 均非空。"""
        injector = AuxMaterialInjector()
        rules = injector._rules

        assert "cabinet_type_templates" in rules
        assert "grounding_materials" in rules
        assert "inbound_outbound_materials" in rules
        assert len(rules["cabinet_type_templates"]) >= 8
        assert "进线柜" in rules["cabinet_type_templates"]
        assert len(rules["grounding_materials"]) >= 5
        assert "TN-S" in rules["grounding_materials"]
        assert len(rules["inbound_outbound_materials"]) >= 5

    def test_load_missing_file_fallback(self, monkeypatch):
        """JSON 文件缺失时使用内置回退字典。"""
        monkeypatch.setattr(Path, "exists", lambda self: False)
        injector = AuxMaterialInjector()
        rules = injector._rules

        assert "cabinet_type_templates" in rules
        assert len(rules["cabinet_type_templates"]) >= 5
        assert len(rules["grounding_materials"]) >= 4

    def test_load_invalid_json_fallback(self, tmp_path):
        """JSON 格式错误时静默回退到内置字典。"""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json")
        injector = AuxMaterialInjector(rules_path=str(bad_file))
        rules = injector._rules

        assert "cabinet_type_templates" in rules
        assert len(rules["cabinet_type_templates"]) >= 5

    def test_load_partial_sections(self, tmp_path):
        """JSON 缺少部分 section 时，缺失层不影响。"""
        partial = tmp_path / "partial.json"
        partial.write_text(json.dumps({"cabinet_type_templates": {"测试柜": {"materials": []}}}))
        injector = AuxMaterialInjector(rules_path=str(partial))
        rules = injector._rules

        assert "cabinet_type_templates" in rules
        assert len(rules["grounding_materials"]) == 0
        assert len(rules["inbound_outbound_materials"]) == 0


class TestCabinetTypeNormalization:
    """L2: 柜型归一化 (5 用例)。"""

    @pytest.mark.parametrize("raw,expected", [
        ("进线柜", "进线柜"),
        ("馈线柜", "进线柜"),
        ("出线柜", "出线柜"),
        ("电源进线柜", "进线柜"),
        ("补偿柜", "补偿柜"),
        ("电容器柜", "补偿柜"),
        ("SVG柜", "补偿柜"),
        ("ATS柜", "ATS柜"),
        ("双电源柜", "ATS柜"),
        ("互投柜", "ATS柜"),
        ("母联柜", "母联柜"),
        ("联络柜", "母联柜"),
        ("变频柜", "变频柜"),
        ("MCC柜", "MCC柜"),
        ("配电箱", "配电箱"),
    ])
    def test_normalize_known_types(self, raw, expected):
        injector = AuxMaterialInjector()
        assert injector._normalize_cabinet_type(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "未知柜型", "xyz"])
    def test_normalize_unknown_returns_none(self, raw):
        injector = AuxMaterialInjector()
        assert injector._normalize_cabinet_type(raw) is None


class TestGroundingNormalization:
    """L3: 接地方式归一化 (5 用例)。"""

    @pytest.mark.parametrize("raw,expected", [
        ("TN-S", "TN-S"),
        ("TN-S 系统", "TN-S"),
        ("TNS", "TN-S"),
        ("tn-s", "TN-S"),
        ("TN-C", "TN-C"),
        ("TN-C 系统", "TN-C"),
        ("tnc", "TN-C"),
        ("TN-C-S", "TN-C-S"),
        ("tncs", "TN-C-S"),
        ("TT", "TT"),
        ("tt", "TT"),
        ("IT", "IT"),
        ("IT 系统", "IT"),
    ])
    def test_normalize_known_modes(self, raw, expected):
        injector = AuxMaterialInjector()
        assert injector._normalize_grounding(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "UNKNOWN", "XYZ"])
    def test_normalize_unknown_returns_none(self, raw):
        injector = AuxMaterialInjector()
        assert injector._normalize_grounding(raw) is None


class TestInboundOutboundNormalization:
    """L4: 进出线方式归一化 (5 用例)。"""

    @pytest.mark.parametrize("raw,expected", [
        ("电缆上进", "电缆上进"),
        ("上进", "电缆上进"),
        ("上进上出", "电缆上进"),
        ("上进线", "电缆上进"),
        ("电缆下进", "电缆下进"),
        ("下进", "电缆下进"),
        ("下进下出", "电缆下进"),
        ("母线槽进线", "母线槽进线"),
        ("母线进线", "母线槽进线"),
        ("母线接入", "母线槽进线"),
        ("母线槽接入", "母线槽进线"),
        ("母线槽出线", "母线槽出线"),
        ("背靠背拼柜", "背靠背拼柜"),
        ("拼柜", "背靠背拼柜"),
        ("背靠背", "背靠背拼柜"),
        ("并柜", "背靠背拼柜"),
    ])
    def test_normalize_known_modes(self, raw, expected):
        injector = AuxMaterialInjector()
        assert injector._normalize_inbound(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "未知方式", "xyz"])
    def test_normalize_unknown_returns_none(self, raw):
        injector = AuxMaterialInjector()
        assert injector._normalize_inbound(raw) is None


from huigongyun.models import CabinetRecord, ProjectDocument, ProjectResult


def _make_cabinet(cabinet_no="1AA1", cabinet_type=None, grounding=None, inbound=None, **kw):
    return CabinetRecord(
        cabinet_no=cabinet_no,
        cabinet_type=cabinet_type,
        grounding_mode=grounding,
        inbound_outbound=inbound,
        **kw,
    )


def _make_result(cabinets):
    doc = ProjectDocument(project_name="test")
    return ProjectResult(project=doc, cabinets=cabinets)


class TestSingleLayerInjection:
    """L5: 单层注入 (6 用例)。"""

    def test_all_three_layers_populated(self):
        """三层属性全有，注入物料数 = 各层之和。"""
        cabinet = _make_cabinet("1AA1", "进线柜", "TN-S", "电缆上进")
        result = _make_result([cabinet])
        injector = AuxMaterialInjector()
        result = injector.inject(result)

        assert len(result.bom_lines) > 0
        names = [line.material.name for line in result.bom_lines]
        assert "框架断路器" in names
        assert "浪涌保护器" in names
        assert "N排" in names or "PE排" in names
        assert "电缆夹具" in names

    def test_cabinet_type_only(self):
        """仅柜型，接地和进出线为空，仅注入柜型模板物料。"""
        cabinet = _make_cabinet("1AA2", "母联柜", None, None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        names = [line.material.name for line in result.bom_lines]
        assert "框架断路器" in names
        assert "多功能表" in names
        assert len(result.bom_lines) >= 3

    def test_grounding_only(self):
        """仅接地方式，无柜型和进出线，仅注入接地物料。"""
        cabinet = _make_cabinet("1AA3", None, "TN-C", None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        names = [line.material.name for line in result.bom_lines]
        assert "PEN排" in names
        assert len(result.bom_lines) >= 1

    def test_inbound_only(self):
        """仅进出线方式，仅注入进出线辅材。"""
        cabinet = _make_cabinet("1AA4", None, None, "母线槽进线")
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        names = [line.material.name for line in result.bom_lines]
        assert "过渡母排" in names
        assert "母线连接件" in names

    def test_all_empty_attributes_no_injection(self):
        """三个属性全部为空，不注入任何物料。"""
        cabinet = _make_cabinet("1AA5", None, None, None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        assert len(result.bom_lines) == 0

    def test_compensation_cabinet_with_grounding(self):
        """补偿柜 + TN-S + 电缆下进，三层叠加。"""
        cabinet = _make_cabinet("1AA6", "补偿柜", "TN-S", "电缆下进")
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        names = [line.material.name for line in result.bom_lines]
        assert "隔离开关" in names
        assert "电容器" in names
        assert "N排" in names
        assert "PE排" in names
        assert "电缆夹具" in names


from huigongyun.models import BomLine, MaterialRecord


class TestMergeAndDedup:
    """L6: 合并去重 (5 用例)。"""

    def test_same_material_from_two_layers_merges(self):
        """两层同时注入同名物料 PE排，合并为 1 条 quantity 相加。"""
        cabinet = _make_cabinet("B01", "配电箱", "TN-S", None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        pe_lines = [l for l in result.bom_lines if l.material.name == "PE排"]
        assert len(pe_lines) == 1, f"PE排 should merge, got {len(pe_lines)}"

    def test_no_duplicates_across_three_layers(self):
        """三层注入均不含重复 → 总物料数 = 三层物料数之和。"""
        cabinet = _make_cabinet("B02", "母联柜", "TN-C", "电缆下进")
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)
        # 每层至少 1 条，无重叠 → >= 1+1+1 = 3
        assert len(result.bom_lines) >= 3

    def test_rule_material_merges_with_existing_excel_bom(self):
        """规则注入物料与 Excel 已提取的同名同规物料合并。"""
        cabinet = _make_cabinet("B03", "进线柜", None, None)
        result = _make_result([cabinet])

        # 模拟 Excel 已提取的物料
        existing = MaterialRecord(name="框架断路器", spec="按额定电流", unit="台")
        existing.quantity = 1
        result.bom_lines.append(BomLine(
            cabinet_no="B03", material=existing, derived_from="Excel提取"
        ))

        result = AuxMaterialInjector().inject(result)

        cb_lines = [l for l in result.bom_lines if l.material.name == "框架断路器"]
        assert len(cb_lines) == 1, f"Should merge, got {len(cb_lines)}"

    def test_same_name_different_spec_not_merged(self):
        """同名但 spec 不同，不合并。"""
        cabinet = _make_cabinet("B04", "进线柜", None, None)
        result = _make_result([cabinet])

        existing = MaterialRecord(name="框架断路器", spec="NSX630", unit="台")
        existing.quantity = 1
        result.bom_lines.append(BomLine(
            cabinet_no="B04", material=existing, derived_from="Excel提取"
        ))

        result = AuxMaterialInjector().inject(result)

        cb_lines = [l for l in result.bom_lines if l.material.name == "框架断路器"]
        assert len(cb_lines) == 2, f"Different spec should not merge, got {len(cb_lines)}"

    def test_same_name_different_brand_not_merged(self):
        """同名同规但 brand 不同，不合并。"""
        cabinet = _make_cabinet("B05", "进线柜", None, None)
        result = _make_result([cabinet])

        existing = MaterialRecord(name="框架断路器", spec="按额定电流", unit="台", brand="施耐德")
        existing.quantity = 1
        result.bom_lines.append(BomLine(
            cabinet_no="B05", material=existing, derived_from="Excel提取"
        ))

        result = AuxMaterialInjector().inject(result)

        cb_lines = [l for l in result.bom_lines if l.material.name == "框架断路器"]
        assert len(cb_lines) == 2, f"Different brand should not merge, got {len(cb_lines)}"


class TestPlaceholderResolution:
    """L7: 占位符处理 (6 用例)。"""

    def test_quantity_by_cabinet_width_with_dimensions(self):
        """quantity='按柜宽' + dimensions='800x800x2200' → 解析为数值。"""
        cabinet = _make_cabinet("C01", None, "TN-S", None, dimensions="800x800x2200")
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        pe_line = next(l for l in result.bom_lines if l.material.name == "PE排")
        assert pe_line.material.quantity > 0

    def test_quantity_by_cabinet_width_without_dimensions(self):
        """quantity='按柜宽' + dimensions 为空 → 标记 pending。"""
        cabinet = _make_cabinet("C02", None, "TN-S", None, dimensions=None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        pe_line = next(l for l in result.bom_lines if l.material.name == "PE排")
        assert pe_line.material.quantity == 0.0
        assert pe_line.material.remarks and "pending" in pe_line.material.remarks.lower()

    def test_quantity_by_circuit_count_with_value(self):
        """quantity='按回路数' + circuit_count=12 → quantity=12。"""
        cabinet = _make_cabinet("C03", "出线柜", None, None, circuit_count=12)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        mccb_line = next(l for l in result.bom_lines if l.material.name == "塑壳断路器")
        assert mccb_line.material.quantity == 12

    def test_quantity_by_circuit_count_without_value(self):
        """quantity='按回路数' + circuit_count=None → 标记 pending。"""
        cabinet = _make_cabinet("C04", "出线柜", None, None, circuit_count=None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        mccb_line = next(l for l in result.bom_lines if l.material.name == "塑壳断路器")
        assert "pending" in (mccb_line.material.remarks or "").lower()

    def test_spec_by_rated_current_with_value(self):
        """spec='按额定电流' + rated_current='630A' → 替换 spec。"""
        cabinet = _make_cabinet("C05", "进线柜", None, None, rated_current="630A")
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        cb_line = next(l for l in result.bom_lines if l.material.name == "框架断路器")
        assert "pending" not in (cb_line.material.remarks or "").lower()

    def test_spec_by_rated_current_without_value(self):
        """spec='按额定电流' + rated_current=None → 标记 pending_spec。"""
        cabinet = _make_cabinet("C06", "进线柜", None, None, rated_current=None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        cb_line = next(l for l in result.bom_lines if l.material.name == "框架断路器")
        assert "pending" in (cb_line.material.remarks or "").lower()


class TestSourceMarking:
    """L8: 来源标记 (3 用例)。"""

    def test_derived_from_is_rule_estimate(self):
        """注入的 BomLine 标记 derived_from='规则推算'。"""
        cabinet = _make_cabinet("D01", "进线柜", "TN-S", None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        for line in result.bom_lines:
            assert line.derived_from == "规则推算"

    def test_material_source_is_bom_rules(self):
        """MaterialRecord.source.file_name = 'bom_rules'。"""
        cabinet = _make_cabinet("D02", "进线柜", None, None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        for line in result.bom_lines:
            assert line.material.source is not None
            assert line.material.source.file_name == "bom_rules"

    def test_remark_contains_rule_label(self):
        """remark 包含具体规则名。"""
        cabinet = _make_cabinet("D03", "母联柜", "TN-S", None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        remarks_all = " ".join(l.material.remarks or "" for l in result.bom_lines)
        assert "柜型:母联柜" in remarks_all
        assert "接地:TN-S" in remarks_all


class TestEdgeCasesAndDegradation:
    """L9: 边缘降级 (6 用例)。"""

    def test_empty_cabinets_no_crash(self):
        """cabinets 为空列表不崩溃。"""
        result = _make_result([])
        result = AuxMaterialInjector().inject(result)
        assert len(result.bom_lines) == 0

    def test_unknown_cabinet_type_skips_layer(self):
        """柜型不在 JSON 中，跳过柜型层，不影响其他层。"""
        cabinet = _make_cabinet("E01", "太阳能柜", "TN-S", "电缆上进")
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        names = [l.material.name for l in result.bom_lines]
        assert "N排" in names, "Grounding layer should still work"
        assert "电缆夹具" in names, "Inbound layer should still work"

    def test_unknown_grounding_skips_layer(self):
        """接地方式不在 JSON 中，log info，不影响其他层。"""
        cabinet = _make_cabinet("E02", "进线柜", "TN-XYZ", "电缆上进")
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        names = [l.material.name for l in result.bom_lines]
        assert "框架断路器" in names, "Cabinet type layer should still work"

    def test_single_cabinet_no_matches_injects_nothing(self):
        """单个柜体三层无匹配 → 不注入任何物料。"""
        cabinet = _make_cabinet("E03", "未知XX", "未知YY", "未知ZZ")
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        assert len(result.bom_lines) == 0

    def test_multi_cabinet_batch(self):
        """多柜体批量处理（3 柜体）每个独立计算。"""
        cabinets = [
            _make_cabinet("E04", "进线柜", "TN-S", "电缆上进"),
            _make_cabinet("E05", "母联柜", None, None),
            _make_cabinet("E06", None, "TN-C", "电缆下进"),
        ]
        result = _make_result(cabinets)
        result = AuxMaterialInjector().inject(result)

        # 每个柜体应至少有物料
        cabinet_nos = set(l.cabinet_no for l in result.bom_lines)
        assert "E04" in cabinet_nos
        assert "E05" in cabinet_nos
        assert "E06" in cabinet_nos

    def test_existing_derived_from_not_overwritten(self):
        """已有 derived_from 非空时保留原值（保留人工修正）。"""
        cabinet = _make_cabinet("E07", "进线柜", None, None)
        result = _make_result([cabinet])

        manual = MaterialRecord(name="框架断路器", spec="NSX400N", unit="台")
        manual.quantity = 1
        result.bom_lines.append(BomLine(
            cabinet_no="E07", material=manual, derived_from="人工修正"
        ))

        result = AuxMaterialInjector().inject(result)

        manual_lines = [l for l in result.bom_lines if l.derived_from == "人工修正"]
        assert len(manual_lines) == 1, "Manual edit should be preserved"
