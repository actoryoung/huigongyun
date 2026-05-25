"""DWG/DXF 格式解析占位实现。

当前为占位解析器，声明对 .dwg/.dxf 文件的支持。未来可扩展为将图纸
转换或渲染为图像/PDF、绘图区域检测以及几何到文本的抽取。
"""

from __future__ import annotations

from .base import ScaffoldFormatParser


class DwgSourceParser(ScaffoldFormatParser):
    """DWG/DXF 源解析器占位骨架。

    输入边界：仅 .dwg 与 .dxf 文件。
    未来实现：转换/渲染、区域检测与图形到文本的抽取。
    """

    input_kind = "dwg"
    source_format = "dwg"
    message = "DWG 解析保留用于后续的转换、渲染与图形抽取实现。"

    def supported_suffixes(self) -> set[str]:
        return {".dwg", ".dxf"}