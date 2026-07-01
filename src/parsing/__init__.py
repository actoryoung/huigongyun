"""解析层脚手架。

此包暴露稳定的解析器接口与占位实现，用于 Excel、PDF、Word、图像
与 DWG 等输入格式的解析与适配。
"""

from .base import ScaffoldFormatParser
from .dwg import DwgSourceParser
from .excel import ExcelProjectParser
from .image import ImageSourceParser
from .multi_source import MultiSourceParser
from .pdf import PdfSourceParser
from .registry import (
	ExcelSourceParser,
	ScaffoldSourceParser,
	SourceParser,
	SourceParserRegistry,
	build_default_source_registry,
)
from .word import WordSourceParser

__all__ = [
	"ScaffoldFormatParser",
	"DwgSourceParser",
	"ExcelProjectParser",
	"ExcelSourceParser",
	"ImageSourceParser",
	"MultiSourceParser",
	"PdfSourceParser",
	"ScaffoldSourceParser",
	"SourceParser",
	"SourceParserRegistry",
	"WordSourceParser",
	"build_default_source_registry",
]
