"""任务模块：可选的 Celery 集成与同步回退实现。

本模块导出 `process_project(...)`，用于对上传的输入文件执行完整处理
流水线。在可用时该函数以 Celery 任务形式注册，否则提供相同签名的
同步实现以便本地或测试运行。

I/O 约定（process_project）：
    - 参数：
            - `run_dir`：临时运行目录，包含上传的文件。
            - `input_filename`：要处理的文件名（位于 `run_dir` 内）。
            - `run_id`：可选的外部运行标识，用于持久化记录。
    - 返回：包含 `project_name`、`cabinet_count`、`bom_line_count`、
        `summary_count`、`issue_count`、`outputs`、`issues`、`user_edits` 等键的摘要字典。
    - 副作用：将 `result.json` 写入 `run_dir/output`，可能将工件上传到 MinIO，
        并在配置了 Postgres 时尝试持久化摘要。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .bootstrap import build_default_pipeline, build_context
from dataclasses import asdict
import re

try:
    from celery import Celery  # type: ignore
    _HAS_CELERY = True
except Exception:
    _HAS_CELERY = False


try:
    from .storage.postgres_store import save_run_summary_if_configured
    _HAS_PG_STORE = True
except Exception:
    _HAS_PG_STORE = False


def _extract_run_id_from_dir(run_dir: str) -> str | None:
    """从运行目录字符串中提取 huigongyun 运行 ID。

    查找模式 `huigongyun-<hex>-` 并返回 `<hex>` 部分；未匹配时返回 `None`。
    """
    m = re.search(r"huigongyun-([0-9a-fA-F]+)-", str(run_dir))
    if m:
        return m.group(1)
    return None


if _HAS_CELERY:
    broker = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    backend = os.environ.get("CELERY_RESULT_BACKEND", broker)
    celery = Celery("huigongyun", broker=broker, backend=backend)

    @celery.task(bind=True)
    def process_project(self, run_dir: str, input_filename: str, run_id: str | None = None) -> dict[str, Any]:
        """对上传项目运行流水线（Celery 任务）。

        参数：
            - `run_dir`：包含上传 `input_filename` 的目录。
            - `input_filename`：待处理文件名，位于 `run_dir` 内。
            - `run_id`：可选的外部运行标识。

        返回：包含项目度量与输出位置的摘要字典。

        副作用：
            - 在运行目录写入 `result.json`
            - 可能通过导出器将结果上传到 MinIO
            - 在可用时尝试将摘要持久化到 Postgres
        """

        run_dir_path = Path(run_dir)
        input_path = run_dir_path / input_filename
        output_dir = run_dir_path / "output"
        pipeline = build_default_pipeline()
        result = pipeline.run(build_context(str(input_path), str(output_dir)))
        output_dir.mkdir(parents=True, exist_ok=True)

        summary = {
            "project_name": result.project.project_name,
            "cabinet_count": len(result.cabinets),
            "bom_line_count": len(result.bom_lines),
            "summary_count": len(result.summary),
            "issue_count": len(result.issues),
            "outputs": result.outputs,
            "issues": [asdict(issue) for issue in result.issues],
            "user_edits": [asdict(edit) for edit in result.user_edits],
        }

        with open(run_dir_path / "result.json", "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2)

        # attempt to persist to Postgres if configured
        try:
            rid = run_id or _extract_run_id_from_dir(str(run_dir_path))
            if _HAS_PG_STORE and rid:
                save_run_summary_if_configured(rid, str(run_dir_path), summary)
        except Exception:
            pass

        return summary


else:
    def process_project(run_dir: str, input_filename: str, run_id: str | None = None) -> dict[str, Any]:
        """`process_project` 的同步回退实现。

        与 Celery 任务具有相同语义：运行流水线、写入 `result.json`，并在
        配置了 Postgres 时尝试持久化摘要。
        """

        run_dir_path = Path(run_dir)
        input_path = run_dir_path / input_filename
        output_dir = run_dir_path / "output"
        pipeline = build_default_pipeline()
        result = pipeline.run(build_context(str(input_path), str(output_dir)))
        output_dir.mkdir(parents=True, exist_ok=True)

        summary = {
            "project_name": result.project.project_name,
            "cabinet_count": len(result.cabinets),
            "bom_line_count": len(result.bom_lines),
            "summary_count": len(result.summary),
            "issue_count": len(result.issues),
            "outputs": result.outputs,
            "issues": [asdict(issue) for issue in result.issues],
            "user_edits": [asdict(edit) for edit in result.user_edits],
        }

        with open(run_dir_path / "result.json", "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2)

        # attempt to persist to Postgres if configured
        try:
            rid = run_id or _extract_run_id_from_dir(str(run_dir_path))
            if _HAS_PG_STORE and rid:
                save_run_summary_if_configured(rid, str(run_dir_path), summary)
        except Exception:
            pass

        return summary
