#!/usr/bin/env python3
"""版本差异演示脚本 — 对比项目 D 两个 Excel 版本的物料清单。

用法::

    PYTHONPATH=. python scripts/demo_version_diff.py
    PYTHONPATH=. python scripts/demo_version_diff.py --output output/version_diff/
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path


def resolve_path(rel: str) -> Path:
    """Resolve a path relative to the project root."""
    return Path(__file__).resolve().parent.parent / rel


def main():
    parser = argparse.ArgumentParser(
        description="比对项目 D 两个版本的设备清单并输出差异报告"
    )
    parser.add_argument(
        "--output", default="output/version_diff",
        help="差异报告输出目录（默认: output/version_diff）"
    )
    parser.add_argument(
        "--old", default=None,
        help="旧版本 Excel 路径（默认: 项目D_设备清单_20250701.xlsx）"
    )
    parser.add_argument(
        "--new", default=None,
        help="新版本 Excel 路径（默认: 项目D_设备清单_新版.xlsx）"
    )
    args = parser.parse_args()

    # 确定输入文件
    examples_dir = resolve_path("examples/项目D_中英文设备清单/输入资料")
    old_path = Path(args.old) if args.old else examples_dir / "项目D_设备清单_20250701.xlsx"
    new_path = Path(args.new) if args.new else examples_dir / "项目D_设备清单_新版.xlsx"

    if not old_path.exists():
        print(f"错误: 旧版本文件不存在: {old_path}")
        sys.exit(1)
    if not new_path.exists():
        print(f"错误: 新版本文件不存在: {new_path}")
        sys.exit(1)

    print(f"旧版本: {old_path}")
    print(f"新版本: {new_path}")
    print()

    # 延迟导入，避免启动时加载重型依赖
    from huigongyun.bootstrap import build_context, build_default_pipeline
    from huigongyun.comparison.differ import VersionDiffer

    # 构建流水线
    pipeline = build_default_pipeline()

    import tempfile

    # 解析旧版本
    print("正在解析旧版本...")
    with tempfile.TemporaryDirectory() as tmpdir:
        ctx_old = build_context(str(old_path), tmpdir)
        result_old = pipeline.run(ctx_old)
    print(f"  柜体: {len(result_old.cabinets)}, BOM行: {len(result_old.bom_lines)}, "
          f"汇总: {len(result_old.summary)}, 问题: {len(result_old.issues)}")

    # 解析新版本
    print("正在解析新版本...")
    with tempfile.TemporaryDirectory() as tmpdir:
        ctx_new = build_context(str(new_path), tmpdir)
        result_new = pipeline.run(ctx_new)
    print(f"  柜体: {len(result_new.cabinets)}, BOM行: {len(result_new.bom_lines)}, "
          f"汇总: {len(result_new.summary)}, 问题: {len(result_new.issues)}")

    # 执行差异比较
    print("\n正在生成差异报告...")
    differ = VersionDiffer()
    diff = differ.compare(result_old, result_new,
                          old_label=old_path.stem, new_label=new_path.stem)

    # 输出汇总
    added_bom = sum(1 for c in diff.bom_changes if c.change_type == "added")
    removed_bom = sum(1 for c in diff.bom_changes if c.change_type == "removed")
    changed_bom = sum(1 for c in diff.bom_changes if c.change_type == "changed")

    added_cab = sum(1 for c in diff.cabinet_changes if c.change_type == "added")
    removed_cab = sum(1 for c in diff.cabinet_changes if c.change_type == "removed")
    changed_cab = sum(1 for c in diff.cabinet_changes if c.change_type == "changed")

    print(f"\n=== 差异汇总 ===")
    print(f"柜体: +{added_cab} -{removed_cab} ~{changed_cab}")
    print(f"BOM行: +{added_bom} -{removed_bom} ~{changed_bom}")
    print(f"汇总物料差异: {len(diff.summary_changes)}")
    print(f"报价行差异: {len(diff.quote_changes)}")

    print(f"\n旧版本指标: {json.dumps(diff.old_metrics, ensure_ascii=False)}")
    print(f"新版本指标: {json.dumps(diff.new_metrics, ensure_ascii=False)}")

    # 输出详细差异报告
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    diff_dict = asdict(diff)
    report_path = output_dir / "version_diff.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(diff_dict, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n差异报告已保存至: {report_path}")

    # 同时保存两个版本的流水线结果
    for label, result, stem in [
        ("old", result_old, old_path.stem),
        ("new", result_new, new_path.stem),
    ]:
        from dataclasses import asdict as dc_asdict
        result_path = output_dir / f"{stem}_pipeline_result.json"
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(dc_asdict(result), f, ensure_ascii=False, indent=2, default=str)
        print(f"流水线结果已保存至: {result_path}")

    print("\n版本差异演示完成。")


if __name__ == "__main__":
    main()
