"""跨源融合校验：对比 Excel / Word / DWG 三个解析器的产出。

提供：
- `extract_cabinet_numbers_from_texts()` — 从 DWG 原始文本中提取柜号
- `CrossSourceValidatorMixin` — 5 条跨源校验规则，可混入 `DefaultProjectValidator`
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from ..models import ProjectResult, ValidationIssue, SourceRef


# ── 柜号提取 ──────────────────────────────────────────────────────────

# 常见柜号前缀（低压配电柜/控制柜/配电箱命名惯例）
_CABINET_PREFIXES = (
    r"AL|AP|AT|AA|AC|AH|AN|AW|"
    r"K|P|MCC|UPS|EPS|DP|SP|CP|IP|JP|PLC|"
    r"EL|EP|ET|ES|"
    r"1AL|2AL|3AL|1AP|2AP|3AP|"
    r"B1AL|B1AP|B2AL|B2AP"
)

_CABINET_RE = re.compile(
    rf"(?<![A-Za-z0-9])"   # 前边界：不能是字母或数字
    rf"({_CABINET_PREFIXES})"
    rf"\d{{1,3}}"            # 柜号后缀数字
    rf"(?![A-Za-z0-9])",    # 后边界
)

# 排除模式：匹配但不是柜号的文本
_EXCLUDE_PATTERNS = re.compile(
    r"NSX\d{1,3}|CVS\d{1,3}|EZD\d{1,3}|"
    r"iC65N|iDPN|iPRD|iCT|iOF|iMX|"
    r"TMY-\d|TMY\d|"
    r"mm2|mm\b|A\b|V\b|kW\b|kVA\b",
    re.IGNORECASE,
)


def extract_cabinet_numbers_from_texts(texts: list[str]) -> set[str]:
    """从 DWG/DXF 文本列表中提取柜号集合。

    使用电气柜号命名惯例正则匹配，并排除已知的电气型号干扰。
    """
    cabinet_numbers: set[str] = set()
    for text in texts:
        for match in _CABINET_RE.finditer(text):
            candidate = match.group(0)
            # 排除已知型号
            if not _EXCLUDE_PATTERNS.fullmatch(candidate):
                cabinet_numbers.add(candidate)
    return cabinet_numbers


# ── 跨源校验混入类 ───────────────────────────────────────────────────

class CrossSourceValidatorMixin:
    """跨源校验规则混入类。

    5 条规则，每条独立方法，只在其依赖数据可用时运行。
    入口：`_validate_cross_source(result)`。
    """

    # ── 入口 ──────────────────────────────────────────────────────────

    def _validate_cross_source(self, result: ProjectResult) -> list[ValidationIssue]:
        """按可用数据依次运行全部跨源规则。"""
        issues: list[ValidationIssue] = []

        metadata = result.project.metadata
        if not isinstance(metadata, dict):
            return issues

        # Word 约束规则
        constraints = metadata.get("constraints", {})
        constraint_rules: dict[str, Any] = (
            constraints.get("validation_rules", {})
            if isinstance(constraints, dict)
            else {}
        )

        # DWG 电气文本
        dwg_texts: list[str] = metadata.get("electrical_texts", [])
        if not isinstance(dwg_texts, list):
            dwg_texts = []

        # 1. 柜号一致性（DWG ↔ Excel）
        if dwg_texts:
            issues.extend(self._validate_cabinet_number_consistency(result, dwg_texts))

        # 2. 柜型一致性（Word → Cabinet）
        if constraint_rules.get("expected_cabinet_type"):
            issues.extend(self._validate_cabinet_type_consistency(result, constraint_rules))

        # 3. 品牌合规性（Word → BOM）
        if constraint_rules.get("preferred_brands"):
            issues.extend(self._validate_brand_compliance(result, constraint_rules))

        # 4. IP 等级 / 接地方式（Word → Cabinet）
        if constraint_rules.get("expected_ip_rating") or constraint_rules.get("expected_grounding_mode"):
            issues.extend(self._validate_ip_grounding_consistency(result, constraint_rules))

        # 5. 保护配置匹配（Word → BOM 物料型号）
        if (constraint_rules.get("frame_breaker")
                or constraint_rules.get("mccb")
                or constraint_rules.get("busbar_specification")):
            issues.extend(self._validate_protection_configuration(result, constraint_rules))

        return issues

    # ── 规则 1：柜号一致性 ────────────────────────────────────────────

    def _validate_cabinet_number_consistency(
        self, result: ProjectResult, dwg_texts: list[str]
    ) -> list[ValidationIssue]:
        """检查 DWG 图纸中出现的柜号与 Excel 中的柜号是否一致。"""
        issues: list[ValidationIssue] = []

        dwg_cabinets = extract_cabinet_numbers_from_texts(dwg_texts)
        if not dwg_cabinets:
            return issues

        excel_cabinets = {c.cabinet_no for c in result.cabinets if c.cabinet_no and c.cabinet_no != "UNASSIGNED"}

        # DWG 有但 Excel 没有 —— 可能是遗漏的柜体
        missing_in_excel = dwg_cabinets - excel_cabinets
        for cab in sorted(missing_in_excel):
            issues.append(ValidationIssue(
                issue_type="cross_source_cabinet_mismatch",
                severity="warning",
                message=f"图纸中存在柜号 {cab}，但在 Excel 清单中未找到对应柜体",
                cabinet_no=cab,
                details={"in_source": "dwg", "not_in": "excel"},
                source=SourceRef(file_name="(dwg)", file_type="dwg"),
            ))

        # Excel 有但 DWG 没有 —— 可能是 DWG 提取不全（info 级别）
        missing_in_dwg = excel_cabinets - dwg_cabinets
        for cab in sorted(missing_in_dwg):
            issues.append(ValidationIssue(
                issue_type="cross_source_cabinet_mismatch",
                severity="info",
                message=f"Excel 清单中存在柜号 {cab}，但在图纸文本中未识别到",
                cabinet_no=cab,
                details={"in_source": "excel", "not_in": "dwg"},
                source=SourceRef(file_name="(excel)", file_type="excel"),
            ))

        return issues

    # ── 规则 2：柜型一致性 ────────────────────────────────────────────

    def _validate_cabinet_type_consistency(
        self, result: ProjectResult, constraint_rules: dict[str, Any]
    ) -> list[ValidationIssue]:
        """检查 CabinetRecord.cabinet_type 与 Word 约束中的期望柜型是否一致。"""
        issues: list[ValidationIssue] = []

        expected = constraint_rules.get("expected_cabinet_type", "")
        if not expected:
            return issues

        expected_norm = _normalize_cabinet_type(expected)

        for cabinet in result.cabinets:
            actual = (cabinet.cabinet_type or "").strip()
            if not actual or actual == "unknown":
                continue
            actual_norm = _normalize_cabinet_type(actual)
            if actual_norm != expected_norm:
                issues.append(ValidationIssue(
                    issue_type="cross_source_cabinet_type_mismatch",
                    severity="warning",
                    message=f"柜体 {cabinet.cabinet_no} 的柜型为 {actual}，与配置说明要求的 {expected} 不一致",
                    cabinet_no=cabinet.cabinet_no,
                    details={"expected": expected, "actual": actual},
                    source=cabinet.sources[0] if cabinet.sources else None,
                ))

        return issues

    # ── 规则 3：品牌合规性 ────────────────────────────────────────────

    def _validate_brand_compliance(
        self, result: ProjectResult, constraint_rules: dict[str, Any]
    ) -> list[ValidationIssue]:
        """检查 BOM 中使用的品牌是否符合 Word 约束中的推荐品牌列表。

        - 读取 ``normalized_brand``（兜底了类别推断的品牌）
        - ``brand_source="inferred"`` 的辅助器件降为 info
        - "国产"/"甲供" 等占位符如无法推断则跳过（已在归一化层处理）
        """
        issues: list[ValidationIssue] = []

        preferred_raw: list[str] = constraint_rules.get("preferred_brands", [])
        if not preferred_raw:
            return issues
        preferred = {_normalize_brand(b) for b in preferred_raw}

        # 统计非推荐品牌（按 normalized_brand 聚合）
        non_preferred: Counter = Counter()
        for bom in result.bom_lines:
            effective = (
                bom.material.normalized_brand
                or (bom.material.brand or "").strip()
            )
            if not effective:
                continue
            brand_norm = _normalize_brand(effective)
            if brand_norm not in preferred:
                brand_source = getattr(bom.material, "brand_source", "explicit")
                non_preferred[(effective, brand_norm, brand_source)] += 1

        for (original, _norm, source), count in non_preferred.items():
            severity = "warning"
            # 推断品牌 + 非关键器件 → info
            if source == "inferred":
                severity = "info"

            issues.append(ValidationIssue(
                issue_type="cross_source_brand_non_compliance",
                severity=severity,
                message=f"物料使用了非推荐品牌：{original}（出现 {count} 次），推荐品牌：{', '.join(preferred_raw)}",
                cabinet_no=None,
                material_name=original,
                details={
                    "brand": original,
                    "count": count,
                    "preferred_brands": preferred_raw,
                    "brand_source": source,
                },
            ))

        return issues

    # ── 规则 4：IP 等级 / 接地方式一致性 ──────────────────────────────

    def _validate_ip_grounding_consistency(
        self, result: ProjectResult, constraint_rules: dict[str, Any]
    ) -> list[ValidationIssue]:
        """检查柜体的 IP 等级 / 接地方式是否与 Word 约束一致。"""
        issues: list[ValidationIssue] = []

        expected_ip = constraint_rules.get("expected_ip_rating", "")
        expected_grounding = constraint_rules.get("expected_grounding_mode", "")

        for cabinet in result.cabinets:
            # IP 等级
            if expected_ip:
                actual_ip = (cabinet.remarks or "")
                # IP 等级主要在 remark 中或需从柜体字段推断；当前 CabinetRecord 无 ip_rating 字段
                # 如果无数据可比较，不产生问题
                pass

            # 接地方式
            if expected_grounding:
                actual_grounding = (cabinet.grounding_mode or "").strip().upper()
                if not actual_grounding:
                    issues.append(ValidationIssue(
                        issue_type="cross_source_grounding_mismatch",
                        severity="info",
                        message=f"柜体 {cabinet.cabinet_no} 未标注接地方式，配置说明要求 {expected_grounding}",
                        cabinet_no=cabinet.cabinet_no,
                        details={"expected": expected_grounding, "actual": None},
                        source=cabinet.sources[0] if cabinet.sources else None,
                    ))
                elif actual_grounding != expected_grounding.upper().replace("-", "").replace("_", ""):
                    issues.append(ValidationIssue(
                        issue_type="cross_source_grounding_mismatch",
                        severity="warning",
                        message=f"柜体 {cabinet.cabinet_no} 接地方式 {actual_grounding} 与配置说明要求 {expected_grounding} 不一致",
                        cabinet_no=cabinet.cabinet_no,
                        details={"expected": expected_grounding, "actual": actual_grounding},
                        source=cabinet.sources[0] if cabinet.sources else None,
                    ))

        return issues

    # ── 规则 5：保护配置匹配 ──────────────────────────────────────────

    def _validate_protection_configuration(
        self, result: ProjectResult, constraint_rules: dict[str, Any]
    ) -> list[ValidationIssue]:
        """检查 BOM 中保护器件型号是否与 Word 约束指定的一致。

        当前实现：对 frame_breaker / mccb / busbar_spec 做关键词包含检查。
        """
        issues: list[ValidationIssue] = []

        checks = [
            ("frame_breaker", "框架断路器", constraint_rules.get("frame_breaker", "")),
            ("mccb", "塑壳断路器", constraint_rules.get("mccb", "")),
            ("busbar_specification", "铜排/母线", constraint_rules.get("busbar_specification", "")),
        ]

        for rule_key, label, expected_spec in checks:
            if not expected_spec:
                continue
            keywords = _extract_keywords(expected_spec)

            # 在 BOM 中查找相关物料类别
            for bom in result.bom_lines:
                name = (bom.material.normalized_name or bom.material.name or "").lower()
                if not _matches_category(name, rule_key):
                    continue

                spec = (bom.material.normalized_spec or bom.material.spec or "").lower()
                if not any(kw.lower() in spec for kw in keywords):
                    issues.append(ValidationIssue(
                        issue_type="cross_source_protection_mismatch",
                        severity="warning",
                        message=f"{label} 型号 {bom.material.spec} 与配置说明要求 {expected_spec} 可能不匹配",
                        cabinet_no=bom.cabinet_no,
                        material_name=bom.material.name,
                        details={
                            "category": label,
                            "expected": expected_spec,
                            "actual_spec": bom.material.spec,
                        },
                        source=bom.material.source,
                    ))
                    break  # 每类只报一条

        return issues


# ── 辅助函数 ──────────────────────────────────────────────────────────

def _normalize_cabinet_type(value: str) -> str:
    """归一化柜型名称为比较用键。

    剥离约束文本中的描述性前缀（如 "柜体采用Blokset" → "BLOKSET"）。
    """
    v = value.strip().upper().replace(" ", "").replace("_", "").replace("-", "")
    # 剥离常见描述性前缀
    for prefix in ["柜体型采用", "柜体采用", "柜型采用", "采用", "柜型为", "柜体型"]:
        if v.startswith(prefix):
            v = v[len(prefix):]
            break
    v = v.replace("柜", "").replace("型", "")
    return v


def _normalize_brand(value: str) -> str:
    """归一化品牌名称为比较用键。"""
    return value.strip().lower().replace(" ", "").replace("-", "")


def _extract_keywords(spec: str) -> list[str]:
    """从规格文本中提取关键词用于型号匹配。"""
    # 例如 "MT系列" → ["mt"]，"TMY-80×8" → ["tmy", "80×8"]
    parts = re.split(r"[，,、\s]+", spec)
    return [p.strip() for p in parts if p.strip()]


def _matches_category(material_name: str, rule_key: str) -> bool:
    """判断物料名称是否属于指定器件类别。"""
    category_map = {
        "frame_breaker": ["框架", "acb", "mccb", "空气断路器", "万能断路器"],
        "mccb": ["塑壳", "mccb", "断路器"],
        "busbar_specification": ["铜排", "母线", "母排", "busbar", "tmy"],
    }
    keywords = category_map.get(rule_key, [])
    return any(kw in material_name for kw in keywords)
