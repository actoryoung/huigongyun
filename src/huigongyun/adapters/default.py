from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..interfaces import BomGenerator, CabinetExtractor, Exporter, MaterialNormalizer, ProjectParser, QuoteGenerator, Validator
from ..models import BomLine, CabinetRecord, MaterialRecord, ProjectDocument, ProjectResult, ValidationIssue
from ..parsing.registry import SourceParserRegistry, build_default_source_registry
from ..validation.default import DefaultProjectValidator
from ..generation.excel_bom import ExcelBomAggregator, ExcelCabinetAndBomExtractor
from ..export.spreadsheet import ProjectExporter
from ..normalization.default import DefaultMaterialNormalizer as _DefaultMaterialNormalizer
from ..pricing.default import DefaultQuoteGenerator as _DefaultQuoteGenerator


class DefaultProjectParser(ProjectParser):
    def __init__(self, registry: SourceParserRegistry | None = None) -> None:
        self.registry = registry or build_default_source_registry()

    def parse(self, input_path: str) -> ProjectDocument:
        path = Path(input_path)
        if path.is_file() or path.is_dir():
            return self.registry.parse(str(path))
        return ProjectDocument(project_name=path.stem, files=[str(path)])


class DefaultCabinetExtractor(CabinetExtractor):
    def extract(self, document: ProjectDocument) -> ProjectResult:
        if document.metadata.get("input_kind") == "excel":
            return ExcelCabinetAndBomExtractor().extract(document)

        result = ProjectResult(project=document)
        result.cabinets.append(CabinetRecord(cabinet_no="TBD-01", cabinet_type="unknown", remarks="placeholder"))
        return result


class DefaultMaterialNormalizer(MaterialNormalizer):
    def normalize(self, result: ProjectResult) -> ProjectResult:
        return _DefaultMaterialNormalizer().normalize(result)


class DefaultBomGenerator(BomGenerator):
    def generate(self, result: ProjectResult) -> ProjectResult:
        if not result.bom_lines:
            placeholder = MaterialRecord(name="placeholder material", unit="set", quantity=1, remarks="placeholder")
            result.bom_lines.append(
                BomLine(
                    cabinet_no=result.cabinets[0].cabinet_no if result.cabinets else "TBD-01",
                    material=placeholder,
                    derived_from="default-scaffold",
                    risk_tags=["needs-implementation"],
                )
            )
        return ExcelBomAggregator().generate(result)


class DefaultQuoteGenerator(QuoteGenerator):
    def generate(self, result: ProjectResult) -> ProjectResult:
        return _DefaultQuoteGenerator().generate(result)


class DefaultValidator(Validator):
    def validate(self, result: ProjectResult) -> ProjectResult:
        return DefaultProjectValidator().validate(result)


class DefaultExporter(Exporter):
    def export(self, result: ProjectResult, output_dir: str) -> dict[str, str]:
        return ProjectExporter().export(result, output_dir)
