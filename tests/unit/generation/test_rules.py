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
