"""PDF 源解析实现。

支持多种 PDF 类型的分层处理流水线：
1. 文本层检测（pdfminer）→ 有文本层的原生 PDF 直接抽取表格
2. 无文本层（CAD 矢量 PDF / 扫描件）→ Vision LLM OCR → ocrmypdf → Tesseract 多级回退
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List

from .base import ScaffoldFormatParser
from ..models import CabinetRecord, MaterialRecord, ProjectDocument, SourceRef


class PdfSourceParser(ScaffoldFormatParser):
    """PDF source parser with text-layer detection and optional Marker enhancement.

    For PDFs with extractable text layers, attempts Marker (local ML-based
    PDF→Markdown) for high-quality table extraction, falling back to pdfplumber
    if Marker is unavailable.

    For PDFs without text layers (CAD vector / scanned), delegate to
    PdfOcrParser for the Vision LLM → ocrmypdf → Tesseract chain.
    """

    input_kind = "pdf"
    source_format = "pdf"
    message = (
        "PDF parsing: text-layer detection + Marker enhancement (with ML) or "
        "pdfplumber fallback. CAD vector PDFs route to PdfOcrParser."
    )

    def supported_suffixes(self) -> set[str]:
        return {".pdf"}

    def parse(
        self,
        input_path: str,
        use_marker: bool = True,
    ) -> ProjectDocument:
        """Parse a PDF file.

        Args:
            input_path: Path to the PDF.
            use_marker: If True and text layer exists, use Marker for enhanced
                        table extraction (downloads ~5GB models on first use).

        Returns:
            ProjectDocument with metadata (and Marker tables if available).
        """
        path = Path(input_path)
        try:
            from pdfminer.high_level import extract_text  # noqa: F811
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

        tables_data: list[dict[str, Any]] | None = None
        marker_md: str = ""
        marker_applied: bool = False

        if has_text:
            if use_marker:
                # Try Marker first for best table extraction quality
                marker_result = self._try_marker_extraction(str(path))
                if marker_result is not None and marker_result.success:
                    marker_applied = True
                    marker_md = marker_result.markdown
                    tables_data = _marker_tables_to_sheets(marker_result.tables)
                else:
                    # Fallback to pdfplumber
                    tables_data = self._try_extract_tables_fast(str(path))
            else:
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
                "marker_applied": marker_applied,
                "marker_markdown_preview": marker_md[:500] if marker_md else "",
            },
        )

    # ------------------------------------------------------------------
    # Marker extraction
    # ------------------------------------------------------------------

    def _try_marker_extraction(self, file_path: str) -> Any | None:
        """Attempt enhanced extraction via Marker (local ML PDF→Markdown).

        Returns a MarkerResult on success, None if Marker is unavailable or fails.
        """
        try:
            from .marker_adapter import MarkerAdapter  # type: ignore
        except Exception:
            return None

        adapter = MarkerAdapter()
        if not adapter.is_available():
            return None

        return adapter.convert(file_path)

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

    多级回退策略（按优先级，兼顾成本与质量）：
    1. 文本层检测（继承自 PdfSourceParser）→ 有文本层 → Marker 增强提取
    2. Marker 本地 OCR（免费 CPU，即使无文本层也可尝试）
    3. Vision LLM OCR（GPT-4o / Claude Vision / Gemini）→ CAD 矢量 PDF 主力
    4. ocrmypdf → 为扫描件添加 OCR 文本层
    5. Tesseract → 传统 OCR 最终兜底

    控制参数：
    - ``ocr_fallback``: 是否启用 OCR 回退（默认 True）
    - ``vision_llm_enabled``: 是否启用 Vision LLM（默认 True）
    - ``marker_enabled``: 是否尝试 Marker 本地 OCR（默认 True，免费）
    - ``vision_llm_max_pages``: Vision LLM 最大处理页数（默认 10，控制成本）
    - 环境变量 ``VISION_LLM_PROVIDER`` / ``*_API_KEY`` 控制 LLM 后端选择
    """

    # --- Public API ---

    def parse(
        self,
        input_path: str,
        ocr_fallback: bool = True,
        vision_llm_enabled: bool = True,
        marker_enabled: bool = True,
        vision_llm_max_pages: int = 10,
    ) -> ProjectDocument:
        """Parse a PDF file through the multi-stage OCR pipeline.

        Args:
            input_path: Path to the PDF file.
            ocr_fallback: Enable OCR fallback chain if no text layer.
            vision_llm_enabled: Enable Vision LLM as the primary OCR path.
            marker_enabled: Enable Marker local OCR (free, CPU).
            vision_llm_max_pages: Max pages to send to Vision LLM (cost control).

        Returns:
            ProjectDocument with metadata populated by the best available path.
        """
        path = Path(input_path)

        # Stage 1: text-layer detection + Marker enhancement (from PdfSourceParser)
        base_doc = super().parse(input_path, use_marker=marker_enabled)
        if base_doc.metadata.get("has_text_layer") and base_doc.metadata.get("marker_applied"):
            return base_doc  # Marker enhanced extraction succeeded

        if base_doc.metadata.get("has_text_layer"):
            return base_doc  # Text layer found, tables extracted via pdfplumber

        if not ocr_fallback:
            return base_doc

        # Stage 2: Marker local OCR (free — try even on no-text-layer PDFs)
        if marker_enabled and not base_doc.metadata.get("marker_applied"):
            marker_result = self._try_marker_ocr(str(path))
            if marker_result is not None:
                return marker_result

        # Stage 3: Vision LLM (primary paid path for CAD vector PDFs)
        if vision_llm_enabled:
            vision_result = self._try_vision_llm_ocr(
                str(path), base_doc, max_pages=vision_llm_max_pages
            )
            if vision_result is not None:
                return vision_result

        # Stage 4: ocrmypdf (good for scanned documents)
        ocrmypdf_result = self._try_ocrmypdf(str(path))
        if ocrmypdf_result is not None:
            return ocrmypdf_result

        # Stage 5: Tesseract (traditional OCR, final fallback)
        tesseract_result = self._try_tesseract(str(path), base_doc)
        return tesseract_result

    # --- OCR stage implementations ---

    def _try_marker_ocr(self, file_path: str) -> ProjectDocument | None:
        """Try Marker local OCR for any PDF (text or no text layer).

        Marker renders pages internally and can extract text even from
        PDFs without explicit text layers, though quality varies.
        """
        try:
            from .marker_adapter import MarkerAdapter  # type: ignore
        except Exception:
            return None

        adapter = MarkerAdapter()
        if not adapter.is_available():
            return None

        result = adapter.convert(file_path)
        if not result.success:
            return None

        # Convert Marker tables to sheets format
        tables_data = _marker_tables_to_sheets(result.tables)

        path = Path(file_path)
        return ProjectDocument(
            project_name=path.stem or "project",
            files=[file_path],
            metadata={
                "input_kind": "pdf",
                "parse_status": "ok",
                "source_format": "pdf",
                "has_text_layer": False,
                "ocr_applied": "marker",
                "plain_text_preview": result.plain_text[:500] if result.plain_text else "",
                "marker_markdown_preview": result.markdown[:500] if result.markdown else "",
                "page_count": result.page_count,
                "table_count": len(tables_data) if tables_data else 0,
                "sheets": tables_data if tables_data else None,
            },
        )

    # --- OCR stage implementations ---

    def _try_vision_llm_ocr(
        self,
        file_path: str,
        base_doc: ProjectDocument,
        max_pages: int = 10,
    ) -> ProjectDocument | None:
        """Render PDF pages → Vision LLM for structured extraction.

        Returns a ProjectDocument enriched with cabinet/material data in
        metadata, or None if Vision LLM is unavailable or fails.
        """
        # Check if any Vision LLM provider is configured
        configured_providers = _detect_vision_llm_providers()
        if not configured_providers:
            return None

        try:
            import pdf2image  # type: ignore
        except Exception:
            return None

        try:
            images = pdf2image.convert_from_path(file_path, dpi=300)
        except Exception:
            return None

        if not images:
            return None

        # Limit pages to control API cost
        page_count = min(len(images), max_pages)
        all_cabinets: List[Any] = []
        all_materials: List[Any] = []
        all_annotations: List[str] = []
        page_summaries: List[str] = []
        ocr_applied: str = ""
        total_usage: dict[str, int] = {}

        from .vision_llm import VisionLLMExtractor

        extractor = VisionLLMExtractor()

        for page_idx in range(page_count):
            try:
                result = extractor.extract_from_image(
                    images[page_idx],
                    page_no=page_idx + 1,
                    source_path=file_path,
                )
                if result.success:
                    all_cabinets.extend(result.cabinets)
                    all_materials.extend(result.materials)
                    all_annotations.extend(result.annotations)
                    if result.page_summary:
                        page_summaries.append(f"p{result.page_no}: {result.page_summary}")
                    if result.model_used:
                        ocr_applied = f"vision_llm/{result.model_used}"
                    for k, v in (result.usage or {}).items():
                        total_usage[k] = total_usage.get(k, 0) + v
            except Exception:
                # Single page failure shouldn't block other pages
                continue

        if not all_cabinets and not all_materials and not all_annotations:
            return None  # No useful data extracted — let next stage try

        # Serialize structured records to metadata
        cabinets_data = [
            {
                "cabinet_no": c.cabinet_no,
                "cabinet_type": c.cabinet_type,
                "rated_current": c.rated_current,
                "dimensions": c.dimensions,
                "circuit_count": c.circuit_count,
                "grounding_mode": c.grounding_mode,
                "confidence": c.confidence,
                "remarks": c.remarks,
            }
            for c in all_cabinets
        ]
        materials_data = [
            {
                "name": m.name,
                "spec": m.spec,
                "unit": m.unit,
                "quantity": m.quantity,
                "brand": m.brand,
                "confidence": m.confidence,
                "remarks": m.remarks,
            }
            for m in all_materials
        ]

        return ProjectDocument(
            project_name=Path(file_path).stem or "project",
            files=[file_path],
            metadata={
                "input_kind": "pdf",
                "parse_status": "ok",
                "source_format": "pdf",
                "has_text_layer": False,
                "ocr_applied": ocr_applied or "vision_llm",
                "page_count_processed": page_count,
                "total_pages": len(images),
                "vision_llm_cabinets": cabinets_data,
                "vision_llm_materials": materials_data,
                "vision_llm_annotations": all_annotations,
                "vision_llm_page_summaries": page_summaries,
                "vision_llm_usage": total_usage,
            },
        )

    def _try_ocrmypdf(self, file_path: str) -> ProjectDocument | None:
        """Attempt to add OCR text layer via ocrmypdf."""
        try:
            import ocrmypdf  # type: ignore
        except Exception:
            return None

        import tempfile
        import shutil

        path = Path(file_path)
        tmp_dir = tempfile.mkdtemp(prefix="ocr_")
        out_path = Path(tmp_dir) / (path.stem + "-ocr.pdf")
        try:
            try:
                ocrmypdf.ocr(str(path), str(out_path))
            except TypeError:
                ocrmypdf.ocr(str(path), str(out_path))

            try:
                from pdfminer.high_level import extract_text
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
            pass
        finally:
            try:
                shutil.rmtree(tmp_dir)
            except Exception:
                pass

        return None

    def _try_tesseract(
        self, file_path: str, base_doc: ProjectDocument
    ) -> ProjectDocument:
        """Traditional Tesseract OCR as final fallback."""
        try:
            from .ocr_adapter import TesseractAdapter

            ocr_result = TesseractAdapter.pdf_to_dict(file_path)
            plain = ocr_result.get("plain_text", "")
            pages = ocr_result.get("pages", [])
            return ProjectDocument(
                project_name=Path(file_path).stem or "project",
                files=[file_path],
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
            meta = dict(base_doc.metadata)
            meta.update({"ocr_attempted": False, "ocr_error": str(e)})
            return ProjectDocument(
                project_name=Path(file_path).stem or "project",
                files=[file_path],
                metadata=meta,
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_vision_llm_providers() -> List[str]:
    """Return list of Vision LLM providers that have API keys configured."""
    available: List[str] = []
    if os.environ.get("OPENAI_API_KEY"):
        available.append("openai")
    if os.environ.get("ANTHROPIC_API_KEY"):
        available.append("anthropic")
    if os.environ.get("GOOGLE_API_KEY"):
        available.append("google")
    return available


def _marker_tables_to_sheets(tables: List[Any]) -> list[dict[str, Any]] | None:
    """Convert MarkerTable objects to the sheets format used by the pipeline.

    The sheets format matches what pdfplumber's _try_extract_tables_fast produces,
    ensuring downstream consumers work with either source.
    """
    if not tables:
        return None
    sheets: list[dict[str, Any]] = []
    for i, table in enumerate(tables):
        headers = getattr(table, 'headers', []) or []
        rows = getattr(table, 'rows', []) or []
        if not rows:
            continue
        records = []
        for row_num, row in enumerate(rows, start=1):
            record = {"_sheet_name": f"marker_table_{i}", "_row_no": row_num}
            non_empty = 0
            for j, header in enumerate(headers):
                if header and j < len(row) and row[j]:
                    val = str(row[j]).strip()
                    if val:
                        record[header] = val
                        non_empty += 1
            if non_empty >= 2:
                records.append(record)
        if records:
            sheets.append({
                "name": f"marker_table_{i}",
                "row_count": len(rows),
                "data_row_count": len(records),
                "column_count": len(headers),
                "headers": headers,
                "records": records,
            })
    return sheets if sheets else None