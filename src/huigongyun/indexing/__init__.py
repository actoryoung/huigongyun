"""索引层脚手架。

此包包含为解析结果构建索引的实用工具（例如机柜索引生成器），便于
下游阶段进行快速查找与聚合。
"""

from .cabinets import CabinetIndexBuilder, CabinetIndexResult

__all__ = ["CabinetIndexBuilder", "CabinetIndexResult"]
