from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..interfaces import BomGenerator, CabinetExtractor, Exporter, MaterialNormalizer, ProjectParser, Validator
from ..models import BomLine, CabinetRecord, MaterialRecord, ProjectDocument, ProjectResult, ValidationIssue
from ..validation.default import DefaultProjectValidator
from ..parsing.excel import ExcelProjectParser
from ..generation.excel_bom import ExcelBomAggregator, ExcelCabinetAndBomExtractor
from ..export.spreadsheet import ProjectExporter


class DefaultProjectParser(ProjectParser):
    def parse(self, input_path: str) -> ProjectDocument:
        path = Path(input_path)
        excel_parser = ExcelProjectParser()
        if path.is_file() or path.is_dir():
            return excel_parser.parse(str(path))
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
        for bom_line in result.bom_lines:
            material = bom_line.material
            material.normalized_name = material.normalized_name or material.name.strip()
            material.normalized_spec = material.normalized_spec or (material.spec.strip() if material.spec else None)

        for material in result.summary:
            material.normalized_name = material.normalized_name or material.name.strip()
            material.normalized_spec = material.normalized_spec or (material.spec.strip() if material.spec else None)
        return result


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


class DefaultValidator(Validator):
    def validate(self, result: ProjectResult) -> ProjectResult:
        return DefaultProjectValidator().validate(result)


class DefaultExporter(Exporter):
    def export(self, result: ProjectResult, output_dir: str) -> dict[str, str]:
        return ProjectExporter().export(result, output_dir)
