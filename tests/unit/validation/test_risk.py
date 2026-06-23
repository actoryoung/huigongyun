"""RiskClassifier 和 RiskLevel 单元测试。

验证默认风险映射、上下文升级规则和仪表盘聚合。
"""

from __future__ import annotations

import pytest

from huigongyun.models import ProjectDocument, ProjectResult, ValidationIssue
from huigongyun.validation.risk import RiskClassifier, RiskDashboard, RiskLevel


def _make_issue(issue_type: str, **kwargs) -> ValidationIssue:
    defaults = {
        "issue_type": issue_type,
        "severity": "info",
        "message": f"Test: {issue_type}",
    }
    defaults.update(kwargs)
    return ValidationIssue(**defaults)


class TestRiskLevel:
    """RiskLevel 枚举测试。"""

    def test_str_serializable(self):
        """RiskLevel 值应为 str 类型，可直接 JSON 序列化。"""
        import json
        levels = {level.value: level.value for level in RiskLevel}
        json_str = json.dumps(levels)
        assert "critical" in json_str
        assert "info" in json_str

    def test_level_order(self):
        """INFO < LOW < MEDIUM < HIGH < CRITICAL。"""
        assert RiskLevel.INFO.value == "info"
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"


class TestRiskClassifierDefaultMapping:
    """默认 issue_type → RiskLevel 映射测试。"""

    def test_critical_issues(self):
        classifier = RiskClassifier()
        issues = [
            _make_issue("missing_material_name"),
            _make_issue("missing_cabinet"),
        ]
        classifier.classify(issues)
        for issue in issues:
            assert issue.risk_level == "critical", f"{issue.issue_type} should be critical"

    def test_high_issues(self):
        classifier = RiskClassifier()
        issues = [
            _make_issue("brand_conflict"),
            _make_issue("duplicate_cabinet"),
            _make_issue("invalid_cabinet_quantity"),
        ]
        classifier.classify(issues)
        for issue in issues:
            assert issue.risk_level == "high", f"{issue.issue_type} should be high"

    def test_medium_issues(self):
        classifier = RiskClassifier()
        issues = [
            _make_issue("missing_bom_cabinet_no", cabinet_no="K1"),  # 有柜号不会被升级
            _make_issue("duplicate_bom_line"),
            _make_issue("invalid_material_quantity"),
            _make_issue("missing_cabinet_no", cabinet_no="K2"),
        ]
        classifier.classify(issues)
        for issue in issues:
            assert issue.risk_level == "medium", f"{issue.issue_type} should be medium (got {issue.risk_level})"

    def test_low_issues(self):
        classifier = RiskClassifier()
        issues = [
            _make_issue("long_lead_time"),
            _make_issue("missing_price"),
            _make_issue("pending_material_spec"),
            _make_issue("pending_material_brand"),
        ]
        classifier.classify(issues)
        for issue in issues:
            assert issue.risk_level == "low", f"{issue.issue_type} should be low"

    def test_info_issues(self):
        classifier = RiskClassifier()
        issues = [_make_issue("pending_marker")]
        classifier.classify(issues)
        assert issues[0].risk_level == "info"

    def test_unknown_type_defaults_to_info(self):
        classifier = RiskClassifier()
        issues = [_make_issue("some_new_check")]
        classifier.classify(issues)
        assert issues[0].risk_level == "info"


class TestEscalationRules:
    """上下文升级规则测试。"""

    def test_long_lead_breaker_escalated_to_medium(self):
        """长交期 + 断路器 → MEDIUM。"""
        classifier = RiskClassifier()
        issues = [_make_issue("long_lead_time", material_name="框架断路器")]
        classifier.classify(issues)
        assert issues[0].risk_level == "medium"
        assert issues[0].details.get("risk_escalated") is True

    def test_long_lead_contactor_escalated_to_medium(self):
        """长交期 + 接触器 → MEDIUM。"""
        classifier = RiskClassifier()
        issues = [_make_issue("long_lead_time", material_name="交流接触器")]
        classifier.classify(issues)
        assert issues[0].risk_level == "medium"

    def test_long_lead_non_critical_not_escalated(self):
        """长交期 + 非关键物料（如电缆）→ 保持 LOW。"""
        classifier = RiskClassifier()
        issues = [_make_issue("long_lead_time", material_name="电缆")]
        classifier.classify(issues)
        assert issues[0].risk_level == "low"

    def test_brand_conflict_widespread_escalated_to_critical(self):
        """品牌冲突 + 品牌数 > 3 → CRITICAL。"""
        classifier = RiskClassifier()
        issues = [_make_issue("brand_conflict", details={"brands_count": 5})]
        classifier.classify(issues)
        assert issues[0].risk_level == "critical"

    def test_brand_conflict_small_not_escalated(self):
        """品牌冲突 + 品牌数 <= 3 → HIGH（默认）。"""
        classifier = RiskClassifier()
        issues = [_make_issue("brand_conflict", details={"brands_count": 2})]
        classifier.classify(issues)
        assert issues[0].risk_level == "high"

    def test_missing_price_with_long_lead_escalated_to_high(self):
        """缺价 + 长交期 → HIGH。"""
        classifier = RiskClassifier()
        issues = [_make_issue("missing_price", details={"long_lead_time": True})]
        classifier.classify(issues)
        assert issues[0].risk_level == "high"

    def test_missing_bom_cabinet_unassigned_escalated_to_high(self):
        """无柜号 + UNASSIGNED → HIGH。"""
        classifier = RiskClassifier()
        issues = [_make_issue("missing_bom_cabinet_no", cabinet_no="UNASSIGNED")
                  ]
        classifier.classify(issues)
        assert issues[0].risk_level == "high"


class TestRiskDashboard:
    """RiskDashboard 构建测试。"""

    def test_empty_issues(self):
        classifier = RiskClassifier()
        dashboard = classifier.build_dashboard([])
        assert dashboard.total_issues == 0
        assert sum(dashboard.level_counts.values()) == 0

    def test_counts_by_level(self):
        classifier = RiskClassifier()
        issues = [
            _make_issue("missing_material_name"),  # critical
            _make_issue("brand_conflict"),          # high
            _make_issue("missing_price"),           # low
            _make_issue("pending_marker"),          # info
            _make_issue("missing_price"),           # low
        ]
        classifier.classify(issues)
        dashboard = classifier.build_dashboard(issues)

        assert dashboard.total_issues == 5
        assert dashboard.level_counts["critical"] == 1
        assert dashboard.level_counts["high"] == 1
        assert dashboard.level_counts["low"] == 2
        assert dashboard.level_counts["info"] == 1

    def test_escalated_items_captured(self):
        classifier = RiskClassifier()
        issues = [
            _make_issue("long_lead_time", material_name="塑壳断路器"),
            _make_issue("missing_price"),
        ]
        classifier.classify(issues)
        dashboard = classifier.build_dashboard(issues)

        assert len(dashboard.escalated_items) == 1
        assert dashboard.escalated_items[0]["issue_type"] == "long_lead_time"
        assert "risk_escalation_reasons" in dashboard.escalated_items[0]["reasons"][0] or \
            "_escalate_" in str(dashboard.escalated_items[0]["reasons"][0])


class TestCustomRiskMap:
    """自定义 risk_map 支持测试。"""

    def test_custom_map_overrides_default(self):
        custom = {"missing_material_name": RiskLevel.HIGH}
        classifier = RiskClassifier(risk_map=custom)
        issues = [_make_issue("missing_material_name")]
        classifier.classify(issues)
        assert issues[0].risk_level == "high"  # not critical
