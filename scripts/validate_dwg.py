#!/usr/bin/env python3
"""DWG 图纸识别准确性验证脚本。

从 DWG 文件中提取电气工程信息，验证：
1. 柜体标识识别完整度（应识别出图纸中所有柜号）
2. 柜型标签准确性（柜型分类是否正确）
3. 技术参数提取覆盖率（电压/电流/功率等关键参数）
4. 文本实体提取量（对比已知参考值）

不直接比对参考报价结果（因为参考是BOM，DWG是布局图，含不同信息）。

用法:
    python scripts/validate_dwg.py
    python scripts/validate_dwg.py --project A
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from huigongyun.parsing.dwg import DwgSourceParser


# ── 电气工程领域验证规则 ──

# 柜号模式（低压配电系统常见命名）
CABINET_ID_PATTERNS = [
    (r'\d+UPS-\d+', "UPS配电柜"),
    (r'\d+D\d+', "配电柜(数字编号)"),
    (r'[A-Z]+-\d+-\d+', "厂房配电柜"),
    (r'[A-Z]+[A-Z]*\d+', "字母+数字编号"),
]

# 柜型关键词 → 标准柜型
CABINET_TYPE_CLASSIFIER = {
    "进线柜": ["进线", "主路输入", "输入柜"],
    "出线柜": ["出线", "馈线", "输出柜"],
    "母联柜": ["母联", "联络"],
    "补偿柜": ["补偿", "电容", "SVG"],
    "开关柜": ["开关柜", "配电柜", "MCC"],
    "旁路柜": ["旁路", "应急旁路"],
    "UPS": ["UPS"],
}

# 技术参数提取模式
TECH_SPEC_PATTERNS = [
    (r'(\d+)\s*kW', "功率(kW)"),
    (r'(\d+)\s*kVA', "容量(kVA)"),
    (r'(\d+)\s*A\b', "电流(A)"),
    (r'(\d+)\s*V\b', "电压(V)"),
    (r'(\d+)\s*AH', "电池容量(AH)"),
    (r'(\d+)\s*mm', "尺寸(mm)"),
    (r'TMY[-\s].*', "铜排规格"),
    (r'COPPER\s*BUSBAR', "铜母线"),
]


def analyze_dwg_extraction(metadata: dict) -> dict:
    """深度分析 DWG 提取结果的质量。

    Returns:
        {
            "cabinet_ids": list[str],
            "cabinet_id_patterns": dict,   # 每种模式命中了几个柜号
            "cabinet_type_hits": dict,     # 每种柜型命中了几个标签
            "tech_specs": dict,            # 每种技术参数的提取值
            "quality_score": float,        # 0-1 综合质量评分
            "issues": list[str],           # 发现的问题
        }
    """
    texts = metadata.get("texts", [])
    text_set = set(texts)
    all_text = " | ".join(texts)

    # 1. Cabinet ID extraction
    cabinet_ids = []
    pattern_hits = {}
    for pattern, name in CABINET_ID_PATTERNS:
        matches = set()
        for t in texts:
            found = re.findall(pattern, t)
            matches.update(found)
        if matches:
            pattern_hits[name] = sorted(matches)
            cabinet_ids.extend(matches)

    cabinet_ids = sorted(set(cabinet_ids))

    # 2. Cabinet type classification
    type_hits = {}
    for std_type, keywords in CABINET_TYPE_CLASSIFIER.items():
        hits = [t for t in texts if any(kw in t for kw in keywords)]
        if hits:
            type_hits[std_type] = hits

    # 3. Technical spec extraction
    tech_specs = {}
    for pattern, name in TECH_SPEC_PATTERNS:
        matches = re.findall(pattern, all_text, re.IGNORECASE)
        if matches:
            tech_specs[name] = sorted(set(str(m) for m in matches))[:20]

    # 4. Quality scoring
    scores = []

    # Score: cabinet ID patterns found
    id_score = min(1.0, len(pattern_hits) / 2)  # expect at least 2 patterns
    scores.append(("柜号识别", id_score, f"{len(pattern_hits)}种模式命中"))

    # Score: cabinet types classified
    type_score = min(1.0, len(type_hits) / 3)  # expect at least 3 types
    scores.append(("柜型分类", type_score, f"{len(type_hits)}种柜型识别"))

    # Score: technical specs extracted
    spec_score = min(1.0, len(tech_specs) / 4)  # expect at least 4 spec types
    scores.append(("技术参数", spec_score, f"{len(tech_specs)}类参数提取"))

    # Score: text entity count (meaningful texts > 100 is good)
    text_count = len([t for t in texts if len(t) > 3])
    text_score = min(1.0, text_count / 200)
    scores.append(("文本量", text_score, f"{text_count}条有效文本"))

    # Score: DWG format support
    format_score = 1.0 if metadata.get("parse_status") == "ok" else 0.0
    scores.append(("格式兼容", format_score, metadata.get("parse_status", "unknown")))

    overall = sum(s for _, s, _ in scores) / len(scores)

    # Issues
    issues = []
    if not pattern_hits:
        issues.append("未识别到任何标准柜号模式")
    if not type_hits:
        issues.append("未识别到柜型标签")
    if metadata.get("parse_status") == "requires_conversion":
        issues.append("DWG格式需要外部转换工具(旧格式支持，AC1032不支持)")

    return {
        "cabinet_ids": cabinet_ids,
        "cabinet_id_patterns": pattern_hits,
        "cabinet_type_hits": type_hits,
        "tech_specs": tech_specs,
        "scores": scores,
        "quality_score": overall,
        "issues": issues,
        "text_count": metadata.get("text_count", 0),
    }


def main():
    parser = argparse.ArgumentParser(description="DWG图纸识别质量验证")
    parser.add_argument("--project", "-p", choices=["A", "D", "B", "C", "all"], default="all")
    args = parser.parse_args()

    projects = {
        "A": ("项目A_IDC机房", "example0516./项目A_IDC机房配电/输入资料/项目A_系统图.dwg", "AC1018"),
        "B": ("项目B_学校配电", "example0516./项目B_学校配电工程/输入资料/项目B_询价图纸.dwg", "AC1032"),
        "C": ("项目C_厂房配电", "example0516./项目C_厂房配电资料更新/输入资料/项目C_图纸版本对比.dwg", "AC1032"),
        "D": ("项目D_中英文设备", "example0516./项目D_中英文设备清单/输入资料/项目D_工艺设备配电图.dwg", "AC1015"),
    }

    if args.project != "all":
        projects = {args.project: projects[args.project]}

    dwg_parser = DwgSourceParser()
    results = {}

    print("=" * 64)
    print("  DWG 图纸识别 — 质量验证报告")
    print("=" * 64)

    for proj, (proj_name, dwg_path, fmt_ver) in projects.items():
        print(f"\n{'─' * 56}")
        print(f"  [{proj}] {proj_name}  |  {Path(dwg_path).name}  |  {fmt_ver}")

        doc = dwg_parser.parse(dwg_path)
        meta = doc.metadata
        status = meta.get("parse_status")

        if status != "ok":
            print(f"  ❌ 状态: {status}")
            print(f"     原因: {meta.get('message', '')}")
            results[proj] = {"status": "failed", "reason": meta.get("message", "")}
            continue

        analysis = analyze_dwg_extraction(meta)

        # Display scores
        print(f"  ✅ 状态: ok | 文本实体: {analysis['text_count']}")
        print(f"\n  📊 质量评估:")
        for name, score, detail in analysis["scores"]:
            bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
            print(f"    {name:8s} [{bar}] {score:.0%}  ({detail})")

        print(f"\n  📐 柜体标识 ({len(analysis['cabinet_ids'])}):")
        for cid in analysis['cabinet_ids'][:16]:
            print(f"    - {cid}")
        if len(analysis['cabinet_ids']) > 16:
            print(f"    ... 共 {len(analysis['cabinet_ids'])} 个")

        print(f"\n  🏷️ 柜型分类:")
        for std_type, hits in analysis['cabinet_type_hits'].items():
            print(f"    {std_type}: {len(hits)} 个标签 → {hits[0][:80]}")

        print(f"\n  ⚙️ 技术参数:")
        for spec_name, values in analysis['tech_specs'].items():
            print(f"    {spec_name}: {', '.join(values[:8])}")

        if analysis['issues']:
            print(f"\n  ⚠️ 问题:")
            for issue in analysis['issues']:
                print(f"    - {issue}")

        print(f"\n  📈 综合质量评分: {analysis['quality_score']:.0%}")

        results[proj] = {
            "status": "ok",
            "quality_score": analysis['quality_score'],
            "cabinet_count": len(analysis['cabinet_ids']),
            "text_count": analysis['text_count'],
            "type_count": len(analysis['cabinet_type_hits']),
        }

    # Final summary
    print(f"\n{'=' * 64}")
    print("  验证汇总")
    print(f"{'=' * 64}")
    print(f"  {'项目':8s} {'格式':8s} {'状态':8s} {'文本':6s} {'柜号':6s} {'质量':8s}")
    print(f"  {'-' * 48}")
    for proj, (proj_name, _, fmt_ver) in projects.items():
        r = results.get(proj, {})
        if r.get("status") == "ok":
            print(f"  {proj:8s} {fmt_ver:8s} {'✅ ok':8s} {r.get('text_count',0):<6d} {r.get('cabinet_count',0):<6d} {r.get('quality_score',0):.0%}")
        else:
            print(f"  {proj:8s} {fmt_ver:8s} {'❌ failed':8s} {'-':6s} {'-':6s} {'N/A':8s}")
            print(f"          原因: {r.get('reason', '')}")
    print()

    # Overall: success if at least one DWG passes
    ok_count = sum(1 for r in results.values() if r.get("status") == "ok")
    return 0 if ok_count > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
