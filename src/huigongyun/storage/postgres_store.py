"""Postgres 持久化助手。

当 `psycopg2` 可用且环境变量中提供连接信息时，将运行摘要写入数据库。
优先使用 `DATABASE_URL` 或 `PG_DSN`，否则从 `PG_HOST` / `PG_PORT` / `PG_DATABASE` /
`PG_USER` / `PG_PASSWORD` 等变量构建 DSN。主要接口：`is_configured()`、
`save_run_summary_if_configured()` 与 `save_run_summary()`。
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

try:
    import psycopg2  # type: ignore
    import psycopg2.extras  # type: ignore
    _HAS_PG = True
except Exception:
    _HAS_PG = False


def _get_dsn() -> str | None:
    """从环境变量解析用于 psycopg2 的连接字符串（DSN）。

    优先级：
      1. 使用完整的 `DATABASE_URL` 或 `PG_DSN`（如果存在，直接返回）；
      2. 否则从 `PG_HOST` / `PG_PORT` / `PG_DATABASE` / `PG_USER` / `PG_PASSWORD`
         构建一个空格分隔的 libpq 风格 DSN（`host=... port=... dbname=...`）。

    如果无法至少从环境中获取 `PG_HOST`，返回 `None`。
    """
    # 优先使用完整的 DATABASE_URL
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("PG_DSN")
    if dsn:
        return dsn

    host = os.environ.get("PG_HOST")
    if not host:
        return None
    port = os.environ.get("PG_PORT", "5432")
    db = os.environ.get("PG_DATABASE") or os.environ.get("PG_DB") or "huigongyun"
    user = os.environ.get("PG_USER") or os.environ.get("PG_USERNAME")
    password = os.environ.get("PG_PASSWORD")
    # 即使缺少 user/password 也尝试连接（某些容器配置可能使用 trust）
    parts = [f"host={host}", f"port={port}", f"dbname={db}"]
    if user:
        parts.append(f"user={user}")
    if password:
        parts.append(f"password={password}")
    return " ".join(parts)


def is_configured() -> bool:
    """返回当前环境是否已配置并可用于持久化写入。"""
    return _HAS_PG and (_get_dsn() is not None)


def _extract_run_id(run_dir: str) -> str | None:
    """从运行目录路径中尝试提取一个短 `run_id`。

    常见格式为 `huigongyun-<hex>-...`（此函数返回 `<hex>` 部分）。
    若未匹配该模式，则回退至路径的 basename，当其本身看起来像一个十六进制标识时返回。
    返回匹配到的 id 或 `None`。
    """
    # expect temp dirs like huigongyun-<hex>-xxxx
    m = re.search(r"huigongyun-([0-9a-fA-F]+)-", run_dir)
    if m:
        return m.group(1)
    # fallback to basename if it's short
    name = os.path.basename(run_dir)
    if re.fullmatch(r"[0-9a-fA-F]{8,}", name):
        return name
    return None


def _ensure_table(conn) -> None:
        """确保数据库中存在 `runs` 表（幂等创建）。

        表结构包含基础度量列（如 cabinet_count）、若干 JSONB 列用于存放
        `outputs`/`issues`/`user_edits` 以及完整的 `raw_result` 以便审计与回溯。
        """
        sql = """
        CREATE TABLE IF NOT EXISTS runs (
            id SERIAL PRIMARY KEY,
            run_id TEXT UNIQUE,
            project_name TEXT,
            run_dir TEXT,
            status TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            completed_at TIMESTAMPTZ,
            cabinet_count INTEGER,
            bom_line_count INTEGER,
            summary_count INTEGER,
            issue_count INTEGER,
            outputs JSONB,
            issues JSONB,
            user_edits JSONB,
            raw_result JSONB
        );
        """
        with conn.cursor() as cur:
                cur.execute(sql)
                conn.commit()


def save_run_summary(run_id: str | None, run_dir: str, summary: dict[str, Any], status: str = "completed") -> bool:
    """将运行摘要写入 `runs` 表，支持 INSERT 或 ON CONFLICT 的 UPSERT。

    参数：
      - `run_id`：外部运行 ID，可为空；为空时尝试从 `run_dir` 提取；
      - `run_dir`：运行目录路径（记录入库以便追溯）；
      - `summary`：包含 `project_name`、`cabinet_count`、`bom_line_count` 等键的字典；
      - `status`：运行状态字符串，默认 `completed`。

    行为：
      - 若未安装 psycopg2 或未配置 DSN，返回 False；
      - 在首次写入前会调用 `_ensure_table` 创建表（幂等）；
      - 将 `outputs`/`issues`/`user_edits` 以及完整 `summary` 以 JSONB 存储；
      - 返回 True 表示成功，任何异常均会导致返回 False（调用方可选择忽略）。
    """
    if not _HAS_PG:
        return False
    dsn = _get_dsn()
    if not dsn:
        return False

    if run_id is None:
        run_id = _extract_run_id(run_dir)
        if run_id is None:
            return False

    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
        try:
            _ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO runs (run_id, project_name, run_dir, status, completed_at, cabinet_count, bom_line_count, summary_count, issue_count, outputs, issues, user_edits, raw_result)
                    VALUES (%s,%s,%s,%s,now(),%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (run_id) DO UPDATE SET
                      project_name = EXCLUDED.project_name,
                      run_dir = EXCLUDED.run_dir,
                      status = EXCLUDED.status,
                      completed_at = EXCLUDED.completed_at,
                      cabinet_count = EXCLUDED.cabinet_count,
                      bom_line_count = EXCLUDED.bom_line_count,
                      summary_count = EXCLUDED.summary_count,
                      issue_count = EXCLUDED.issue_count,
                      outputs = EXCLUDED.outputs,
                      issues = EXCLUDED.issues,
                      user_edits = EXCLUDED.user_edits,
                      raw_result = EXCLUDED.raw_result;
                    """,
                    (
                        run_id,
                        summary.get("project_name"),
                        run_dir,
                        status,
                        summary.get("cabinet_count"),
                        summary.get("bom_line_count"),
                        summary.get("summary_count"),
                        summary.get("issue_count"),
                        psycopg2.extras.Json(summary.get("outputs", {})),
                        psycopg2.extras.Json(summary.get("issues", [])),
                        psycopg2.extras.Json(summary.get("user_edits", [])),
                        psycopg2.extras.Json(summary),
                    ),
                )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception:
        return False


def save_run_summary_if_configured(run_id: str | None, run_dir: str, summary: dict[str, Any]) -> bool:
    """在已配置 Postgres 的情况下保存运行摘要的安全包装器。

    该函数捕获所有异常并返回布尔值以表示操作是否成功，便于在 Web/任务流程中
    以不影响主流程的方式调用（例如记录失败但不抛出）。
    """
    try:
        return save_run_summary(run_id, run_dir, summary)
    except Exception:
        return False
