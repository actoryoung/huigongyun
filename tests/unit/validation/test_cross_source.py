"""跨源校验规则单元测试。"""

import pytest

from huigongyun.validation.cross_source import (
    CrossSourceValidatorMixin,
    extract_cabinet_numbers_from_texts,
    _normalize_cabinet_type,
    _normalize_brand,
)


class TestCabinetNumberExtraction:
    """柜号提取函数测试。"""

    def test_extracts_standard_cabinet_numbers(self):
        texts = ["AL1", "AP02", "K1柜", "MCC1 配电柜"]
        result = extract_cabinet_numbers_from_texts(texts)
        assert "AL1" in result
        assert "AP02" in result
        assert "K1" in result
        assert "MCC1" in result

    def test_excludes_electrical_model_numbers(self):
        """型号如 NSX250 不应被误识别为柜号。"""
        texts = ["NSX250", "CVS100", "EZD160"]
        result = extract_cabinet_numbers_from_texts(texts)
        assert "NSX250" not in result

    def test_empty_input_returns_empty_set(self):
        assert extract_cabinet_numbers_from_texts([]) == set()
        assert extract_cabinet_numbers_from_texts(["some text without cabinet"]) == set()


class TestNormalization:
    """归一化函数测试。"""

    def test_normalize_cabinet_type_strips_prefix(self):
        """'柜体采用Blokset' → 'BLOKSET'"""
        assert _normalize_cabinet_type("柜体采用Blokset") == "BLOKSET"
        assert _normalize_cabinet_type("BlokSeT") == "BLOKSET"
        assert _normalize_cabinet_type("柜体型采用Blokset") == "BLOKSET"

    def test_normalize_cabinet_type_equivalent(self):
        """不同写法归一化后一致。"""
        a = _normalize_cabinet_type("BlokSeT")
        b = _normalize_cabinet_type("柜体采用Blokset")
        assert a == b

    def test_normalize_brand(self):
        assert _normalize_brand("施耐德") == "施耐德"
        assert _normalize_brand("Schneider") == "schneider"
        assert _normalize_brand(" 正泰 ") == "正泰"


class TestCrossSourceValidatorMixin:
    """跨源规则行为测试。"""

    def test_no_data_produces_no_issues(self):
        """无跨源数据时静默跳过。"""
        from huigongyun.models import ProjectDocument, ProjectResult

        doc = ProjectDocument(project_name="test", files=[])
        result = ProjectResult(project=doc)
        mixin = CrossSourceValidatorMixin()
        issues = mixin._validate_cross_source(result)
        assert issues == []

    def test_cabinet_number_consistency_with_empty_dwg(self):
        """DWG 无文本时不触发规则。"""
        from huigongyun.models import ProjectDocument, ProjectResult

        doc = ProjectDocument(project_name="test", files=[], metadata={"electrical_texts": []})
        result = ProjectResult(project=doc)
        mixin = CrossSourceValidatorMixin()
        issues = mixin._validate_cross_source(result)
        dwg_issues = [i for i in issues if "dwg" in str(i.details)]
        assert len(dwg_issues) == 0

    def test_cabinet_number_consistency_detects_missing(self):
        """DWG 有柜号但 Excel 无 → issue。"""
        from huigongyun.models import ProjectDocument, ProjectResult, CabinetRecord

        doc = ProjectDocument(project_name="test", files=[])
        result = ProjectResult(project=doc)
        result.cabinets.append(CabinetRecord(cabinet_no="AL1", cabinet_type="BlokSeT"))

        mixin = CrossSourceValidatorMixin()
        dwg_texts = ["AL1 配电柜", "AL2 配电柜", "AP1"]  # AL2、AP1 在 Excel 中不存在
        issues = mixin._validate_cabinet_number_consistency(result, dwg_texts)

        # AL2 和 AP1 在 DWG 有但 Excel 无 → warning
        missing = [i for i in issues if i.severity == "warning"]
        assert len(missing) == 2
        missing_cabs = {i.cabinet_no for i in missing}
        assert "AL2" in missing_cabs
        assert "AP1" in missing_cabs

    def test_brand_compliance_skips_when_no_preferred(self):
        """无 preferred_brands 时跳过品牌规则。"""
        from huigongyun.models import ProjectDocument, ProjectResult

        doc = ProjectDocument(project_name="test", files=[])
        result = ProjectResult(project=doc)
        mixin = CrossSourceValidatorMixin()
        issues = mixin._validate_brand_compliance(result, {})
        assert issues == []

    def test_ward_compliance_detects_non_preferred(self):
        """BOM 中使用非推荐品牌 → issue。"""
        from huigongyun.models import ProjectDocument, ProjectResult, BomLine, MaterialRecord

        doc = ProjectDocument(project_name="test", files=[])
        result = ProjectResult(project=doc)
        mat = MaterialRecord(name="断路器", brand="正泰", spec="NSX250", quantity=1)
        result.bom_lines.append(BomLine(cabinet_no="K1", material=mat, derived_from="test"))

        mixin = CrossSourceValidatorMixin()
        rules = {"preferred_brands": ["施耐德", "ABB"]}
        issues = mixin._validate_brand_compliance(result, rules)
        assert len(issues) == 1
        assert "正泰" in issues[0].message
        assert "施耐德" in issues[0].details.get("preferred_brands", [])
