"""构建默认流水线的便捷工具。

本模块提供工厂方法，供应用程序与测试构造默认的处理流水线以及运行时
的 `PipelineContext`。

函数：
    - `build_default_pipeline()` -> `Pipeline`：返回已组装好默认适配器（解析、提取、归一、
        BOM 生成、报价、验证与导出）的流水线实例。
    - `build_context(input_path, output_dir)` -> `PipelineContext`：构造传递给
        `Pipeline.run()` 的上下文对象。
"""

from __future__ import annotations

from .adapters import (
    DefaultBomGenerator,
    DefaultCabinetExtractor,
    DefaultExporter,
    DefaultMaterialNormalizer,
    DefaultProjectParser,
    DefaultQuoteGenerator,
    DefaultValidator,
)
from .interfaces import PipelineContext
from .pipeline import Pipeline


def build_default_pipeline() -> Pipeline:
    """构造默认的 `Pipeline`，并用标准适配器进行组装。

    返回：已组装、可直接运行的 `Pipeline` 实例。"""
    pipeline = Pipeline(
        parser=DefaultProjectParser(),
        extractor=DefaultCabinetExtractor(),
        normalizer=DefaultMaterialNormalizer(),
        bom_generator=DefaultBomGenerator(),
        quote_generator=DefaultQuoteGenerator(),
        validator=DefaultValidator(),
        exporter=DefaultExporter(),
    )

    # 可选：若 FAISS + sentence-transformers 可用则注入检索器
    try:
        from .retrieval import FaissCaseRetriever, SentenceTransformerProvider

        provider = SentenceTransformerProvider()
        retriever = FaissCaseRetriever(provider)
        if retriever.is_available:
            pipeline.retriever = retriever
    except (ImportError, OSError):
        pass  # 依赖未安装时静默跳过

    # 可选：若 sentence-transformers 可用则注入物料相似度匹配器
    try:
        from .retrieval import EmbeddingMaterialMatcher, SentenceTransformerProvider

        matcher_provider = SentenceTransformerProvider()
        pipeline.matcher = EmbeddingMaterialMatcher(matcher_provider)
    except (ImportError, OSError):
        pass  # 依赖未安装时静默跳过

    return pipeline


def build_context(input_path: str, output_dir: str) -> PipelineContext:
    """创建用于运行流水线的 `PipelineContext`。

    参数：
      - `input_path`：要解析的输入文件或目录路径。
      - `output_dir`：导出器应将工件写入的目录。

    返回：`PipelineContext` 对象。"""
    return PipelineContext(input_path=input_path, output_dir=output_dir)
