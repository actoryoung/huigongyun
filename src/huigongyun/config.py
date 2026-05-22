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
