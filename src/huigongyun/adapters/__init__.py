"""MVP 骨架的默认适配器实现导出。

该模块重新导出一组默认的解析、提取、归一、生成与导出器实现，便于
在开发与测试中直接组装流水线。
"""

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
