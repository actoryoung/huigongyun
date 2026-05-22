from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .models import ProjectDocument, ProjectResult


@runtime_checkable
class ProjectParser(Protocol):
    def parse(self, input_path: str) -> ProjectDocument:
        """Parse project source files into a normalized document model."""


@runtime_checkable
class SourceParser(Protocol):
    def supports(self, input_path: str) -> bool:
        """Report whether this parser can handle the given source path."""

    def parse(self, input_path: str) -> ProjectDocument:
        """Parse a specific source format into a normalized document model."""


@runtime_checkable
class CabinetExtractor(Protocol):
    def extract(self, document: ProjectDocument) -> ProjectResult:
        """Extract cabinet candidates from a parsed project document."""


@runtime_checkable
class MaterialNormalizer(Protocol):
    def normalize(self, result: ProjectResult) -> ProjectResult:
        """Normalize material names, specs, and brands."""


@runtime_checkable
class BomGenerator(Protocol):
    def generate(self, result: ProjectResult) -> ProjectResult:
        """Generate cabinet-level and project-level BOM lines."""


@runtime_checkable
class Validator(Protocol):
    def validate(self, result: ProjectResult) -> ProjectResult:
        """Validate BOM completeness and consistency."""


@runtime_checkable
class Exporter(Protocol):
    def export(self, result: ProjectResult, output_dir: str) -> dict[str, str]:
        """Export result artifacts and return generated paths."""


@dataclass(slots=True)
class PipelineContext:
    input_path: str
    output_dir: str
