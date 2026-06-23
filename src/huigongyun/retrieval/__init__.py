"""检索与相似度接口导出。

该包重新导出历史检索与物料相似度匹配的接口契约，以及第一个具体实现
``FaissCaseRetriever``（FAISS 向量搜索 + sentence-transformers 嵌入）。

使用方式::

    from huigongyun.retrieval import FaissCaseRetriever, SentenceTransformerProvider

    provider = SentenceTransformerProvider()
    retriever = FaissCaseRetriever(provider)
    retriever.index_cases(cases)
    results = retriever.search({"material_name": "断路器"})
"""

from ..interfaces import CaseHit, HistoricalCaseRetriever, SimilarMaterialMatcher
from .embeddings import EmbeddingProvider, SentenceTransformerProvider
from .faiss_index import FaissCaseRetriever
from .indexer import CaseIndexer
from .models import IndexedCase

__all__ = [
    "CaseHit",
    "CaseIndexer",
    "EmbeddingProvider",
    "FaissCaseRetriever",
    "HistoricalCaseRetriever",
    "IndexedCase",
    "SentenceTransformerProvider",
    "SimilarMaterialMatcher",
]
