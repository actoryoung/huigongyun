from __future__ import annotations

from pathlib import Path

from ..models import ProjectDocument


class ScaffoldFormatParser:
    """Shared fallback behavior for not-yet-implemented source formats."""

    input_kind = "unimplemented"
    parse_status = "scaffold"
    source_format = "unknown"
    message = "This source type is reserved for later OCR/PDF/Word/DWG implementation."

    def supports(self, input_path: str) -> bool:
        """Match by extension so the registry can route inputs deterministically."""
        return Path(input_path).suffix.lower() in self.supported_suffixes()

    def parse(self, input_path: str) -> ProjectDocument:
        """Return a scaffold document that preserves the future implementation hook."""
        path = Path(input_path)
        return ProjectDocument(
            project_name=path.stem or "project",
            files=[str(path)],
            metadata={
                "input_kind": self.input_kind,
                "parse_status": self.parse_status,
                "source_format": self.source_format,
                "message": self.message,
            },
        )

    def supported_suffixes(self) -> set[str]:
        """Declare which file suffixes this parser owns."""
        return set()