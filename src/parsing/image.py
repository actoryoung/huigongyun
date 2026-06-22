"""图像解析占位实现。

当前为占位适配器，声明对常见栅格图像格式的支持。未来将加入 OCR、纠偏、
区域检测、图注解析及图像到文本的来源映射功能。
"""

from __future__ import annotations

from .base import ScaffoldFormatParser


class ImageSourceParser(ScaffoldFormatParser):
    """图像源解析器占位骨架。

    输入边界：常见栅格图像格式。
    未来实现：OCR、去倾斜、区域检测、图注解析与来源映射。
    """

    input_kind = "image"
    source_format = "image"
    message = "图像解析保留用于后续的 OCR 与布局分析实现。"

    def supported_suffixes(self) -> set[str]:
        return {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}