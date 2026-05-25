"""定价与报价生成工具导出。

此包暴露用于将 BOM 转换为报价行并聚合小计的生成器实现。
"""

from .default import DefaultQuoteGenerator

__all__ = ["DefaultQuoteGenerator"]
