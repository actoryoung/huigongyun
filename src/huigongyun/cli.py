"""用于运行 Huigongyun 流水线的命令行接口。

提供一个简洁的包装，用于对指定输入运行流水线并将结果概要打印到 stdout，
主要用于本地测试与演示场景。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .bootstrap import build_context, build_default_pipeline


def build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器。

    返回：配置好的 `argparse.ArgumentParser`。
    """
    parser = argparse.ArgumentParser(prog="huigongyun", description="Low-voltage quotation MVP scaffold")
    parser.add_argument("input", nargs="?", default='.', help="Input file or folder path")
    parser.add_argument("--output-dir", default="./output", help="Directory for generated artifacts")
    return parser


def main() -> int:
    """`python -m huigongyun` 或控制台脚本的入口点。

    运行默认流水线并打印简要结果概要。
    """
    args = build_parser().parse_args()
    pipeline = build_default_pipeline()
    context = build_context(input_path=str(Path(args.input).resolve()), output_dir=str(Path(args.output_dir).resolve()))
    result = pipeline.run(context)
    print(f"project={result.project.project_name}")
    print(f"cabinets={len(result.cabinets)} bom_lines={len(result.bom_lines)} issues={len(result.issues)}")
    print(f"outputs={result.outputs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
