"""项目特定的异常类型定义。

此处定义在解析、提取与导出等阶段使用的轻量异常类，设计为便于
调用方捕获并映射为用户友好提示或日志策略。
"""

from __future__ import annotations


class HuigongyunError(Exception):
    """Base class for project-specific exceptions."""


class ConfigurationError(HuigongyunError):
    """Raised when runtime configuration is invalid."""


class ParseError(HuigongyunError):
    """Raised when an input file cannot be parsed."""


class ExtractionError(HuigongyunError):
    """Raised when cabinet or BOM extraction fails."""


class ExportError(HuigongyunError):
    """Raised when result export fails."""
