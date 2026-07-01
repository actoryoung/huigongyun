#!/usr/bin/env python3
"""历史检索 RAG 演示脚本 — 索引示例项目并执行相似案例搜索。

用法::

    PYTHONPATH=. python scripts/demo_retrieval.py
    PYTHONPATH=. python scripts/demo_retrieval.py --index path/to/input.xlsx
    PYTHONPATH=. python scripts/demo_retrieval.py --query "断路器 施耐德"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def resolve_path(rel: str) -> Path:
    return Path(__file__).resolve().parent.parent / rel


def main():
    parser = argparse.ArgumentParser(
        description="索引示例项目并执行历史案例检索"
    )
    parser.add_argument(
        "--index", default=None,
        help="要索引的输入文件或目录（默认: 项目B Excel）"
    )
    parser.add_argument(
        "--query", default="断路器 施耐德",
        help="自由文本搜索查询（默认: '断路器 施耐德'）"
    )
    parser.add_argument(
        "--output", default="output/retrieval",
        help="输出目录"
    )
    parser.add_argument(
        "--save", default=None,
        help="保存索引到指定路径前缀"
    )
    parser.add_argument(
        "--load", default=None,
        help="从指定路径前缀加载索引"
    )
    args = parser.parse_args()

    # 延迟导入 — 避免加载重型依赖直到需要
    from src.bootstrap import build_context, build_default_pipeline

    # 检查检索依赖
    try:
        from src.retrieval import (
            CaseIndexer,
            FaissCaseRetriever,
            SentenceTransformerProvider,
        )
    except ImportError as e:
        print(f"错误: 检索依赖未安装: {e}")
        print("请运行: pip install faiss-cpu sentence-transformers")
        sys.exit(1)

    # 初始化 embedding provider
    print("正在加载嵌入模型 (all-MiniLM-L6-v2)...")
    try:
        provider = SentenceTransformerProvider()
    except ImportError as e:
        print(f"错误: {e}")
        sys.exit(1)
    print(f"  模型已就绪，维数: {provider.dimension}")

    retriever = FaissCaseRetriever(provider)
    if not retriever.is_available:
        print("错误: FAISS 索引初始化失败。请安装 faiss-cpu。")
        sys.exit(1)
    print("  FAISS 检索器已就绪")

    # 加载或构建索引
    if args.load:
        print(f"\n正在从 {args.load} 加载索引...")
        retriever.load(args.load)
        print(f"  已加载 {retriever.case_count} 个案例")
    else:
        # 确定输入文件
        if args.index:
            input_path = args.index
        else:
            input_path = str(
                resolve_path("examples/项目B_学校配电工程/输入资料/项目B_主元件清单.xlsx")
            )
        p = Path(input_path)
        if not p.exists():
            print(f"警告: 输入文件不存在: {input_path}")
            print("使用项目 B Excel 作为演示或通过 --index 指定路径。")
            sys.exit(1)

        print(f"\n正在索引: {input_path}")
        pipeline = build_default_pipeline()
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)

        with __import__("tempfile").TemporaryDirectory() as tmpdir:
            ctx = build_context(str(p), tmpdir)
            result = pipeline.run(ctx)
        print(f"  已解析: {len(result.bom_lines)} BOM 行, {len(result.summary)} 汇总物料")

        indexer = CaseIndexer()
        cases = indexer.index_project(result)
        print(f"  已创建 {len(cases)} 个索引案例")

        retriever.index_cases(cases)
        print(f"  已索引 {retriever.case_count} 个案例")

        if args.save:
            retriever.save(args.save)
            print(f"  索引已保存至: {args.save}.faiss / {args.save}.json")

    # 执行搜索
    print(f"\n搜索查询: '{args.query}'")
    results = retriever.search({"material_name": args.query}, top_k=5)

    if not results:
        print("  无结果。索引可能为空。")
    else:
        for i, hit in enumerate(results, 1):
            print(f"  {i}. [{hit.score:.3f}] {hit.case_id}")
            print(f"     {hit.summary}")
            if hit.payload:
                details = {k: v for k, v in hit.payload.items()
                          if v is not None and k in ("material_name", "spec", "brand", "cabinet_no")}
                print(f"     {json.dumps(details, ensure_ascii=False)}")

    print("\n检索演示完成。")


if __name__ == "__main__":
    main()
