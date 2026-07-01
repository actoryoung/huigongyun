"""风险分级模块 — 在现有校验结果上叠加风险等级标签。

提供 ``RiskLevel`` 枚举、``RiskClassifier``（默认映射 + 上下文升级规则）
和 ``RiskDashboard`` 汇总数据类。

使用方式::

    from huigongyun.validation.risk import RiskClassifier, RiskLevel

    classifier = RiskClassifier()
    graded = classifier.classify(result.issues, result)
    dashboard = classifier.build_dashboard(graded)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    """风险等级枚举。值继承 str 以确保 JSON 序列化兼容。"""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# ---------------------------------------------------------------------------
# 默认映射：issue_type → RiskLevel
# ---------------------------------------------------------------------------
_DEFAULT_RISK_MAP: dict[str, RiskLevel] = {
    # Critical — 阻塞性错误，必须修复
    "missing_material_name": RiskLevel.CRITICAL,
    "missing_cabinet": RiskLevel.CRITICAL,

    # High — 严重影响输出质量
    "brand_conflict": RiskLevel.HIGH,
    "duplicate_cabinet": RiskLevel.HIGH,
    "invalid_cabinet_quantity": RiskLevel.HIGH,

    # Medium — 需要关注，但可能不影响核心流程
    "missing_bom_cabinet_no": RiskLevel.MEDIUM,
    "duplicate_bom_line": RiskLevel.MEDIUM,
    "invalid_material_quantity": RiskLevel.MEDIUM,
    "missing_cabinet_no": RiskLevel.MEDIUM,
    # 跨源融合校验
    "cross_source_cabinet_mismatch": RiskLevel.MEDIUM,
    "cross_source_cabinet_type_mismatch": RiskLevel.MEDIUM,
    "cross_source_grounding_mismatch": RiskLevel.MEDIUM,
    "cross_source_ip_mismatch": RiskLevel.MEDIUM,
    "cross_source_protection_mismatch": RiskLevel.MEDIUM,

    # Low — 提示性信息，通常不需要立即处理
    "long_lead_time": RiskLevel.LOW,
    "missing_price": RiskLevel.LOW,
    "pending_material_spec": RiskLevel.LOW,
    "pending_material_brand": RiskLevel.LOW,
    "cross_source_brand_non_compliance": RiskLevel.LOW,

    # Info — 纯信息性标记
    "pending_marker": RiskLevel.INFO,
}


@dataclass(slots=True)
class RiskDashboard:
    """风险仪表盘 — 聚合统计与升级项明细。"""

    level_counts: dict[str, int] = field(default_factory=dict)
    escalated_items: list[dict[str, Any]] = field(default_factory=list)
    total_issues: int = 0


class RiskClassifier:
    """对 ValidationIssue 列表进行风险分级。

    两阶段处理：
    1. 默认映射：根据 ``issue_type`` 分配基础 RiskLevel
    2. 上下文升级：应用升级规则，根据项目上下文提升风险等级
    """

    #                                                                    等级阈值
    _LEVEL_ORDER: dict[RiskLevel, int] = {
        RiskLevel.INFO: 0,
        RiskLevel.LOW: 1,
        RiskLevel.MEDIUM: 2,
        RiskLevel.HIGH: 3,
        RiskLevel.CRITICAL: 4,
    }

    # ── 上下文升级规则 ──────────────────────────────────────────────
    # 每条规则是一个可调用对象，接受 (issue, result) 返回 RiskLevel | None。
    # 返回 None 表示不触发升级；返回 RiskLevel 则触发升级（仅当新等级 > 当前等级）。

    def _escalate_long_lead_critical_material(
        self, issue: Any, _result: Any
    ) -> RiskLevel | None:
        """长交期 + 关键物料 → 中等风险。"""
        if issue.issue_type != "long_lead_time":
            return None
        name = (issue.material_name or "").lower()
        critical_keywords = ["断路器", "框架断路器", "接触器", "塑壳断路器"]
        if any(kw in name for kw in critical_keywords):
            return RiskLevel.MEDIUM
        return None

    def _escalate_brand_conflict_widespread(
        self, issue: Any, result: Any
    ) -> RiskLevel | None:
        """品牌冲突 + 受影响行数 > 3 → 严重风险。"""
        if issue.issue_type != "brand_conflict":
            return None
        affected_count = issue.details.get("brands_count", 0)
        if affected_count > 3:
            return RiskLevel.CRITICAL
        return None

    def _escalate_missing_price_plus_lead(
        self, issue: Any, result: Any
    ) -> RiskLevel | None:
        """缺价 + 长交期物料 → 高风险。"""
        if issue.issue_type != "missing_price":
            return None
        # Check if this quote line has a long_lead_time flag in its source material
        is_long = issue.details.get("long_lead_time", False)
        if is_long:
            return RiskLevel.HIGH
        return None

    def _escalate_unassigned_cabinet(
        self, issue: Any, _result: Any
    ) -> RiskLevel | None:
        """BOM 行无柜号 + cabinet_no == UNASSIGNED → 高风险。"""
        if issue.issue_type != "missing_bom_cabinet_no":
            return None
        if issue.cabinet_no == "UNASSIGNED" or not issue.cabinet_no:
            return RiskLevel.HIGH
        return None

    # 规则列表
    _ESCALATION_RULES = [
        _escalate_long_lead_critical_material,
        _escalate_brand_conflict_widespread,
        _escalate_missing_price_plus_lead,
        _escalate_unassigned_cabinet,
    ]

    def __init__(self, risk_map: dict[str, RiskLevel] | None = None):
        """初始化分类器。

        Args:
            risk_map: 可选的自定义 issue_type → RiskLevel 映射，
                      默认使用 ``_DEFAULT_RISK_MAP``。
        """
        self._risk_map = risk_map or dict(_DEFAULT_RISK_MAP)

    def classify(self, issues: list[Any], result: Any = None) -> list[Any]:
        """对问题列表进行风险分级（原地修改）。

        Args:
            issues: ValidationIssue 列表
            result: 可选的 ProjectResult，供上下文升级规则使用

        Returns:
            同一列表（已原地修改 risk_level 字段）
        """
        for issue in issues:
            # 阶段 1：默认映射
            default_level = self._risk_map.get(
                issue.issue_type, RiskLevel.INFO
            )
            issue.risk_level = default_level.value

            # 阶段 2：上下文升级
            for rule_fn in self._ESCALATION_RULES:
                escalated = rule_fn(self, issue, result)
                if escalated is not None:
                    current_order = self._LEVEL_ORDER.get(
                        RiskLevel(issue.risk_level), 0
                    )
                    escalated_order = self._LEVEL_ORDER[escalated]
                    if escalated_order > current_order:
                        issue.risk_level = escalated.value
                        # 在 details 中记录升级信息
                        issue.details["risk_escalated"] = True
                        issue.details.setdefault(
                            "risk_escalation_reasons", []
                        ).append(rule_fn.__name__)

        return issues

    def build_dashboard(self, issues: list[Any]) -> RiskDashboard:
        """构建风险仪表盘 — 按等级聚合统计。

        Args:
            issues: 已分级的 ValidationIssue 列表

        Returns:
            RiskDashboard 包含各级别计数和升级项明细
        """
        counts: dict[str, int] = {level.value: 0 for level in RiskLevel}
        escalated: list[dict[str, Any]] = []

        for issue in issues:
            level = getattr(issue, "risk_level", RiskLevel.INFO.value)
            counts[level] = counts.get(level, 0) + 1

            if issue.details.get("risk_escalated"):
                escalated.append({
                    "issue_type": issue.issue_type,
                    "risk_level": level,
                    "severity": issue.severity,
                    "message": issue.message,
                    "cabinet_no": issue.cabinet_no,
                    "reasons": issue.details.get("risk_escalation_reasons", []),
                })

        return RiskDashboard(
            level_counts=counts,
            escalated_items=escalated,
            total_issues=len(issues),
        )
