"""嵌入提供者抽象层。

提供 ``EmbeddingProvider`` ABC 和基于 sentence-transformers 的具体实现。
遵循项目"依赖可选"原则：sentence-transformers 为延迟导入，缺失时优雅回退。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List


class EmbeddingProvider(ABC):
    """文本到向量的嵌入服务抽象基类。

    实现应提供 ``embed()`` 方法，将文本转换为浮点数向量列表。
    ``dimension`` 属性暴露该模型产生的向量维数。
    """

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """将单段文本转换为嵌入向量。"""
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """将一批文本转换为嵌入向量。"""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """该提供者产生的嵌入向量的维数。"""
        ...


class SentenceTransformerProvider(EmbeddingProvider):
    """基于 sentence-transformers 的嵌入提供者。

    依赖：
        ``pip install sentence-transformers``

    在首次使用时下载模型。默认模型 ``all-MiniLM-L6-v2``
    产生 384 维嵌入，大小约 80 MB，在 CPU 上运行良好。

    用法::

        provider = SentenceTransformerProvider()
        vec = provider.embed("断路器 MCCB-250A 施耐德")
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """初始化提供者。

        Args:
            model_name: HuggingFace sentence-transformers 模型名称。

        Raises:
            ImportError: 如果未安装 ``sentence-transformers``。
        """
        self._model_name = model_name
        self._model = None
        self._load_model()

    def _load_model(self) -> None:
        """延迟加载模型。首次调用时下载模型权重。"""
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers 未安装。"
                " 使用 `pip install sentence-transformers` 安装。"
            )
        self._model = SentenceTransformer(self._model_name)

    @property
    def dimension(self) -> int:
        if self._model is None:
            self._load_model()
        return self._model.get_sentence_embedding_dimension()

    def embed(self, text: str) -> list[float]:
        if self._model is None:
            self._load_model()
        return self._model.encode(text, normalize_embeddings=True).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            self._load_model()
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()
