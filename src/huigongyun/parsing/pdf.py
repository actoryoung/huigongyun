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
    """PDF 源解析器（接口保留，暂不深入实现）。

    当前仅做文本层检测：用 pdfminer 读取首页文本判断是否包含可抽取文本层。
    CAD 矢量 PDF（无文本层/编码乱码）暂不处理，优先投入 DWG→DXF 文本提取。

    行为：当环境中可用 `pdfminer.six` 时会尝试读取少量页面的文本以判断
    文档是否包含可抽取的文本层；若未安装依赖则回退到占位实现。
    """

    input_kind = "pdf"
    source_format = "pdf"
    message = "PDF 解析接口保留：文本层检测可用，CAD矢量PDF暂不处理，优先使用DWG→DXF方案。"

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

        # For pages with text, try quick table extraction (first page only for speed)
        tables_data: list[dict[str, Any]] | None = None
        if has_text:
            tables_data = self._try_extract_tables_fast(str(path))

        return ProjectDocument(
            project_name=path.stem or "project",
            files=[str(path)],
            metadata={
                "input_kind": "pdf",
                "parse_status": "ok" if (has_text or tables_data) else "scanned",
                "source_format": "pdf",
                "has_text_layer": has_text,
                "plain_text_preview": (text.strip()[:200] if has_text else ""),
                "table_count": len(tables_data) if tables_data else 0,
                "sheets": tables_data if tables_data else None,
            },
        )

    def _try_extract_tables_fast(self, path: str) -> list[dict[str, Any]] | None:
        """Quick table extraction from first few pages of a text-layer PDF.

        Uses pdfplumber with a page limit to avoid timeout on large drawing PDFs.
        """
        try:
            import pdfplumber  # type: ignore
        except Exception:
            return None

        sheets: list[dict[str, Any]] = []
        try:
            pdf = pdfplumber.open(path)
            # Only scan first 3 pages for tables (drawings have many pages but tables are rare)
            for page_num, page in enumerate(pdf.pages[:3], start=1):
                tables = page.extract_tables()
                if not tables:
                    continue
                for table_idx, table in enumerate(tables):
                    if not table or len(table) < 2:
                        continue
                    headers = [str(cell or "").strip() for cell in table[0]]
                    records = []
                    for row_num, row in enumerate(table[1:], start=2):
                        record = {"_sheet_name": f"pdf_p{page_num}_t{table_idx}", "_row_no": row_num}
                        non_empty = 0
                        for i, header in enumerate(headers):
                            if header and i < len(row) and row[i] is not None:
                                val = str(row[i]).strip()
                                if val:
                                    record[header] = val
                                    non_empty += 1
                        if non_empty >= 2:
                            records.append(record)
                    if records:
                        sheets.append({
                            "name": f"pdf_page{page_num}_table{table_idx}",
                            "row_count": len(table),
                            "data_row_count": len(records),
                            "column_count": len(headers),
                            "headers": headers,
                            "records": records,
                        })
        except Exception:
            pass
        finally:
            try:
                pdf.close()
            except Exception:
                pass

        return sheets if sheets else None


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