"""检索模块内部数据模型。

定义 ``IndexedCase`` — 索引到向量搜索中的轻量案例表示。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class IndexedCase:
    """索引中的一个案例记录。

    ``text`` 是将被嵌入的文本（物料名+规格+品牌+柜型的串联）。
    ``payload`` 承载原始结构化数据以便在搜索结果中返回。
    ``case_id`` 是文档内唯一的标识符。
    """

    case_id: str
    text: str
    payload: dict[str, Any] = field(default_factory=dict)
    project_name: str = ""
    cabinet_no: str | None = None
