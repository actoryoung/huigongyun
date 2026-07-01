"""EmbeddingMaterialMatcher 单元测试。"""

from src.retrieval.embeddings import EmbeddingProvider
from src.retrieval.matcher import EmbeddingMaterialMatcher


class FakeEmbeddingProvider(EmbeddingProvider):
    """为测试提供确定性的嵌入。"""

    def __init__(self, dim: int = 16):
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for i, ch in enumerate(text):
            vec[i % self._dim] += ord(ch) * 0.001
        norm = max(sum(v * v for v in vec) ** 0.5, 1e-8)
        return [v / norm for v in vec]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class TestEmbeddingMaterialMatcher:

    def test_identical_materials_score_high(self):
        """完全相同物料→相似度接近1.0。"""
        matcher = EmbeddingMaterialMatcher(FakeEmbeddingProvider(16))
        m = {"name": "断路器", "spec": "NSX250", "brand": "施耐德"}
        score = matcher.match(m, m)
        assert score > 0.99, f"Expected near 1.0, got {score}"

    def test_different_materials_score_low(self):
        """完全不同物料→相似度较低。"""
        matcher = EmbeddingMaterialMatcher(FakeEmbeddingProvider(16))
        a = {"name": "断路器", "spec": "NSX250", "brand": "施耐德"}
        b = {"name": "电缆", "spec": "YJV-4x25", "brand": "国产"}
        score = matcher.match(a, b)
        assert score < 0.9, f"Expected low score, got {score}"

    def test_similar_materials_moderate_score(self):
        """相近但不同的物料→中等相似度。"""
        matcher = EmbeddingMaterialMatcher(FakeEmbeddingProvider(16))
        a = {"name": "断路器", "spec": "NSX250", "brand": "施耐德"}
        b = {"name": "塑壳断路器", "spec": "NSX250", "brand": "Schneider"}
        score = matcher.match(a, b)
        assert 0.3 < score < 1.0  # FakeEmbedding 无法建模语义，放宽阈值

    def test_empty_material_returns_zero(self):
        """空物料字典→0.0。"""
        matcher = EmbeddingMaterialMatcher(FakeEmbeddingProvider(16))
        assert matcher.match({}, {}) == 0.0

    def test_partial_empty_handling(self):
        """单侧空→0.0。"""
        matcher = EmbeddingMaterialMatcher(FakeEmbeddingProvider(16))
        score = matcher.match(
            {"name": "断路器", "spec": "NSX250"},
            {},
        )
        assert score == 0.0

    def test_build_text_with_normalized_fields(self):
        """normalized_* 字段优先于原始字段。"""
        matcher = EmbeddingMaterialMatcher(FakeEmbeddingProvider(1))
        text = matcher._build_text({
            "name": "空气开关",
            "normalized_name": "断路器",
            "spec": "MCCB-250A",
            "brand": "Schneider",
            "normalized_brand": "施耐德",
        })
        assert "断路器" in text
        assert "空气开关" not in text
        assert "施耐德" in text

    def test_build_text_with_minimum(self):
        """最简字段也可正常工作。"""
        matcher = EmbeddingMaterialMatcher(FakeEmbeddingProvider(1))
        assert matcher._build_text({"name": "断路器"}) == "断路器"
        assert matcher._build_text({"material_name": "接触器"}) == "接触器"
