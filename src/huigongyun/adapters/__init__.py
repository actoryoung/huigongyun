"""Default adapter implementations for the MVP scaffold."""

from .default import (
    DefaultBomGenerator,
    DefaultCabinetExtractor,
    DefaultExporter,
    DefaultMaterialNormalizer,
    DefaultProjectParser,
    DefaultQuoteGenerator,
    DefaultValidator,
)
from ..parsing.registry import ExcelSourceParser, ScaffoldSourceParser, SourceParserRegistry, build_default_source_registry

__all__ = [
    "DefaultBomGenerator",
    "DefaultCabinetExtractor",
    "DefaultExporter",
    "DefaultMaterialNormalizer",
    "DefaultProjectParser",
    "DefaultQuoteGenerator",
    "DefaultValidator",
    "ExcelSourceParser",
    "ScaffoldSourceParser",
    "SourceParserRegistry",
    "build_default_source_registry",
]
