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
