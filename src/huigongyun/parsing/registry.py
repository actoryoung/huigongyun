from __future__ import annotations

"""源解析器注册表与格式适配器。

提供解析器查找与按优先级选择解析器的机制，并包含针对 Excel/PDF/Word/
Image/DWG 的适配器与回退占位实现。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..models import ProjectDocument
from .excel import ExcelProjectParser
from .pdf import PdfSourceParser
from .word import WordSourceParser
from .image import ImageSourceParser
from .dwg import DwgSourceParser


@runtime_checkable
class SourceParser(Protocol):
    def supports(self, input_path: str) -> bool:
        """当解析器能处理给定输入路径时返回 True。

        边界：仅负责格式归属判断，不应包含实现特定的业务逻辑。
        """

    def parse(self, input_path: str) -> ProjectDocument:
        """将源文件解析为共享的 `ProjectDocument` 中间模型。

        边界：将单一格式解析为通用的项目文档脚手架。
        """


@dataclass(slots=True)
class SourceParserRegistry:
    parsers: list[SourceParser] = field(default_factory=list)

    def register(self, parser: SourceParser) -> None:
        """按优先级顺序注册格式解析器。"""
        self.parsers.append(parser)

    def select(self, input_path: str) -> SourceParser:
        """选择第一个明确认领输入后缀的解析器。"""
        for parser in self.parsers:
            if parser.supports(input_path):
                return parser
        return ScaffoldSourceParser()

    def parse(self, input_path: str) -> ProjectDocument:
        """通过被选中的解析器解析输入。"""
        return self.select(input_path).parse(input_path)


class ExcelSourceParser:
    """Excel 源适配器。

    输入边界：仅支持 .xlsx/.xlsm/.xltx/.xltm 工作簿文件。
    未来扩展：表格分类、更鲁棒的表格启发式算法、多工作簿项目包等。
    """

    def __init__(self) -> None:
        self._parser = ExcelProjectParser()

    def supports(self, input_path: str) -> bool:
        """仅认领 Excel 工作簿后缀。"""
        suffix = Path(input_path).suffix.lower()
        return suffix in {".xlsx", ".xlsm", ".xltx", ".xltm"}

    def parse(self, input_path: str) -> ProjectDocument:
        """委托给工作簿解析器并保留 Excel 的脚手架表示。"""
        return self._parser.parse(input_path)


class ScaffoldSourceParser:
    """未实现格式的回退解析器。

    说明：仅在没有专用解析器认领输入时使用此回退实现。返回的文档
    在 metadata 中带有明显的未实现标记。
    """

    def supports(self, input_path: str) -> bool:
        """对未匹配的输入一律作为回退解析器认领。"""
        return True

    def parse(self, input_path: str) -> ProjectDocument:
        """返回带有未实现标记的最小 `ProjectDocument`。"""
        path = Path(input_path)
        return ProjectDocument(
            project_name=path.stem or "project",
            files=[str(path)],
            metadata={
                "input_kind": "unimplemented",
                "parse_status": "scaffold",
                "source_format": path.suffix.lower().lstrip(".") or "unknown",
                "message": "此源类型保留用于后续的 OCR/PDF/Word/DWG 实现。",
            },
        )


def build_default_source_registry() -> SourceParserRegistry:
    """构建 MVP 流水线使用的默认源解析器注册表。

    注册顺序反映当前的覆盖优先级：先 Excel，其次为格式占位解析器，最后
    为通用回退解析器。
    """
    registry = SourceParserRegistry()
    registry.register(ExcelSourceParser())
    registry.register(PdfSourceParser())
    registry.register(WordSourceParser())
    registry.register(ImageSourceParser())
    registry.register(DwgSourceParser())
    return registry