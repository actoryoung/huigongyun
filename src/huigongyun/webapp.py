"""轻量 Flask 演示 Web 应用与交互壳。

该模块提供一个最小化的 Flask 应用，演示流水线的上传/运行流程以及
简单的人机交互（人工修正）。关键端点：
  - POST /run：接收上传文件并入队或同步运行流水线。
  - GET /status/<run_id>：检查运行是否完成并返回摘要。
  - GET /download/<run_id>/<filename>：下载已导出的工件（若为本地文件）。
  - POST /edit/<run_id>：对内存结果应用人工修改并重新导出（HTML 返回）。
  - POST /edit/<run_id>/json：对内存结果应用人工修改并重新导出（JSON 返回）。

该应用在 `RUN_STORAGE` 中保留短期运行状态以便演示；生产环境应使用
持久化存储。
"""

from __future__ import annotations

import json as json_lib
import os
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path

from flask import Flask, abort, jsonify, render_template_string, request, send_file, url_for

from .bootstrap import build_context, build_default_pipeline
from .export.spreadsheet import ProjectExporter
from .generation.excel_bom import ExcelBomAggregator
from .models import UserEdit
from .normalization.default import DefaultMaterialNormalizer
from .validation.default import DefaultProjectValidator
from . import tasks
try:
  from .storage.postgres_store import save_run_summary_if_configured
  _HAS_PG_STORE = True
except Exception:
  _HAS_PG_STORE = False


RUN_STORAGE: dict[str, dict[str, object]] = {}
ALLOWED_CABINET_EDIT_FIELDS = {"cabinet_type", "rated_current", "dimensions", "circuit_count", "quantity", "inbound_outbound", "grounding_mode", "remarks"}
ALLOWED_BOM_EDIT_FIELDS = {"name", "spec", "unit", "quantity", "brand", "manufacturer", "long_lead_time", "remarks"}
ALLOWED_PRICING_EDIT_FIELDS = {"unit_price", "price_source"}


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        return render_template_string(
            INDEX_TEMPLATE,
            last_result=None,
            error=None,
        )

    def _app_doc_endpoints() -> str:
      """开发用的端点简要说明（非 HTTP 路由）。

      用于代码注释与文档内部说明，不作为对外路由暴露。
      """

    @app.post("/run")
    def run_pipeline() -> str:
        uploaded = request.files.get("input_file")
        if uploaded is None or not uploaded.filename:
            return render_template_string(INDEX_TEMPLATE, last_result=None, error="请先选择一个 Excel 文件。")

        run_id = uuid.uuid4().hex
        run_dir = Path(tempfile.mkdtemp(prefix=f"huigongyun-{run_id}-"))
        input_path = run_dir / uploaded.filename
        uploaded.save(input_path)

        # If Celery is available, enqueue the pipeline run; otherwise run synchronously.
        if getattr(tasks, "_HAS_CELERY", False) and os.environ.get("HUIGONGYUN_ASYNC", "").strip().lower() in {"1", "true", "yes"}:
          task = tasks.process_project.delay(str(run_dir), uploaded.filename, run_id) if hasattr(tasks.process_project, "delay") else tasks.process_project(str(run_dir), uploaded.filename, run_id)
          RUN_STORAGE[run_id] = {"run_dir": str(run_dir), "task_id": getattr(task, "id", None), "status": "queued", "result": None}
          # show queued summary
          summary = {"run_id": run_id, "project_name": "queued", "cabinet_count": 0, "bom_line_count": 0, "summary_count": 0, "issue_count": 0, "outputs": {}}
          return render_template_string(INDEX_TEMPLATE, last_result=summary, error=None)

        # synchronous execution
        output_dir = run_dir / "output"
        pipeline = build_default_pipeline()
        result = pipeline.run(build_context(str(input_path), str(output_dir)))
        RUN_STORAGE[run_id] = {"run_dir": str(run_dir), "result": result}

        summary = _build_summary(run_id, result)

        # persist to Postgres if available
        try:
          if _HAS_PG_STORE:
            persist_payload = summary if isinstance(summary, dict) else _build_summary(run_id, result)
            save_run_summary_if_configured(run_id, str(run_dir), persist_payload)
        except Exception:
          pass

        return render_template_string(INDEX_TEMPLATE, last_result=summary, error=None)

    @app.post("/edit/<run_id>")
    def edit_result(run_id: str) -> str:
        run_state = RUN_STORAGE.get(run_id)
        if not run_state:
            abort(404)

        result = run_state.get("result")
        if result is None:
            abort(404)

        scope = (request.form.get("scope") or "").strip()
        field_name = (request.form.get("field_name") or "").strip()
        target = (request.form.get("target") or "").strip()
        value = (request.form.get("value") or "").strip()

        _apply_edit(result, scope, field_name, target, value, request.form)

        _reprocess_result(result, run_state)

        summary = _build_summary(run_id, result)
        return render_template_string(INDEX_TEMPLATE, last_result=summary, error=None)

    @app.post("/edit/<run_id>/json")
    def edit_result_json(run_id: str):
        run_state = RUN_STORAGE.get(run_id)
        if not run_state:
            return jsonify(success=False, error="运行不存在", result=None), 404

        result = run_state.get("result")
        if result is None:
            return jsonify(success=False, error="结果不存在", result=None), 404

        data = request.get_json(silent=True) or {}
        scope = (data.get("scope") or "").strip()
        field_name = (data.get("field_name") or "").strip()
        target = (data.get("target") or "").strip()
        value = (data.get("value") or "").strip()

        try:
            _apply_edit(result, scope, field_name, target, value, data)
            _reprocess_result(result, run_state)
            summary = _build_summary(run_id, result)
            return jsonify(success=True, error=None, result=summary)
        except Exception as exc:
            return jsonify(success=False, error=str(exc), result=None), 400

    @app.get("/download/<run_id>/<path:filename>")
    def download_artifact(run_id: str, filename: str):
        run_state = RUN_STORAGE.get(run_id)
        if run_state is None:
            abort(404)
        file_path = Path(run_state["run_dir"]) / "output" / filename
        if not file_path.exists():
            abort(404)
        return send_file(file_path, as_attachment=True)

    @app.get("/status/<run_id>")
    def status(run_id: str):
        run_state = RUN_STORAGE.get(run_id)
        if not run_state:
            abort(404)
        run_dir = Path(run_state["run_dir"])
        result_file = run_dir / "result.json"
        if result_file.exists():
            import json

            summary = json.loads(result_file.read_text(encoding="utf-8"))
            RUN_STORAGE[run_id]["result"] = summary
            RUN_STORAGE[run_id]["status"] = "completed"
            return render_template_string(INDEX_TEMPLATE, last_result=summary, error=None)
        # still queued
        summary = {"run_id": run_id, "project_name": "queued", "cabinet_count": 0, "bom_line_count": 0, "summary_count": 0, "issue_count": 0, "outputs": {}}
        return render_template_string(INDEX_TEMPLATE, last_result=summary, error=None)

    return app


