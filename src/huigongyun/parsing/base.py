"""解析器基础与占位实现。

包含用于尚未实现格式的占位解析器，返回最小化的 `ProjectDocument`，
以便后续流水线阶段继续处理或提示未实现功能。
"""

from __future__ import annotations

from pathlib import Path

from ..models import ProjectDocument


class ScaffoldFormatParser:
    """尚未实现格式的共享占位解析行为。

    属性：
      - `input_kind`/`parse_status`/`source_format`/`message` 用以在返回的
        `ProjectDocument.metadata` 中标注占位信息。
    """

    input_kind = "unimplemented"
    parse_status = "scaffold"
    source_format = "unknown"
    message = "此源类型保留用于后续的 OCR/PDF/Word/DWG 实现。"

    def supports(self, input_path: str) -> bool:
        """按扩展名匹配，便于注册表将输入路由到对应解析器。"""
        return Path(input_path).suffix.lower() in self.supported_suffixes()

    def parse(self, input_path: str) -> ProjectDocument:
        """返回包含占位标记的最小 `ProjectDocument`。"""
        path = Path(input_path)
        return ProjectDocument(
            project_name=path.stem or "project",
            files=[str(path)],
            metadata={
                "input_kind": self.input_kind,
                "parse_status": self.parse_status,
                "source_format": self.source_format,
                "message": self.message,
            },
        )

    def supported_suffixes(self) -> set[str]:
        """声明此解析器负责的文件后缀集合。"""
        return set()