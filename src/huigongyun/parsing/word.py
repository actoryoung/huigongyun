"""Word 文档解析占位实现。

当前为占位解析器，声明对 .doc/.docx 的支持，未来将实现段落与表格抽取、
技术约束挖掘及引用/来源信息的保留。
"""

from __future__ import annotations

from .base import ScaffoldFormatParser


class WordSourceParser(ScaffoldFormatParser):
    """Word 源解析器占位骨架。

    输入边界：仅支持 .doc 与 .docx 文件。
    未来实现：段落抽取、表格抽取、技术约束挖掘与来源保留。
    """

    input_kind = "word"
    source_format = "word"
    message = "Word 解析保留用于后续的文档文本抽取与约束挖掘实现。"

    def supported_suffixes(self) -> set[str]:
        return {".doc", ".docx"}