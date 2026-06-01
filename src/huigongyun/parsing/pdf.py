"""PDF 源解析占位实现。

当前为占位适配器：仅声明文件后缀并在未来扩展为文本抽取、表格重建、
OCR 回退与页面级布局分析等功能。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import ScaffoldFormatParser
from ..models import ProjectDocument


class PdfSourceParser(ScaffoldFormatParser):
    """PDF 源解析器：包含文本层检测和可选的 pdfminer.six 抽取。

    行为：当环境中可用 `pdfminer.six` 时会尝试读取少量页面的文本以判断
    文档是否包含可抽取的文本层；若未安装依赖则回退到占位实现，确保注册表
    的行为稳定。
    """

    input_kind = "pdf"
    source_format = "pdf"
    message = "PDF 解析：尝试检测文本层（需要 pdfminer.six），缺失依赖时回退。"

    def supported_suffixes(self) -> set[str]:
        return {".pdf"}

    def parse(self, input_path: str) -> ProjectDocument:
        path = Path(input_path)
        try:
            # lazy import pdfminer
            from pdfminer.high_level import extract_text
        except Exception:
            return super().parse(input_path)

        try:
            text = extract_text(str(path), maxpages=1)
        except Exception:
            return ProjectDocument(
                project_name=path.stem or "project",
                files=[str(path)],
                metadata={
                    "input_kind": "pdf",
                    "parse_status": "error",
                    "source_format": "pdf",
                    "message": "Failed to extract text from PDF using pdfminer.",
                },
            )

        has_text = bool(text and text.strip())
        return ProjectDocument(
            project_name=path.stem or "project",
            files=[str(path)],
            metadata={
                "input_kind": "pdf",
                "parse_status": "ok" if has_text else "scanned",
                "source_format": "pdf",
                "has_text_layer": has_text,
                "plain_text_preview": (text.strip()[:200] if has_text else ""),
            },
        )


class PdfOcrParser(PdfSourceParser):
    """PDF OCR 流水线解析器。

    行为：优先检测文本层（继承自 `PdfSourceParser`）；若文档无文本层且
    允许回退，则尝试通过 `ocrmypdf` 为 PDF 添加文本层；若 `ocrmypdf` 不可用，
    则回退到 `TesseractAdapter` 的基于图像的 OCR。所有外部依赖均为可选，
    在缺失时保持优雅回退并在 `metadata` 中记录过程信息。
    """

    def parse(self, input_path: str, ocr_fallback: bool = True) -> ProjectDocument:
        path = Path(input_path)

        # First pass: use PdfSourceParser detection
        base_doc = super().parse(input_path)
        if base_doc.metadata.get("has_text_layer"):
            return base_doc

        if not ocr_fallback:
            return base_doc

        # Try ocrmypdf first
        try:
            import ocrmypdf  # type: ignore
        except Exception:
            ocrmypdf = None  # type: ignore

        if ocrmypdf is not None:
            import tempfile
            import shutil

            tmp_dir = tempfile.mkdtemp(prefix="ocr_")
            out_path = Path(tmp_dir) / (path.stem + "-ocr.pdf")
            try:
                # Use ocrmypdf to produce a searchable PDF
                try:
                    ocrmypdf.ocr(str(path), str(out_path))
                except TypeError:
                    # older/newer API differences; try positional
                    ocrmypdf.ocr(str(path), str(out_path))

                # Attempt to extract text from the OCR'd PDF
                try:
                    from pdfminer.high_level import extract_text  # type: ignore
                    text = extract_text(str(out_path), maxpages=1)
                    has_text = bool(text and text.strip())
                except Exception:
                    has_text = False

                if has_text:
                    return ProjectDocument(
                        project_name=path.stem or "project",
                        files=[str(path)],
                        metadata={
                            "input_kind": "pdf",
                            "parse_status": "ok",
                            "source_format": "pdf",
                            "has_text_layer": True,
                            "ocr_applied": "ocrmypdf",
                            "plain_text_preview": text.strip()[:200] if text else "",
                        },
                    )
            except Exception:
                # If ocrmypdf fails, continue to next fallback
                pass
            finally:
                try:
                    shutil.rmtree(tmp_dir)
                except Exception:
                    pass

        # Fallback: use TesseractAdapter to OCR images of the PDF
        try:
            from .ocr_adapter import TesseractAdapter  # type: ignore

            ocr_result = TesseractAdapter.pdf_to_dict(str(path))
            plain = ocr_result.get("plain_text", "")
            pages = ocr_result.get("pages", [])
            return ProjectDocument(
                project_name=path.stem or "project",
                files=[str(path)],
                metadata={
                    "input_kind": "pdf",
                    "parse_status": "ok",
                    "source_format": "pdf",
                    "has_text_layer": False,
                    "ocr_applied": "tesseract",
                    "plain_text_preview": plain[:200],
                    "ocr_page_count": len(pages),
                },
            )
        except Exception as e:
            # All OCR attempts failed; return base doc annotated with error
            meta = dict(base_doc.metadata)
            meta.update({"ocr_attempted": False, "ocr_error": str(e)})
            return ProjectDocument(project_name=path.stem or "project", files=[str(path)], metadata=meta)