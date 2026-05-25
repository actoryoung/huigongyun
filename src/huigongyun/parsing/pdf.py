"""PDF 源解析占位实现。

当前为占位适配器：仅声明文件后缀并在未来扩展为文本抽取、表格重建、
OCR 回退与页面级布局分析等功能。
"""

from __future__ import annotations

from .base import ScaffoldFormatParser


class PdfSourceParser(ScaffoldFormatParser):
    """PDF 源适配器占位骨架。

    输入边界：仅 .pdf 文件。
    未来实现：文本抽取、表格重建、OCR 回退及扫描文档的布局分析。
    """

    input_kind = "pdf"
    source_format = "pdf"
    message = "PDF 解析保留用于后续的 OCR、文本抽取与布局分析实现。"

    def supported_suffixes(self) -> set[str]:
        return {".pdf"}