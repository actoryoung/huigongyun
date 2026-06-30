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
        ("出线柜", "进线柜"),
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
