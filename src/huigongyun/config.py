"""应用默认值的配置 dataclass。

这些轻量容器供示例流水线和测试使用，用于集中默认路径与功能开关
（例如 OCR、Excel 解析、匹配阈值、导出选项）。该模块并非用于生产的
完整配置管理方案。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class AppConfig:
    project_root: Path = field(default_factory=lambda: Path.cwd())
    input_dir: Path = field(default_factory=lambda: Path.cwd())
    output_dir: Path = field(default_factory=lambda: Path.cwd() / "output")
    temp_dir: Path = field(default_factory=lambda: Path.cwd() / ".tmp")
    use_mock_data: bool = True


@dataclass(slots=True)
class ParsingConfig:
    enable_ocr: bool = False
    enable_pdf_tables: bool = False
    enable_excel_parsing: bool = True


@dataclass(slots=True)
class MatchingConfig:
    similarity_threshold: float = 0.85
    normalize_brand_names: bool = True
    normalize_material_names: bool = True


@dataclass(slots=True)
class ExportConfig:
    export_json: bool = True
    export_excel: bool = False
    include_audit_log: bool = True
