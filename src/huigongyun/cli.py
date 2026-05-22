from __future__ import annotations

import argparse
from pathlib import Path

from .bootstrap import build_context, build_default_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="huigongyun", description="Low-voltage quotation MVP scaffold")
    parser.add_argument("input", nargs="?", default=".", help="Input file or folder path")
    parser.add_argument("--output-dir", default="./output", help="Directory for generated artifacts")
    return parser


def main() -> int:
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
