from __future__ import annotations

from .adapters import (
    DefaultBomGenerator,
    DefaultCabinetExtractor,
    DefaultExporter,
    DefaultMaterialNormalizer,
    DefaultProjectParser,
    DefaultValidator,
)
from .interfaces import PipelineContext
from .pipeline import Pipeline


def build_default_pipeline() -> Pipeline:
    return Pipeline(
        parser=DefaultProjectParser(),
        extractor=DefaultCabinetExtractor(),
        normalizer=DefaultMaterialNormalizer(),
        bom_generator=DefaultBomGenerator(),
        validator=DefaultValidator(),
        exporter=DefaultExporter(),
    )


def build_context(input_path: str, output_dir: str) -> PipelineContext:
    return PipelineContext(input_path=input_path, output_dir=output_dir)