def main() -> int:
    app = create_app()
    host = os.environ.get("HUIGONGYUN_HOST", "127.0.0.1")
    port = int(os.environ.get("HUIGONGYUN_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
    return 0


def _apply_edit(result, scope: str, field_name: str, target: str, value: str, form_data):
    """Apply a user edit to a result object.

    Supports scopes: cabinet, bom, pricing.
    Mutates result in-place.
    """
    from .models import QuoteLine

    if scope == "cabinet":
        if field_name not in ALLOWED_CABINET_EDIT_FIELDS:
            raise ValueError(f"不允许的柜体字段: {field_name}")
        cabinet = next((item for item in result.cabinets if item.cabinet_no == target), None)
        if cabinet is None:
            raise ValueError(f"未找到柜体: {target}")
        old_value = getattr(cabinet, field_name)
        setattr(cabinet, field_name, _coerce_value(field_name, value, old_value))
        result.user_edits.append(
            UserEdit(
                scope="cabinet",
                target=target,
                field_name=field_name,
                old_value=None if old_value is None else str(old_value),
                new_value=value or None,
                note="manual correction",
            )
        )
    elif scope == "bom":
        if field_name not in ALLOWED_BOM_EDIT_FIELDS:
            raise ValueError(f"不允许的 BOM 字段: {field_name}")
        material_name = (form_data.get("material_name") if isinstance(form_data, dict) else form_data.get("material_name") or "").strip()
        bom_line = next(
            (
                item
                for item in result.bom_lines
                if item.cabinet_no == target and item.material.name == material_name
            ),
            None,
        )
        if bom_line is None:
            raise ValueError(f"未找到 BOM 行: {target}:{material_name}")
        material = bom_line.material
        old_value = getattr(material, field_name)
        setattr(material, field_name, _coerce_value(field_name, value, old_value))
        result.user_edits.append(
            UserEdit(
                scope="bom",
                target=f"{target}:{material_name}",
                field_name=field_name,
                old_value=None if old_value is None else str(old_value),
                new_value=value or None,
                note="manual correction",
            )
        )
    elif scope == "pricing":
        if field_name not in ALLOWED_PRICING_EDIT_FIELDS:
            raise ValueError(f"不允许的价格字段: {field_name}")
        material_name = (form_data.get("material_name") if isinstance(form_data, dict) else form_data.get("material_name") or "").strip()
        quote_line = next(
            (
                item
                for item in result.summary
                if isinstance(item, QuoteLine) and item.cabinet_no == target and item.material_name == material_name
            ),
            None,
        )
        if quote_line is None:
            raise ValueError(f"未找到报价行: {target}:{material_name}")
        old_value = getattr(quote_line, field_name)
        setattr(quote_line, field_name, _coerce_value(field_name, value, old_value))
        if field_name == "unit_price" and value:
            quote_line.price_missing = False
        result.user_edits.append(
            UserEdit(
                scope="pricing",
                target=f"{target}:{material_name}",
                field_name=field_name,
                old_value=None if old_value is None else str(old_value),
                new_value=value or None,
                note="manual price correction",
            )
        )
    else:
        raise ValueError(f"不支持的范围: {scope}")


def _reprocess_result(result, run_state):
    """Re-run normalization, generation, validation, and export after an edit."""
    DefaultMaterialNormalizer().normalize(result)
    ExcelBomAggregator().generate(result)
    result.issues = DefaultProjectValidator().validate(result).issues

    output_dir = Path(run_state["run_dir"]) / "output"
    result.outputs = ProjectExporter().export(result, str(output_dir))


def _build_summary(run_id: str, result) -> dict[str, object]:
  # support both dataclass ProjectResult and serialized dict written by worker
  if isinstance(result, dict):
    outputs = result.get("outputs", {}) or {}
    download_links = {}
    for key, path in outputs.items():
      if isinstance(path, str) and (path.startswith("http://") or path.startswith("https://")):
        download_links[key] = path
      else:
        download_links[key] = url_for("download_artifact", run_id=run_id, filename=Path(path).name)
    return {
      "run_id": run_id,
      "project_name": result.get("project_name"),
      "cabinet_count": result.get("cabinet_count", 0),
      "bom_line_count": result.get("bom_line_count", 0),
      "summary_count": result.get("summary_count", 0),
      "issue_count": result.get("issue_count", 0),
      "outputs": outputs,
      "download_links": download_links,
      "issues": result.get("issues", []),
      "cabinets": result.get("cabinets", []),
      "bom_lines": result.get("bom_lines", []),
      "user_edits": result.get("user_edits", []),
    }

  return {
    "run_id": run_id,
    "project_name": result.project.project_name,
    "cabinet_count": len(result.cabinets),
    "bom_line_count": len(result.bom_lines),
    "summary_count": len(result.summary),
    "issue_count": len(result.issues),
    "outputs": result.outputs,
    "download_links": {
      (key if (isinstance(path, str) and (path.startswith("http://") or path.startswith("https://"))) else key): (
        (path if (isinstance(path, str) and (path.startswith("http://") or path.startswith("https://"))) else url_for("download_artifact", run_id=run_id, filename=Path(path).name))
      )
      for key, path in result.outputs.items()
    },
    "issues": [asdict(issue) for issue in result.issues],
    "cabinets": [asdict(cabinet) for cabinet in result.cabinets],
    "bom_lines": [asdict(bom_line) for bom_line in result.bom_lines],
    "user_edits": [asdict(edit) for edit in result.user_edits],
  }


def _coerce_value(field_name: str, value: str, old_value):
    if field_name == "quantity":
        try:
            return float(value) if "." in value else int(value)
        except ValueError:
            return old_value
    if field_name == "circuit_count":
        try:
            return int(float(value))
        except ValueError:
            return old_value
    if field_name == "long_lead_time":
        return value.strip().lower() in {"1", "true", "yes", "y", "是", "有", "x"}
    if field_name == "unit_price":
        try:
            return float(value)
        except ValueError:
            return old_value
    return value


INDEX_TEMPLATE = r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>低压电气成套智能报价清单生成系统</title>
  <style>
    :root {
      --bg: #0f172a;
      --panel: rgba(15, 23, 42, 0.82);
      --card: rgba(30, 41, 59, 0.92);
      --text: #e2e8f0;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --accent-2: #22c55e;
      --danger: #f87171;
      --line: rgba(148, 163, 184, 0.2);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(56, 189, 248, 0.22), transparent 30%),
        radial-gradient(circle at bottom right, rgba(34, 197, 94, 0.18), transparent 28%),
        var(--bg);
      color: var(--text);
    }
    .shell {
      max-width: 1280px;
      margin: 0 auto;
      padding: 40px 20px 60px;
    }
    .hero {
      display: grid;
      grid-template-columns: 1.4fr 1fr;
      gap: 20px;
      align-items: stretch;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      backdrop-filter: blur(12px);
      border-radius: 24px;
      box-shadow: 0 24px 80px rgba(15, 23, 42, 0.35);
    }
    .card { padding: 24px; }
    h1 {
      margin: 0 0 12px;
      font-size: 34px;
      line-height: 1.1;
    }
    .lead { color: var(--muted); line-height: 1.7; margin: 0; }
    .upload {
      display: grid;
      gap: 14px;
    }
    .dropzone {
      border: 1.5px dashed rgba(56, 189, 248, 0.5);
      background: rgba(15, 23, 42, 0.45);
      border-radius: 18px;
      padding: 18px;
    }
    input[type="file"] {
      width: 100%;
      color: var(--muted);
    }
    button {
      border: 0;
      border-radius: 14px;
      background: linear-gradient(135deg, var(--accent), #818cf8);
      color: white;
      padding: 13px 18px;
      font-weight: 700;
      cursor: pointer;
    }
    button.sm {
      padding: 6px 12px;
      font-size: 12px;
      border-radius: 8px;
    }
    button.ghost {
      background: transparent;
      border: 1px solid var(--line);
      color: var(--text);
    }
    button.ghost:hover {
      background: rgba(148, 163, 184, 0.1);
    }
    button.danger {
      background: linear-gradient(135deg, #ef4444, #dc2626);
    }
    .meta-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }
    .metric {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
    }
    .metric .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
    .metric .value { font-size: 24px; font-weight: 800; margin-top: 6px; }
    .section { margin-top: 20px; }
    .section h2 { margin: 0 0 12px; font-size: 20px; }
    .list { display: grid; gap: 8px; }
    .item {
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px 16px;
      background: rgba(15, 23, 42, 0.35);
    }
    .item strong { display: block; margin-bottom: 4px; }
    .error {
      margin-top: 12px;
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(248, 113, 113, 0.14);
      border: 1px solid rgba(248, 113, 113, 0.35);
      color: #fecaca;
    }
    a { color: var(--accent); cursor: pointer; }
    a:hover { text-decoration: underline; }
    .footnote { margin-top: 18px; color: var(--muted); font-size: 13px; }

    /* ---- Risk Badges ---- */
    .risk-badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 10px;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .risk-critical { border-left: 3px solid #ef4444; }
    .risk-critical .risk-badge { background: rgba(239, 68, 68, 0.2); color: #fca5a5; }
    .risk-high { border-left: 3px solid #f97316; }
    .risk-high .risk-badge { background: rgba(249, 115, 22, 0.2); color: #fdba74; }
    .risk-medium { border-left: 3px solid #eab308; }
    .risk-medium .risk-badge { background: rgba(234, 179, 8, 0.2); color: #fde047; }
    .risk-low { border-left: 3px solid #3b82f6; }
    .risk-low .risk-badge { background: rgba(59, 130, 246, 0.2); color: #93c5fd; }
    .risk-info { border-left: 3px solid #6b7280; }
    .risk-info .risk-badge { background: rgba(107, 114, 128, 0.2); color: #d1d5db; }

    /* ---- Issue Item ---- */
    .issue-header {
      display: flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
      user-select: none;
    }
    .issue-header .issue-type { font-weight: 600; font-size: 12px; }
    .issue-header .issue-msg { flex: 1; font-size: 13px; color: var(--muted); }
    .issue-header .toggle-icon { font-size: 12px; color: var(--muted); transition: transform .2s; }
    .issue-header .toggle-icon.expanded { transform: rotate(90deg); }
    .issue-details {
      display: none;
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px solid var(--line);
      font-size: 13px;
    }
    .issue-details.open { display: block; }
    .issue-details .detail-row {
      display: flex;
      gap: 8px;
      margin-bottom: 6px;
    }
    .issue-details .detail-label {
      color: var(--muted);
      min-width: 80px;
      flex-shrink: 0;
    }
    .issue-action {
      margin-top: 10px;
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }
    .issue-action input, .issue-action select {
      border-radius: 8px;
      border: 1px solid var(--line);
      background: rgba(15, 23, 42, 0.5);
      color: var(--text);
      padding: 6px 10px;
      font-size: 13px;
    }
    .issue-action input { min-width: 100px; }

    /* ---- Tables ---- */
    .table-wrap {
      overflow-x: auto;
      margin-top: 12px;
    }
    table.data-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    table.data-table th {
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
      font-weight: 600;
      white-space: nowrap;
      cursor: pointer;
      user-select: none;
    }
    table.data-table th:hover { color: var(--text); }
    table.data-table th .sort-indicator { margin-left: 4px; opacity: 0.4; }
    table.data-table th.sort-asc .sort-indicator,
    table.data-table th.sort-desc .sort-indicator { opacity: 1; }
    table.data-table td {
      padding: 8px 12px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.08);
      vertical-align: top;
    }
    table.data-table tr:hover td { background: rgba(56, 189, 248, 0.04); }
    table.data-table td[contenteditable="true"] {
      cursor: text;
      border-radius: 4px;
      padding: 4px 6px;
    }
    table.data-table td[contenteditable="true"]:hover {
      background: rgba(56, 189, 248, 0.08);
    }
    table.data-table td[contenteditable="true"]:focus {
      outline: 1px solid var(--accent);
      background: rgba(56, 189, 248, 0.1);
    }

    /* ---- Search/Toolbar ---- */
    .toolbar {
      display: flex;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }
    .toolbar input, .toolbar select {
      border-radius: 10px;
      border: 1px solid var(--line);
      background: rgba(15, 23, 42, 0.5);
      color: var(--text);
      padding: 8px 12px;
      font-size: 13px;
    }
    .toolbar input { flex: 1; min-width: 140px; }
    .toolbar select { min-width: 100px; }
    .toolbar .result-count { font-size: 12px; color: var(--muted); margin-left: auto; }

    /* ---- Toast ---- */
    .toast {
      position: fixed;
      bottom: 20px;
      right: 20px;
      padding: 12px 20px;
      border-radius: 12px;
      font-size: 13px;
      z-index: 999;
      opacity: 0;
      transition: opacity .3s;
      pointer-events: none;
    }
    .toast.show { opacity: 1; }
    .toast.success { background: rgba(34, 197, 94, 0.9); color: white; }
    .toast.error { background: rgba(239, 68, 68, 0.9); color: white; }

    /* ---- Responsive ---- */
    @media (max-width: 980px) {
      .hero { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="hero">
      <div class="panel card">
        <h1>低压电气成套智能报价清单生成系统</h1>
        <p class="lead">
          上传 Excel 主元器件清单，运行当前最小闭环：解析工作簿、抽取柜体和 BOM、生成汇总、输出校验和导出文件。
        </p>
        <form class="upload" method="post" action="/run" enctype="multipart/form-data">
          <div class="dropzone">
            <input type="file" name="input_file" accept=".xlsx,.xlsm,.xltx,.xltm">
          </div>
          <button type="submit">运行分析</button>
        </form>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <div class="footnote">当前阶段已保留 `pending_*` 记号，复杂支持与高级校验先暂缓，等待后续数据格式正式下发。</div>
      </div>

      <div class="panel card">
        <h2>演示说明</h2>
        <div class="list">
          <div class="item"><strong>1. 输入</strong>选择一个 Excel 文件并运行。</div>
          <div class="item"><strong>2. 输出</strong>展示柜体数、BOM 行数、校验项数。</div>
          <div class="item"><strong>3. 导出</strong>可下载 JSON 与 Excel 结果。</div>
          <div class="item"><strong>4. 追溯</strong>保留原始行号、来源和待确认记号。</div>
        </div>
      </div>
    </div>

    {% if last_result %}
    <div id="results-section" class="section panel card" style="margin-top: 20px;">
      <h2>运行结果</h2>
      <div class="meta-grid" id="metrics-grid">
        <div class="metric"><div class="label">项目</div><div class="value" id="metric-project">{{ last_result.project_name }}</div></div>
        <div class="metric"><div class="label">柜体</div><div class="value" id="metric-cabinets">{{ last_result.cabinet_count }}</div></div>
        <div class="metric"><div class="label">BOM 行</div><div class="value" id="metric-bom">{{ last_result.bom_line_count }}</div></div>
        <div class="metric"><div class="label">Issues</div><div class="value" id="metric-issues">{{ last_result.issue_count }}</div></div>
      </div>

      <!-- ======== Issue Focus Panel ======== -->
      <div class="section" id="issue-panel">
        <h2>问题确认面板 <span style="font-size:12px;color:var(--muted);font-weight:400;" id="issue-count-label">({{ last_result.issues|length }})</span></h2>
        <div class="list" id="issue-list">
          {% for issue in last_result.issues %}
          <div class="item risk-{{ issue.risk_level|default('info') }}" data-issue-idx="{{ loop.index0 }}" data-cabinet="{{ issue.cabinet_no or '' }}" data-material="{{ issue.material_name or '' }}">
            <div class="issue-header" onclick="toggleIssue(this)">
              <span class="risk-badge">{{ issue.risk_level|upper|default('INFO') }}</span>
              <span class="issue-type">{{ issue.issue_type }}</span>
              <span class="issue-msg">{{ issue.message }}</span>
              <span class="toggle-icon">&#9654;</span>
            </div>
            <div class="issue-details">
              {% if issue.cabinet_no %}
              <div class="detail-row">
                <span class="detail-label">柜号</span>
                <span><a onclick="filterByCabinet('{{ issue.cabinet_no }}')">{{ issue.cabinet_no }}</a></span>
              </div>
              {% endif %}
              {% if issue.material_name %}
              <div class="detail-row">
                <span class="detail-label">物料</span>
                <span><a onclick="jumpToBomRow('{{ issue.material_name }}', '{{ issue.cabinet_no or '' }}')">{{ issue.material_name }}</a></span>
              </div>
              {% endif %}
              {% if issue.details %}
              <div class="detail-row">
                <span class="detail-label">详情</span>
                <span style="font-family:monospace;font-size:11px;color:var(--muted);white-space:pre-wrap;">{{ issue.details|tojson }}</span>
              </div>
              {% endif %}
              <div class="issue-action" id="issue-action-{{ loop.index0 }}"></div>
            </div>
          </div>
          {% endfor %}
          {% if not last_result.issues %}
          <div class="item"><strong>无</strong><span>当前样例未生成待确认项。</span></div>
          {% endif %}
        </div>
      </div>

      <!-- ======== Cabinet Table ======== -->
      <div class="section" id="cabinet-panel">
        <h2>柜体列表 <span style="font-size:12px;color:var(--muted);font-weight:400;">({{ last_result.cabinets|length }})</span></h2>
        <div class="table-wrap">
          <table class="data-table" id="cabinet-table">
            <thead>
              <tr>
                <th data-col="cabinet_no">柜号 <span class="sort-indicator">&#9650;</span></th>
                <th data-col="cabinet_type">柜型</th>
                <th data-col="rated_current">额定电流</th>
                <th data-col="circuit_count">回路数</th>
                <th data-col="quantity">数量</th>
                <th data-col="grounding_mode">接地方式</th>
              </tr>
            </thead>
            <tbody>
              {% for cab in last_result.cabinets %}
              <tr>
                <td>{{ cab.cabinet_no }}</td>
                <td>{{ cab.cabinet_type or '-' }}</td>
                <td>{{ cab.rated_current or '-' }}</td>
                <td>{{ cab.circuit_count or '-' }}</td>
                <td>{{ cab.quantity }}</td>
                <td>{{ cab.grounding_mode or '-' }}</td>
              </tr>
              {% endfor %}
              {% if not last_result.cabinets %}
              <tr><td colspan="6" style="text-align:center;color:var(--muted);">暂无柜体数据</td></tr>
              {% endif %}
            </tbody>
          </table>
        </div>
      </div>

      <!-- ======== BOM Detail Table ======== -->
      <div class="section" id="bom-panel">
        <h2>BOM 明细 <span style="font-size:12px;color:var(--muted);font-weight:400;" id="bom-count-label">({{ last_result.bom_lines|length }})</span></h2>
        <div class="toolbar">
          <input type="text" id="bom-search" placeholder="搜索物料名称/规格/柜号..." oninput="filterBomTable()">
          <select id="bom-cabinet-filter" onchange="filterBomTable()">
            <option value="">全部柜体</option>
            {% for cab in last_result.cabinets %}
            <option value="{{ cab.cabinet_no }}">{{ cab.cabinet_no }}</option>
            {% endfor %}
          </select>
          <span class="result-count" id="bom-result-count">显示 {{ last_result.bom_lines|length }} 行</span>
        </div>
        <div class="table-wrap">
          <table class="data-table" id="bom-table">
            <thead>
              <tr>
                <th data-col="cabinet_no" onclick="sortBomTable('cabinet_no')">柜号 <span class="sort-indicator">&#9650;</span></th>
                <th data-col="material_name" onclick="sortBomTable('material_name')">物料名称 <span class="sort-indicator">&#9650;</span></th>
                <th data-col="spec" onclick="sortBomTable('spec')">规格 <span class="sort-indicator">&#9650;</span></th>
                <th data-col="quantity" onclick="sortBomTable('quantity')">数量 <span class="sort-indicator">&#9650;</span></th>
                <th data-col="unit">单位</th>
                <th data-col="brand" onclick="sortBomTable('brand')">品牌 <span class="sort-indicator">&#9650;</span></th>
                <th data-col="source">来源</th>
                <th data-col="risk">风险</th>
                <th data-col="actions">操作</th>
              </tr>
            </thead>
            <tbody id="bom-tbody">
              {% for bom in last_result.bom_lines %}
              <tr data-cabinet="{{ bom.cabinet_no }}" data-material="{{ bom.material.name }}">
                <td>{{ bom.cabinet_no }}</td>
                <td>{{ bom.material.normalized_name or bom.material.name }}</td>
                <td class="editable" data-field="spec" data-cabinet="{{ bom.cabinet_no }}" data-material="{{ bom.material.name }}">{{ bom.material.spec or '-' }}</td>
                <td class="editable" data-field="quantity" data-cabinet="{{ bom.cabinet_no }}" data-material="{{ bom.material.name }}">{{ bom.material.quantity }}</td>
                <td>{{ bom.material.unit or '-' }}</td>
                <td class="editable" data-field="brand" data-cabinet="{{ bom.cabinet_no }}" data-material="{{ bom.material.name }}">{{ bom.material.normalized_brand or bom.material.brand or '-' }}</td>
                <td style="font-size:11px;color:var(--muted);">{{ bom.derived_from }}</td>
                <td>
                  {% if bom.risk_tags %}
                  {% for tag in bom.risk_tags %}
                  <span class="risk-badge risk-medium">{{ tag }}</span>
                  {% endfor %}
                  {% else %}
                  <span style="color:var(--muted);font-size:11px;">-</span>
                  {% endif %}
                </td>
                <td>
                  <button class="sm ghost" onclick="deleteBomRow(this)" title="删除此行">删除</button>
                </td>
              </tr>
              {% endfor %}
              {% if not last_result.bom_lines %}
              <tr><td colspan="9" style="text-align:center;color:var(--muted);">暂无 BOM 数据</td></tr>
              {% endif %}
            </tbody>
          </table>
        </div>
      </div>

      <!-- ======== Download Links ======== -->
      <div class="section">
        <h2>导出文件</h2>
        <div class="list" id="download-list">
          {% for key, value in last_result.outputs.items() %}
          <div class="item">
            <strong>{{ key }}</strong>
            <span><a href="{{ last_result.download_links[key] }}">{{ value }}</a></span>
          </div>
          {% endfor %}
        </div>
      </div>

      <!-- ======== Edit History ======== -->
      {% if last_result.user_edits %}
      <div class="section">
        <h2>修正历史</h2>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>范围</th><th>目标</th><th>字段</th><th>旧值</th><th>新值</th></tr></thead>
            <tbody>
              {% for edit in last_result.user_edits %}
              <tr>
                <td>{{ edit.scope }}</td>
                <td>{{ edit.target }}</td>
                <td>{{ edit.field_name }}</td>
                <td style="color:var(--muted);">{{ edit.old_value or '-' }}</td>
                <td style="color:var(--accent-2);">{{ edit.new_value or '-' }}</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
      {% endif %}
    </div>
    {% endif %}
  </div>

  <div id="toast" class="toast"></div>

  <script>
  /* ======== Initial Data ======== */
  var RESULT_DATA = {% if last_result %}{{ last_result|tojson }}{% else %}null{% endif %};
  var CURRENT_SORT = { col: null, asc: true };
  var CABINET_LIST = RESULT_DATA ? (RESULT_DATA.cabinets || []).map(function(c) { return c.cabinet_no; }) : [];

  /* ======== Toast ======== */
  function showToast(msg, type) {
    var t = document.getElementById('toast');
    t.textContent = msg;
    t.className = 'toast show ' + type;
    setTimeout(function() { t.classList.remove('show'); }, 3000);
  }

  /* ======== Issue Panel ======== */
  function toggleIssue(el) {
    var details = el.parentElement.querySelector('.issue-details');
    var icon = el.querySelector('.toggle-icon');
    var isOpen = details.classList.toggle('open');
    if (icon) icon.classList.toggle('expanded', isOpen);
    // Initialize action buttons on first expand
    if (isOpen && !details.dataset.initialized) {
      details.dataset.initialized = '1';
      initIssueAction(el.parentElement);
    }
  }

  function initIssueAction(issueEl) {
    var idx = issueEl.dataset.issueIdx;
    var actionDiv = issueEl.querySelector('.issue-action');
    if (!actionDiv) return;
    var issue = RESULT_DATA.issues[idx];
    if (!issue) return;

    var it = issue.issue_type;
    var cabinet = issue.cabinet_no || '';
    var material = issue.material_name || '';
    var details = issue.details || {};

    if (it === 'missing_price') {
      actionDiv.innerHTML =
        '<span style="color:var(--muted);font-size:12px;">单价: </span>' +
        '<input type="number" step="0.01" min="0" id="price-input-' + idx + '" placeholder="输入单价">' +
        '<button class="sm" onclick="fixMissingPrice(' + idx + ')">设置</button>';
    } else if (it === 'brand_conflict') {
      var brands = details.brands || [];
      if (brands.length > 1) {
        var opts = brands.map(function(b) { return '<option value="' + b.replace(/"/g, '&quot;') + '">' + b + '</option>'; }).join('');
        actionDiv.innerHTML =
          '<span style="color:var(--muted);font-size:12px;">选择品牌: </span>' +
          '<select id="brand-select-' + idx + '">' + opts + '</select>' +
          '<button class="sm" onclick="fixBrandConflict(' + idx + ')">确认</button>';
      } else {
        actionDiv.innerHTML = '<span style="color:var(--muted);font-size:11px;">暂无可选品牌</span>';
      }
    } else if (it === 'missing_cabinet_no' || it === 'missing_bom_cabinet_no') {
      if (CABINET_LIST.length > 0) {
        var opts = CABINET_LIST.map(function(c) { return '<option value="' + c + '">' + c + '</option>'; }).join('');
        actionDiv.innerHTML =
          '<span style="color:var(--muted);font-size:12px;">分配柜号: </span>' +
          '<select id="cabinet-select-' + idx + '">' + opts + '</select>' +
          '<button class="sm" onclick="fixMissingCabinet(' + idx + ')">分配</button>';
      } else {
        actionDiv.innerHTML = '<span style="color:var(--muted);font-size:11px;">无可用的柜体</span>';
      }
    } else if (it.indexOf('duplicate_') === 0) {
      var count = details.count || '?';
      actionDiv.innerHTML =
        '<span style="color:var(--muted);font-size:12px;">重复 ' + count + ' 次</span>' +
        '<button class="sm ghost" onclick="showToast(\'请手动删除重复行\', \'success\')">忽略</button>';
    } else if (it === 'cross_source_brand_non_compliance') {
      actionDiv.innerHTML =
        '<button class="sm" onclick="showToast(\'品牌合规问题，已在备注中标记\', \'success\')">标记已处理</button>';
    } else {
      actionDiv.innerHTML =
        '<span style="color:var(--muted);font-size:11px;">需人工确认</span>' +
        '<button class="sm ghost" onclick="dismissIssue(' + idx + ')">忽略</button>';
    }
  }

  function fixMissingPrice(idx) {
    var issue = RESULT_DATA.issues[idx];
    var input = document.getElementById('price-input-' + idx);
    if (!input || !input.value) { showToast('请输入单价', 'error'); return; }
    var value = parseFloat(input.value);
    if (isNaN(value) || value < 0) { showToast('无效的单价', 'error'); return; }
    sendEdit({
      scope: 'pricing',
      target: issue.cabinet_no || '',
      field_name: 'unit_price',
      value: String(value),
      material_name: issue.material_name || ''
    }, function(data) {
      input.value = '';
      showToast('单价已设置: ' + value, 'success');
    });
  }

  function fixBrandConflict(idx) {
    var issue = RESULT_DATA.issues[idx];
    var select = document.getElementById('brand-select-' + idx);
    if (!select) return;
    var chosen = select.value;
    sendEdit({
      scope: 'bom',
      target: issue.cabinet_no || '',
      field_name: 'brand',
      value: chosen,
      material_name: issue.material_name || ''
    }, function(data) {
      showToast('品牌已更新: ' + chosen, 'success');
    });
  }

  function fixMissingCabinet(idx) {
    var issue = RESULT_DATA.issues[idx];
    var select = document.getElementById('cabinet-select-' + idx);
    if (!select) return;
    var chosen = select.value;
    sendEdit({
      scope: 'bom',
      target: chosen,
      field_name: 'cabinet_no',
      value: chosen,
      material_name: issue.material_name || ''
    }, function(data) {
      showToast('柜号已分配: ' + chosen, 'success');
    });
  }

  function dismissIssue(idx) {
    var el = document.querySelector('[data-issue-idx="' + idx + '"]');
    if (el) el.style.display = 'none';
    showToast('问题已忽略', 'success');
  }

  /* ======== Send Edit (AJAX) ======== */
  function sendEdit(payload, onSuccess) {
    var runId = RESULT_DATA ? RESULT_DATA.run_id : '';
    if (!runId) return;

    fetch('/edit/' + runId + '/json', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.success && data.result) {
        RESULT_DATA = data.result;
        refreshSummary(data.result);
        if (onSuccess) onSuccess(data);
      } else {
        showToast(data.error || '修正失败', 'error');
      }
    })
    .catch(function(err) {
      showToast('网络错误: ' + err.message, 'error');
    });
  }

  /* ======== Refresh Summary ======== */
  function refreshSummary(data) {
    // Metrics
    document.getElementById('metric-project').textContent = data.project_name || '-';
    document.getElementById('metric-cabinets').textContent = data.cabinet_count || 0;
    document.getElementById('metric-bom').textContent = data.bom_line_count || 0;
    document.getElementById('metric-issues').textContent = data.issue_count || 0;

    // Rebuild Issue List
    rebuildIssueList(data);

    // Rebuild Cabinet Table
    rebuildCabinetTable(data);

    // Rebuild BOM Table
    rebuildBomTable(data);

    // Rebuild Download Links
    rebuildDownloadLinks(data);

    // Rebuild Edit History
    rebuildEditHistory(data);
  }

  function rebuildIssueList(data) {
    var container = document.getElementById('issue-list');
    if (!container) return;
    var label = document.getElementById('issue-count-label');
    if (label) label.textContent = '(' + (data.issues || []).length + ')';

    var issues = data.issues || [];
    if (issues.length === 0) {
      container.innerHTML = '<div class="item"><strong>无</strong><span>当前样例未生成待确认项。</span></div>';
      return;
    }

    var html = '';
    for (var i = 0; i < issues.length; i++) {
      var iss = issues[i];
      var rl = (iss.risk_level || 'info').toLowerCase();
      html += '<div class="item risk-' + rl + '" data-issue-idx="' + i + '" data-cabinet="' + (iss.cabinet_no || '') + '" data-material="' + (iss.material_name || '') + '">';
      html += '<div class="issue-header" onclick="toggleIssue(this)">';
      html += '<span class="risk-badge">' + (iss.risk_level || 'INFO').toUpperCase() + '</span>';
      html += '<span class="issue-type">' + escHtml(iss.issue_type) + '</span>';
      html += '<span class="issue-msg">' + escHtml(iss.message) + '</span>';
      html += '<span class="toggle-icon">&#9654;</span></div>';
      html += '<div class="issue-details"><div class="issue-action" id="issue-action-' + i + '"></div></div></div>';
    }
    container.innerHTML = html;
    // Re-init actions for already-open issues
    for (var j = 0; j < issues.length; j++) {
      initIssueAction(container.children[j]);
    }
  }

  function rebuildCabinetTable(data) {
    var tbody = document.querySelector('#cabinet-table tbody');
    if (!tbody) return;
    var cabs = data.cabinets || [];
    if (cabs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--muted);">暂无柜体数据</td></tr>';
      return;
    }
    var html = '';
    for (var i = 0; i < cabs.length; i++) {
      var c = cabs[i];
      html += '<tr><td>' + escHtml(c.cabinet_no) + '</td>';
      html += '<td>' + escHtml(c.cabinet_type || '-') + '</td>';
      html += '<td>' + escHtml(c.rated_current || '-') + '</td>';
      html += '<td>' + (c.circuit_count != null ? c.circuit_count : '-') + '</td>';
      html += '<td>' + c.quantity + '</td>';
      html += '<td>' + escHtml(c.grounding_mode || '-') + '</td></tr>';
    }
    tbody.innerHTML = html;

    // Update cabinet filter dropdown
    var filter = document.getElementById('bom-cabinet-filter');
    if (filter) {
      var currentVal = filter.value;
      CABINET_LIST = cabs.map(function(c) { return c.cabinet_no; });
      var opts = '<option value="">全部柜体</option>';
      for (var j = 0; j < CABINET_LIST.length; j++) {
        opts += '<option value="' + CABINET_LIST[j] + '">' + CABINET_LIST[j] + '</option>';
      }
      filter.innerHTML = opts;
      filter.value = currentVal;
    }
  }

  function rebuildBomTable(data) {
    var tbody = document.getElementById('bom-tbody');
    if (!tbody) return;
    var label = document.getElementById('bom-count-label');
    var rows = data.bom_lines || [];
    if (label) label.textContent = '(' + rows.length + ')';

    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--muted);">暂无 BOM 数据</td></tr>';
      updateBomCount(0);
      return;
    }

    var html = '';
    for (var i = 0; i < rows.length; i++) {
      var b = rows[i];
      var m = b.material || {};
      var brand = m.normalized_brand || m.brand || '-';
      var name = m.normalized_name || m.name || '-';
      var spec = m.spec || '-';
      var tags = b.risk_tags || [];

      html += '<tr data-cabinet="' + escAttr(b.cabinet_no) + '" data-material="' + escAttr(m.name) + '">';
      html += '<td>' + escHtml(b.cabinet_no) + '</td>';
      html += '<td>' + escHtml(name) + '</td>';
      html += '<td class="editable" data-field="spec" data-cabinet="' + escAttr(b.cabinet_no) + '" data-material="' + escAttr(m.name) + '">' + escHtml(spec) + '</td>';
      html += '<td class="editable" data-field="quantity" data-cabinet="' + escAttr(b.cabinet_no) + '" data-material="' + escAttr(m.name) + '">' + (m.quantity != null ? m.quantity : '0') + '</td>';
      html += '<td>' + escHtml(m.unit || '-') + '</td>';
      html += '<td class="editable" data-field="brand" data-cabinet="' + escAttr(b.cabinet_no) + '" data-material="' + escAttr(m.name) + '">' + escHtml(brand) + '</td>';
      html += '<td style="font-size:11px;color:var(--muted);">' + escHtml(b.derived_from || '') + '</td>';
      html += '<td>';
      if (tags.length > 0) {
        for (var t = 0; t < tags.length; t++) {
          html += '<span class="risk-badge risk-medium">' + escHtml(tags[t]) + '</span> ';
        }
      } else {
        html += '<span style="color:var(--muted);font-size:11px;">-</span>';
      }
      html += '</td>';
      html += '<td><button class="sm ghost" onclick="deleteBomRow(this)" title="删除此行">删除</button></td>';
      html += '</tr>';
    }
    tbody.innerHTML = html;
    updateBomCount(rows.length);

    // Re-attach editable cell handlers
    attachEditableCells();
    // Apply current filter/sort
    filterBomTable();
  }

  function rebuildDownloadLinks(data) {
    var container = document.getElementById('download-list');
    if (!container) return;
    var outputs = data.outputs || {};
    var links = data.download_links || {};
    var keys = Object.keys(outputs);
    if (keys.length === 0) {
      container.innerHTML = '<div class="item"><strong>无导出文件</strong></div>';
      return;
    }
    var html = '';
    for (var i = 0; i < keys.length; i++) {
      var key = keys[i];
      var val = outputs[key];
      var link = links[key] || '#';
      html += '<div class="item"><strong>' + escHtml(key) + '</strong>';
      html += '<span><a href="' + link + '">' + escHtml(val) + '</a></span></div>';
    }
    container.innerHTML = html;
  }

  function rebuildEditHistory(data) {
    var edits = data.user_edits || [];
    if (edits.length === 0) return;
    // Find or create the edit history section
    var existing = document.getElementById('edit-history-section');
    if (existing) existing.remove();

    var section = document.createElement('div');
    section.className = 'section';
    section.id = 'edit-history-section';
    section.innerHTML = '<h2>修正历史</h2><div class="table-wrap"><table class="data-table"><thead><tr><th>范围</th><th>目标</th><th>字段</th><th>旧值</th><th>新值</th></tr></thead><tbody id="edit-history-tbody"></tbody></table></div>';
    document.getElementById('results-section').appendChild(section);

    var tbody = document.getElementById('edit-history-tbody');
    var html = '';
    for (var i = 0; i < edits.length; i++) {
      var e = edits[i];
      html += '<tr><td>' + escHtml(e.scope) + '</td><td>' + escHtml(e.target) + '</td><td>' + escHtml(e.field_name) + '</td><td style="color:var(--muted);">' + escHtml(e.old_value || '-') + '</td><td style="color:var(--accent-2);">' + escHtml(e.new_value || '-') + '</td></tr>';
    }
    tbody.innerHTML = html;
  }

  /* ======== BOM Table Search / Filter / Sort ======== */
  function filterBomTable() {
    var query = (document.getElementById('bom-search').value || '').toLowerCase();
    var cabinetFilter = document.getElementById('bom-cabinet-filter').value;
    var rows = document.querySelectorAll('#bom-tbody tr');
    var visible = 0;

    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      if (row.cells.length <= 1) continue;
      var text = row.textContent.toLowerCase();
      var cab = row.dataset.cabinet || '';

      var match = true;
      if (query && text.indexOf(query) === -1) match = false;
      if (cabinetFilter && cab !== cabinetFilter) match = false;

      row.style.display = match ? '' : 'none';
      if (match) visible++;
    }
    updateBomCount(visible);
  }

  function updateBomCount(n) {
    var el = document.getElementById('bom-result-count');
    if (el) el.textContent = '显示 ' + n + ' 行';
  }

  var SORT_STATE = { col: null, asc: true };

  function sortBomTable(col) {
    var tbody = document.getElementById('bom-tbody');
    var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    if (rows.length === 0) return;

    if (SORT_STATE.col === col) {
      SORT_STATE.asc = !SORT_STATE.asc;
    } else {
      SORT_STATE.col = col;
      SORT_STATE.asc = true;
    }

    rows.sort(function(a, b) {
      var va = getSortValue(a, col);
      var vb = getSortValue(b, col);
      if (va < vb) return SORT_STATE.asc ? -1 : 1;
      if (va > vb) return SORT_STATE.asc ? 1 : -1;
      return 0;
    });

    // Update sort indicators
    var headers = document.querySelectorAll('#bom-table th[data-col]');
    headers.forEach(function(h) {
      h.classList.remove('sort-asc', 'sort-desc');
      if (h.dataset.col === col) {
        h.classList.add(SORT_STATE.asc ? 'sort-asc' : 'sort-desc');
      }
    });

    for (var i = 0; i < rows.length; i++) {
      tbody.appendChild(rows[i]);
    }
    filterBomTable();
  }

  function getSortValue(row, col) {
    if (col === 'cabinet_no') return (row.dataset.cabinet || '').toLowerCase();
    if (col === 'material_name') {
      var cell = row.cells[1];
      return (cell ? cell.textContent : '').toLowerCase();
    }
    if (col === 'spec') {
      var cell = row.cells[2];
      return (cell ? cell.textContent : '').toLowerCase();
    }
    if (col === 'quantity') {
      var cell = row.cells[3];
      return parseFloat(cell ? cell.textContent : '0') || 0;
    }
    if (col === 'brand') {
      var cell = row.cells[5];
      return (cell ? cell.textContent : '').toLowerCase();
    }
    return '';
  }

  /* ======== Inline Editing ======== */
  function attachEditableCells() {
    var cells = document.querySelectorAll('#bom-table td.editable');
    for (var i = 0; i < cells.length; i++) {
      cells[i].setAttribute('contenteditable', 'true');
      cells[i].addEventListener('blur', onEditBlur);
      cells[i].addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          this.blur();
        }
        if (e.key === 'Escape') {
          this.textContent = this.dataset.originalValue || this.textContent;
          this.blur();
        }
      });
      cells[i].addEventListener('focus', function() {
        this.dataset.originalValue = this.textContent;
      });
    }
  }

  function onEditBlur() {
    var cell = this;
    var newValue = cell.textContent.trim();
    var oldValue = cell.dataset.originalValue || '';
    if (newValue === oldValue) return;

    var field = cell.dataset.field;
    var cabinet = cell.dataset.cabinet;
    var material = cell.dataset.material;
    if (!field || !cabinet || !material) return;

    sendEdit({
      scope: 'bom',
      target: cabinet,
      field_name: field,
      value: newValue,
      material_name: material
    }, function(data) {
      showToast('已更新 ' + field + ': ' + newValue, 'success');
    });
  }

  /* ======== Delete BOM Row ======== */
  function deleteBomRow(btn) {
    var tr = btn.closest('tr');
    if (!tr) return;
    var cabinet = tr.dataset.cabinet;
    var material = tr.dataset.material;
    if (!cabinet || !material) return;
    if (!confirm('确定要删除 ' + cabinet + ' / ' + material + ' 吗？')) return;

    // For deletion, we set a special marker via edit
    // In a full implementation this would have a dedicated DELETE endpoint
    // For now, mark it as removed by setting a remarks field
    sendEdit({
      scope: 'bom',
      target: cabinet,
      field_name: 'remarks',
      value: 'deleted',
      material_name: material
    }, function(data) {
      showToast('已删除: ' + material, 'success');
    });
  }

  /* ======== Issue-to-Table Linking ======== */
  function filterByCabinet(cabinetNo) {
    var filter = document.getElementById('bom-cabinet-filter');
    if (filter) {
      filter.value = cabinetNo;
    }
    filterBomTable();
    document.getElementById('bom-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function jumpToBomRow(materialName, cabinetNo) {
    var filter = document.getElementById('bom-cabinet-filter');
    if (filter && cabinetNo) {
      filter.value = cabinetNo;
    }
    var search = document.getElementById('bom-search');
    if (search) {
      search.value = materialName;
    }
    filterBomTable();
    document.getElementById('bom-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  /* ======== Utility ======== */
  function escHtml(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function escAttr(s) {
    if (!s) return '';
    return String(s).replace(/"/g, '&quot;').replace(/&/g, '&amp;');
  }

  /* ======== Init ======== */
  document.addEventListener('DOMContentLoaded', function() {
    attachEditableCells();
  });
  </script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
