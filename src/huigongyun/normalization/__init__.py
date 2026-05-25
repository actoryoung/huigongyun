"""归一化层脚手架。

该包导出物料归一化的默认实现，用于清洗、别名映射与简单的模糊匹配。
"""

from .default import DefaultMaterialNormalizer

__all__ = ["DefaultMaterialNormalizer"]
