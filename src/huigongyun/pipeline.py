from __future__ import annotations

from dataclasses import dataclass

from .interfaces import BomGenerator, CabinetExtractor, Exporter, MaterialNormalizer, PipelineContext, ProjectParser, QuoteGenerator, Validator
from .models import ProjectResult


@dataclass(slots=True)
class Pipeline:
    parser: ProjectParser
    extractor: CabinetExtractor
    normalizer: MaterialNormalizer
    bom_generator: BomGenerator
    quote_generator: QuoteGenerator
    validator: Validator
    exporter: Exporter

    def run(self, context: PipelineContext) -> ProjectResult:
        document = self.parser.parse(context.input_path)
        result = self.extractor.extract(document)
        result = self.normalizer.normalize(result)
        result = self.bom_generator.generate(result)
        result = self.quote_generator.generate(result)
        result = self.validator.validate(result)
        result.outputs = self.exporter.export(result, context.output_dir)
        return result
