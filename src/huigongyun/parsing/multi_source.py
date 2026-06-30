"""多源解析器：目录感知分发与元数据合并。

`MultiSourceParser` 接收目录路径，遍历文件，按后缀分发到注册表中
对应解析器，最终将多个 `ProjectDocument.metadata` 合并为一个统一的文档。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import ProjectDocument
from .registry import SourceParserRegistry, build_default_source_registry


class MultiSourceParser:
    """多源解析器：目录 → 多文件分发 → 合并 metadata。

    单文件输入时退化为普通的注册表派发（向后兼容）。
    """

    def __init__(self, registry: SourceParserRegistry | None = None) -> None:
        self.registry = registry or build_default_source_registry()

    # ── 公共入口 ──────────────────────────────────────────────────────

    def parse(self, input_path: str) -> ProjectDocument:
        path = Path(input_path)
        if path.is_dir():
            return self._parse_directory(path)
        # 单文件 → 委托原注册表
        return self.registry.parse(input_path)

    # ── 目录解析 ──────────────────────────────────────────────────────

    def _parse_directory(self, dir_path: Path) -> ProjectDocument:
        """遍历目录文件，按后缀分发解析器，收集并合并结果。"""
        documents: list[ProjectDocument] = []

        for file_path in sorted(dir_path.iterdir()):
            if not file_path.is_file():
                continue
            try:
                doc = self.registry.parse(str(file_path))
                if self._is_usable(doc):
                    documents.append(doc)
            except Exception:
                # 个别文件解析失败不阻塞整体流程
                continue

        if not documents:
            return ProjectDocument(
                project_name=dir_path.name,
                files=[str(dir_path)],
                metadata={"input_kind": "multi_source", "parse_status": "empty"},
            )

        return self._merge_documents(documents, dir_path)

    # ── 文档合并 ──────────────────────────────────────────────────────

    def _merge_documents(self, documents: list[ProjectDocument], dir_path: Path) -> ProjectDocument:
        """将多个 ProjectDocument 的 metadata 按 key 合并。

        - 同名 key 且双方都是 list → extend
        - 同名 key 且一方非 list → 保留第一个非空值
        - 不同 key → 合并
        """
        all_files: list[str] = []
        merged_meta: dict[str, Any] = {"input_kind": "multi_source"}
        source_map: dict[str, str] = {}

        for doc in documents:
            # files 并集
            for f in doc.files:
                if f not in all_files:
                    all_files.append(f)

            # 记录来源映射
            for f in doc.files:
                suffix = Path(f).suffix.lower()
                source_map[f] = doc.metadata.get("input_kind", suffix.lstrip("."))

            # metadata 合并
            for key, value in doc.metadata.items():
                if key in ("input_kind",):
                    continue  # 由顶层统一设置
                if key not in merged_meta:
                    merged_meta[key] = value
                elif isinstance(merged_meta[key], list) and isinstance(value, list):
                    merged_meta[key].extend(value)
                elif not merged_meta[key] and value:
                    merged_meta[key] = value
                # 否则保留已有值（先到先得）

        merged_meta["_source_map"] = source_map
        merged_meta["parse_status"] = "ok"
        merged_meta["source_count"] = len(documents)

        # 项目名取目录名
        return ProjectDocument(
            project_name=dir_path.name,
            files=all_files,
            metadata=merged_meta,
        )

    # ── 辅助 ──────────────────────────────────────────────────────────

    @staticmethod
    def _is_usable(doc: ProjectDocument) -> bool:
        """判断解析结果是否可用。"""
        status = doc.metadata.get("parse_status", "")
        return status in ("ok", "scaffold")
