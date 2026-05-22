from __future__ import annotations

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
        """Return True when the parser can handle the given input path.

        Boundary: format ownership only; keep implementation-specific logic out.
        """

    def parse(self, input_path: str) -> ProjectDocument:
        """Parse a source file into the shared project document model.

        Boundary: parse one format into the common project document scaffold.
        """


@dataclass(slots=True)
class SourceParserRegistry:
    parsers: list[SourceParser] = field(default_factory=list)

    def register(self, parser: SourceParser) -> None:
        """Register a format parser in precedence order."""
        self.parsers.append(parser)

    def select(self, input_path: str) -> SourceParser:
        """Select the first parser that explicitly claims the input suffix."""
        for parser in self.parsers:
            if parser.supports(input_path):
                return parser
        return ScaffoldSourceParser()

    def parse(self, input_path: str) -> ProjectDocument:
        """Parse input through the selected parser."""
        return self.select(input_path).parse(input_path)


class ExcelSourceParser:
    """Excel source adapter.

    Input boundary: .xlsx/.xlsm/.xltx/.xltm workbook files.
    Future work: sheet classification, more robust table heuristics, multi-workbook
    project bundles.
    """

    def __init__(self) -> None:
        self._parser = ExcelProjectParser()

    def supports(self, input_path: str) -> bool:
        """Own Excel workbook suffixes only."""
        suffix = Path(input_path).suffix.lower()
        return suffix in {".xlsx", ".xlsm", ".xltx", ".xltm"}

    def parse(self, input_path: str) -> ProjectDocument:
        """Delegate to the workbook parser and preserve the Excel scaffold."""
        return self._parser.parse(input_path)


class ScaffoldSourceParser:
    """Fallback parser for formats that are not implemented yet.

    Boundary: this should only be used when no dedicated parser claims the input.
    """

    def supports(self, input_path: str) -> bool:
        """Always claim unmatched inputs as the registry fallback."""
        return True

    def parse(self, input_path: str) -> ProjectDocument:
        """Return a minimal project document with explicit unimplemented markers."""
        path = Path(input_path)
        return ProjectDocument(
            project_name=path.stem or "project",
            files=[str(path)],
            metadata={
                "input_kind": "unimplemented",
                "parse_status": "scaffold",
                "source_format": path.suffix.lower().lstrip(".") or "unknown",
                "message": "This source type is reserved for later OCR/PDF/Word/DWG implementation.",
            },
        )


def build_default_source_registry() -> SourceParserRegistry:
    """Build the default source parser registry used by the MVP pipeline.

    Registration order reflects current coverage priority: Excel first, then
    the reserved format-specific scaffold parsers, followed by the generic fallback.
    """
    registry = SourceParserRegistry()
    registry.register(ExcelSourceParser())
    registry.register(PdfSourceParser())
    registry.register(WordSourceParser())
    registry.register(ImageSourceParser())
    registry.register(DwgSourceParser())
    return registry