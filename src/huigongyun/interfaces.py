from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .models import ProjectDocument, ProjectResult


@runtime_checkable
class ProjectParser(Protocol):
    def parse(self, input_path: str) -> ProjectDocument:
        """Parse a project input path into the normalized document model.

        Scope: top-level entry for a source file, folder, or future source bundle.
        Boundary: should not perform business rules, BOM generation, or pricing.
        """


@runtime_checkable
class SourceParser(Protocol):
    def supports(self, input_path: str) -> bool:
        """Report whether this parser can handle the given source path.

        Scope: format detection only.
        Boundary: do not decode business rules or cross-document semantics here.
        """

    def parse(self, input_path: str) -> ProjectDocument:
        """Parse a specific source format into a normalized document model.

        Scope: turn one format into a shared project document scaffold.
        Boundary: preserve provenance, but leave OCR, semantic resolution, and
        cabinet/BOM inference to downstream stages.
        """


@dataclass(slots=True)
class OCRBlock:
    text: str
    confidence: float | None = None
    bbox: tuple[float, float, float, float] | None = None
    page_no: int | None = None
    source_format: str | None = None


@dataclass(slots=True)
class ExtractedDocument:
    blocks: list[OCRBlock]
    metadata: dict[str, Any] | None = None


@runtime_checkable
class OCRTextExtractor(Protocol):
    def extract_text(self, input_path: str) -> ExtractedDocument:
        """Extract text and layout hints from OCR-capable inputs.

        Scope: scanned PDF, images, and future rendered drawing pages.
        Boundary: return raw text blocks and coordinates only; do not interpret
        cabinet semantics, brands, or BOM rules.
        """


@runtime_checkable
class DocumentTextExtractor(Protocol):
    def extract_text(self, input_path: str) -> ExtractedDocument:
        """Extract text and structure from Office/PDF documents.

        Scope: Word/PDF text mining for technical specs, constraints, and notes.
        Boundary: avoid BOM generation; keep extracted clauses and provenance.
        """


@dataclass(slots=True)
class CaseHit:
    """A ranked historical-case hit.

    This is a lightweight transport object for retrieval results. The payload is
    intentionally generic so future implementations can carry case metadata,
    source references, or embedding-derived evidence without changing the API.
    """

    case_id: str
    score: float
    summary: str | None = None
    payload: dict[str, Any] | None = None


@runtime_checkable
class HistoricalCaseRetriever(Protocol):
    """Historical-case retrieval contract.

    Boundary:
    - Search prior projects, cabinets, or quotation records.
    - Return ranked hits and traceable evidence only.

    Future implementation hooks:
    - BM25 or keyword search.
    - Vector search / embeddings.
    - Hybrid retrieval with filter predicates.
    """

    def search(self, query: dict[str, Any], top_k: int = 5) -> list[CaseHit]:
        """Retrieve similar historical cases for BOM or rule assistance."""


@runtime_checkable
class SimilarMaterialMatcher(Protocol):
    """Similarity matching contract for material normalization.

    Boundary:
    - Compare one material candidate against candidate material records.
    - Return similarity scores or ranked matches, but do not merge records.

    Future implementation hooks:
    - RapidFuzz or other string similarity libraries.
    - Embedding-based semantic matching.
    - Brand/spec disambiguation rules.
    """

    def match(self, left: dict[str, Any], right: dict[str, Any]) -> float:
        """Return a similarity score for two material representations."""


@runtime_checkable
class CabinetExtractor(Protocol):
    def extract(self, document: ProjectDocument) -> ProjectResult:
        """Extract cabinet candidates from a parsed project document.

        Scope: cabinet-level records and traceable provenance.
        Boundary: no pricing, no UI logic, no direct external API calls.
        """


@runtime_checkable
class MaterialNormalizer(Protocol):
    def normalize(self, result: ProjectResult) -> ProjectResult:
        """Normalize material names, specs, and brands.

        Scope: deterministic cleaning, alias mapping, and canonicalization.
        Boundary: keep business rules explicit and explainable.
        """


@runtime_checkable
class BomGenerator(Protocol):
    def generate(self, result: ProjectResult) -> ProjectResult:
        """Generate cabinet-level and project-level BOM lines.

        Scope: deterministic BOM assembly and aggregation.
        Boundary: no pricing and no validation side effects.
        """


@runtime_checkable
class QuoteGenerator(Protocol):
    def generate(self, result: ProjectResult) -> ProjectResult:
        """Generate quote lines and totals from BOM and pricing inputs.

        Scope: pricing lookup and subtotal aggregation.
        Boundary: avoid parsing source files or mutating extraction stages.
        """


@runtime_checkable
class Validator(Protocol):
    def validate(self, result: ProjectResult) -> ProjectResult:
        """Validate BOM completeness and consistency.

        Scope: rule checks, warnings, and traceable issue reporting.
        Boundary: validation only; should not silently rewrite source data.
        """


@runtime_checkable
class Exporter(Protocol):
    def export(self, result: ProjectResult, output_dir: str) -> dict[str, str]:
        """Export result artifacts and return generated paths.

        Scope: JSON, Excel, and future report artifacts.
        Boundary: serialization only; no business inference.
        """


@dataclass(slots=True)
class PipelineContext:
    input_path: str
    output_dir: str
