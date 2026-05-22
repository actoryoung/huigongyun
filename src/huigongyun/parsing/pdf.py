from __future__ import annotations

from .base import ScaffoldFormatParser


class PdfSourceParser(ScaffoldFormatParser):
    """PDF source adapter skeleton.

    Input boundary: .pdf files only.
    Future implementation: text extraction, table reconstruction, OCR fallback,
    and page-level layout analysis for scanned documents.
    """

    input_kind = "pdf"
    source_format = "pdf"
    message = "PDF parsing is reserved for later OCR, text extraction, and layout analysis."

    def supported_suffixes(self) -> set[str]:
        return {".pdf"}