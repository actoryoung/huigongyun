"""EmbeddingProvider 单元测试。

测试 SentenceTransformerProvider 的导入和回退行为。
"""

from __future__ import annotations

import pytest

from huigongyun.retrieval.embeddings import EmbeddingProvider, SentenceTransformerProvider


class TestSentenceTransformerProvider:
    """测试 embedding provider 导入行为。"""

    def test_import_error_when_not_installed(self):
        """若 sentence-transformers 未安装应给出清晰的 ImportError。"""
        try:
            import sentence_transformers  # noqa: F401
            pytest.skip("sentence-transformers 已安装")
        except ImportError:
            with pytest.raises(ImportError, match="sentence-transformers"):
                SentenceTransformerProvider()

    @pytest.mark.slow
    def test_provider_loads_model(self):
        """若 sentence-transformers 已安装应能加载模型。"""
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            pytest.skip("sentence-transformers 未安装")

        provider = SentenceTransformerProvider(model_name="all-MiniLM-L6-v2")
        assert provider.dimension == 384

        vec = provider.embed("断路器 MCCB-250A 施耐德")
        assert len(vec) == 384
        assert all(isinstance(v, float) for v in vec)

        batch = provider.embed_batch(["断路器", "接触器 LC1D-32"])
        assert len(batch) == 2
        assert all(len(v) == 384 for v in batch)
