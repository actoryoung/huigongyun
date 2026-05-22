"""Parsing layer scaffolding.

This package exposes stable parser interfaces and scaffold implementations for
Excel, PDF, Word, image, and DWG inputs.
"""

from .base import ScaffoldFormatParser
from .dwg import DwgSourceParser
from .excel import ExcelProjectParser
from .image import ImageSourceParser
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
	"PdfSourceParser",
	"ScaffoldSourceParser",
	"SourceParser",
	"SourceParserRegistry",
	"WordSourceParser",
	"build_default_source_registry",
]
