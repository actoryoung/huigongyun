#!/usr/bin/env python3
"""Simple CLI to run the TesseractAdapter on an image or PDF and print JSON."""
import argparse
import json
import sys

from src.parsing.ocr_adapter import TesseractAdapter


def main():
    p = argparse.ArgumentParser(description='OCR PoC runner')
    p.add_argument('input', help='Image or PDF path')
    p.add_argument('--dpi', type=int, default=300, help='DPI for PDF rendering')
    args = p.parse_args()

    path = args.input
    if path.lower().endswith('.pdf'):
        out = TesseractAdapter.pdf_to_dict(path, dpi=args.dpi)
    else:
        out = TesseractAdapter.image_to_dict(path)

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
