#!/usr/bin/env python3
"""低压电气成套智能报价清单生成系统 — 演示脚本。

一键运行：对样例项目B执行全流程处理，展示解析→柜体→BOM→报价→校验→导出结果。

用法:
    python scripts/demo.py                          # 默认处理项目B
    python scripts/demo.py --project C              # 处理项目C
    python scripts/demo.py --project B --web        # 处理后启动Web界面
    python scripts/demo.py --input path/to/file.xlsx  # 处理自定义Excel

输出：
    - demo_output/ 目录下的 JSON 和 Excel 结果文件
    - 控制台摘要报告
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

# Ensure the src directory is on the path
# 把第 27 行改为指向项目根目录
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bootstrap import build_default_pipeline, build_context
from src.parsing.word import WordSourceParser

try:
    from src.parsing.constraint_extractor import TechnicalConstraintExtractor

    _HAS_CONSTRAINT = True
except Exception:
    _HAS_CONSTRAINT = False

# ── Project configuration ────────────────────────────────────────────
PROJECTS = {
    "A": {
        "name": "项目A_IDC机房配电",
        "excel": None,
        "word": None,
        "pdf": "example0516./项目A_IDC机房配电/输入资料/项目A_系统图.pdf",
    },
    "B": {
        "name": "项目B_学校配电工程",
        "excel": "example0516./项目B_学校配电工程/输入资料/项目B_主元件清单.xlsx",
        "word": "example0516./项目B_学校配电工程/输入资料/项目B_报价说明.docx",
        "pdf": "example0516./项目B_学校配电工程/输入资料/项目B_询价图纸.pdf",
    },
    "C": {
        "name": "项目C_厂房配电资料更新",
        "excel": "example0516./项目C_厂房配电资料更新/输入资料/项目C_主元器件清单.xlsx",
        "word": "example0516./项目C_厂房配电资料更新/输入资料/项目C_配置说明.docx",
    },
    "D": {
        "name": "项目D_中英文设备清单",
        "excel": "example0516./项目D_中英文设备清单/输入资料/项目D_设备清单_20250701.xlsx",
        "word": None,
    },
}


def run_pipeline(input_path: str, output_dir: str) -> dict:
    """Run the full quotation pipeline and return summary dict."""
    pipeline = build_default_pipeline()
    context = build_context(
        input_path=str(Path(input_path).resolve()),
        output_dir=str(Path(output_dir).resolve()),
    )
    result = pipeline.run(context)
    return _build_demo_summary(result)


def process_word_constraints(word_path: str) -> dict | None:
    """Extract technical constraints from a Word document."""
    if not word_path or not Path(word_path).exists():
        return None
    parser = WordSourceParser()
    doc = parser.parse(str(Path(word_path).resolve()))
    constraints = (
        doc.metadata.get("constraints") if isinstance(doc.metadata, dict) else None
    )
    if constraints:
        return {
            "status": "ok",
            "count": constraints.get("constraint_count", 0),
            "cabinet_type": constraints.get("cabinet_type"),
            "ip_rating": constraints.get("ip_rating"),
            "dimensions": constraints.get("dimensions"),
            "specified_brands": constraints.get("specified_brands", []),
            "frame_breaker": constraints.get("frame_breaker"),
            "mccb": constraints.get("mccb"),
            "meter_incomer": constraints.get("meter_incomer"),
            "surge_protection": constraints.get("surge_protection"),
        }
    if _HAS_CONSTRAINT:
        # Try direct extraction if Word parser didn't include constraints
        para_texts = []
        for p in doc.metadata.get("paragraphs", []):
            para_texts.append(p if isinstance(p, str) else str(p))
        if para_texts:
            extractor = TechnicalConstraintExtractor()
            cr = extractor.extract(para_texts)
            return {
                "status": "ok",
                "count": len(cr.constraints),
                "cabinet_type": cr.cabinet_type,
                "ip_rating": cr.ip_rating,
                "specified_brands": cr.specified_brands,
            }
    return None


def _build_demo_summary(result) -> dict:
    """Extract demo-worthy summary from a ProjectResult."""
    proj = result.project
    issue_counts = Counter(iss.issue_type for iss in result.issues)

    # Top materials by quantity
    top_materials = []
    for m in sorted(result.summary, key=lambda x: x.quantity, reverse=True)[:10]:
        top_materials.append(
            {
                "name": m.normalized_name or m.name,
                "spec": m.spec or "",
                "brand": m.brand or "",
                "quantity": m.quantity,
                "unit": m.unit or "",
            }
        )

    # Brand distribution
    brands = Counter(m.brand or m.manufacturer for m in result.summary)

    return {
        "project_name": proj.project_name,
        "cabinet_count": len(result.cabinets),
        "bom_line_count": len(result.bom_lines),
        "summary_count": len(result.summary),
        "quote_line_count": len(result.quote_lines),
        "issue_count": len(result.issues),
        "issue_breakdown": dict(issue_counts.most_common(10)),
        "top_materials": top_materials,
        "brand_distribution": dict(brands.most_common(10)),
        "quote_totals": result.quote_totals,
        "cabinets": [
            {
                "no": c.cabinet_no,
                "type": c.cabinet_type,
                "dimensions": c.dimensions,
                "quantity": c.quantity,
            }
            for c in result.cabinets[:10]
        ],
        "outputs": result.outputs,
    }


def print_report(demo_summary: dict, word_info: dict | None = None) -> None:
    """Print a formatted console report."""
    sep = "=" * 64
    print(f"\n{sep}")
    print(f"  低压电气成套智能报价清单生成系统 — Demo Report")
    print(f"{sep}")
    print(f"  项目: {demo_summary['project_name']}")

    if word_info and word_info.get("count"):
        print(f"\n  📋 技术约束抽取 (Word):")
        print(f"     约束数量: {word_info['count']}")
        if word_info.get("cabinet_type"):
            print(f"     柜型: {word_info['cabinet_type']}")
        if word_info.get("ip_rating"):
            print(f"     防护等级: {word_info['ip_rating']}")
        if word_info.get("specified_brands"):
            print(f"     指定品牌: {', '.join(word_info['specified_brands'][:5])}")

    print(f"\n  📊 解析结果:")
    print(f"     柜体数: {demo_summary['cabinet_count']}")
    print(f"     BOM 行: {demo_summary['bom_line_count']}")
    print(f"     汇总物料: {demo_summary['summary_count']}")
    print(f"     报价行: {demo_summary['quote_line_count']}")
    print(f"     校验问题: {demo_summary['issue_count']}")
    if demo_summary["issue_breakdown"]:
        print(f"     问题分类: {demo_summary['issue_breakdown']}")

    print(f"\n  🏭 柜体列表 (前10):")
    for c in demo_summary.get("cabinets", [])[:10]:
        print(
            f"     {c['no']:12s} | 类型={c['type'] or '?'} | 尺寸={c['dimensions'] or '?'} | 数量={c['quantity']}"
        )

    print(f"\n  📦 物料汇总 (Top 10):")
    for i, m in enumerate(demo_summary.get("top_materials", []), 1):
        print(
            f"     {i:2d}. {m['name']:20s} {m['spec']:30s} | {m['brand']:8s} | x{m['quantity']} {m['unit']}"
        )

    print(f"\n  🏷️ 品牌分布:")
    for brand, cnt in demo_summary.get("brand_distribution", {}).items():
        print(f"     {brand}: {cnt}")

    qt = demo_summary.get("quote_totals", {})
    if qt:
        print(f"\n  💰 报价摘要:")
        print(f"     价格表大小: {qt.get('price_table_size', 0)}")
        print(f"     缺价物料: {qt.get('missing_price_count', 0)}")
        if qt.get("project_total", 0) > 0:
            print(f"     项目总价: ¥{qt['project_total']:,.2f}")

    print(f"\n  📁 导出文件:")
    for key, path in demo_summary.get("outputs", {}).items():
        print(f"     {key}: {path}")
    print(f"{sep}\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="低压电气成套智能报价清单生成系统 — Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--project",
        "-p",
        choices=list(PROJECTS.keys()),
        default="B",
        help="选择样例项目 (default: B)",
    )
    parser.add_argument("--input", "-i", help="直接指定输入文件路径")
    parser.add_argument(
        "--output",
        "-o",
        default="./demo_output",
        help="输出目录 (default: ./demo_output)",
    )
    parser.add_argument("--no-word", action="store_true", help="跳过 Word 约束抽取")
    args = parser.parse_args()

    # Determine input path
    if args.input:
        input_path = args.input
        proj_key = None
    else:
        proj_key = args.project
        proj = PROJECTS[proj_key]
        if proj["excel"]:
            input_path = proj["excel"]
        else:
            print(f"项目 {proj_key} 没有 Excel 输入文件。", file=sys.stderr)
            return 1

    if not Path(input_path).exists():
        print(f"输入文件不存在: {input_path}", file=sys.stderr)
        return 1

    output_dir = Path(args.output) / Path(input_path).stem
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"🚀 开始处理: {input_path}")
    print(f"📂 输出目录: {output_dir}")

    # Step 1: Excel pipeline
    print(f"\n📊 Step 1: Excel 解析与流水线...")
    summary = run_pipeline(input_path, str(output_dir))

    # Step 2: Word constraint extraction (if applicable)
    word_info = None
    if not args.no_word and proj_key in PROJECTS and PROJECTS[proj_key].get("word"):
        word_path = PROJECTS[proj_key]["word"]
        if Path(word_path).exists():
            print(f"📝 Step 2: Word 技术约束抽取...")
            word_info = process_word_constraints(word_path)
            if word_info:
                # Save constraint results
                constraint_file = output_dir / "constraints.json"
                constraint_file.write_text(
                    json.dumps(word_info, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

    # Step 3: Save summary
    summary_file = output_dir / "demo_summary.json"
    summary_file.write_text(
        json.dumps(
            {"pipeline": summary, "word_constraints": word_info},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    # Print report
    print_report(summary, word_info)

    print(f"✅ 演示完成。所有产物已保存到: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
