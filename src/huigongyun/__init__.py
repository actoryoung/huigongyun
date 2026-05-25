"""Huigongyun MVP 包。

此包提供项目的轻量演示实现，包括流水线组装、解析器、导出器与
基础数据模型。主要用于开发、测试与概念验证。
"""

from .models import (
    BomLine,
    CabinetRecord,
    MaterialRecord,
    ProjectDocument,
    ProjectResult,
    ValidationIssue,
)
from .bootstrap import build_context, build_default_pipeline

__all__ = [
    "BomLine",
    "CabinetRecord",
    "build_context",
    "build_default_pipeline",
    "MaterialRecord",
    "ProjectDocument",
    "ProjectResult",
    "ValidationIssue",
]
