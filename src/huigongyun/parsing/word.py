from __future__ import annotations

from .base import ScaffoldFormatParser


class WordSourceParser(ScaffoldFormatParser):
    """Word source adapter skeleton.

    Input boundary: .doc and .docx files only.
    Future implementation: paragraph extraction, table extraction, technical
    constraint mining, and citation/provenance retention.
    """

    input_kind = "word"
    source_format = "word"
    message = "Word parsing is reserved for later document text extraction and constraint mining."

    def supported_suffixes(self) -> set[str]:
        return {".doc", ".docx"}