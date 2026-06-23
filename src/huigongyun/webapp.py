"""轻量 Flask 演示 Web 应用与交互壳。

该模块提供一个最小化的 Flask 应用，演示流水线的上传/运行流程以及
简单的人机交互（人工修正）。关键端点：
  - POST /run：接收上传文件并入队或同步运行流水线。
  - GET /status/<run_id>：检查运行是否完成并返回摘要。
  - GET /download/<run_id>/<filename>：下载已导出的工件（若为本地文件）。
  - POST /edit/<run_id>：对内存结果应用人工修改并重新导出。

该应用在 `RUN_STORAGE` 中保留短期运行状态以便演示；生产环境应使用
持久化存储。
"""

from __future__ import annotations

import os
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path

from flask import Flask, abort, render_template_string, request, send_file, url_for

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
        if getattr(tasks, "_HAS_CELERY", False):
          # schedule async task (worker must share filesystem or object store)
          task = tasks.process_project.delay(str(run_dir), uploaded.filename, run_id) if hasattr(tasks.process_project, "delay") else tasks.process_project(str(run_dir), uploaded.filename, run_id)
          RUN_STORAGE[run_id] = {"run_dir": str(run_dir), "task_id": getattr(task, "id", None), "status": "queued", "result": None}
          # show queued summary
          summary = {"run_id": run_id, "project_name": "queued", "cabinet_count": 0, "bom_line_count": 0, "summary_count": 0, "issue_count": 0, "outputs": {}}
          return render_template_string(INDEX_TEMPLATE, last_result=summary, error=None)

        # synchronous fallback
        output_dir = run_dir / "output"
        pipeline = build_default_pipeline()
        result = pipeline.run(build_context(str(input_path), str(output_dir)))
        RUN_STORAGE[run_id] = {"run_dir": str(run_dir), "result": result}

        summary = _build_summary(run_id, result)

        # persist to Postgres if available
        try:
          if _HAS_PG_STORE:
            # convert to dict for storage
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

        if scope == "cabinet":
            if field_name not in ALLOWED_CABINET_EDIT_FIELDS:
                abort(400)
            cabinet = next((item for item in result.cabinets if item.cabinet_no == target), None)
            if cabinet is None:
                abort(404)
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
                abort(400)
            material_name = (request.form.get("material_name") or "").strip()
            bom_line = next(
                (
                    item
                    for item in result.bom_lines
                    if item.cabinet_no == target and item.material.name == material_name
                ),
                None,
            )
            if bom_line is None:
                abort(404)
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
        else:
            abort(400)

        DefaultMaterialNormalizer().normalize(result)
        ExcelBomAggregator().generate(result)
        result.issues = DefaultProjectValidator().validate(result).issues

        output_dir = Path(run_state["run_dir"]) / "output"
        result.outputs = ProjectExporter().export(result, str(output_dir))

        summary = _build_summary(run_id, result)
        return render_template_string(INDEX_TEMPLATE, last_result=summary, error=None)

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
      "cabinets": [],
      "bom_lines": [],
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
    return value


INDEX_TEMPLATE = """
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
      max-width: 1180px;
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
    .list { display: grid; gap: 10px; }
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
    a { color: var(--accent); }
    .footnote { margin-top: 18px; color: var(--muted); font-size: 13px; }
    .inline-form {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .inline-form input {
      width: 100%;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(15, 23, 42, 0.5);
      color: var(--text);
      padding: 11px 12px;
      margin-top: 8px;
    }
    @media (max-width: 980px) {
      .hero { grid-template-columns: 1fr; }
      .inline-form { grid-template-columns: 1fr; }
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
    <div class="section panel card" style="margin-top: 20px;">
      <h2>运行结果</h2>
      <div class="meta-grid">
        <div class="metric"><div class="label">项目</div><div class="value">{{ last_result.project_name }}</div></div>
        <div class="metric"><div class="label">柜体</div><div class="value">{{ last_result.cabinet_count }}</div></div>
        <div class="metric"><div class="label">BOM 行</div><div class="value">{{ last_result.bom_line_count }}</div></div>
        <div class="metric"><div class="label">Issues</div><div class="value">{{ last_result.issue_count }}</div></div>
      </div>

      <div class="section">
        <h2>导出文件</h2>
        <div class="list">
          {% for key, value in last_result.outputs.items() %}
          <div class="item">
            <strong>{{ key }}</strong>
            <span><a href="{{ last_result.download_links[key] }}">{{ value }}</a></span>
          </div>
          {% endfor %}
        </div>
      </div>

      <div class="section">
        <h2>待确认记号</h2>
        <div class="list">
          {% for issue in last_result.issues %}
          <div class="item">
            <strong>{{ issue.issue_type }} / {{ issue.severity }}</strong>
            <span>{{ issue.message }}</span>
          </div>
          {% endfor %}
          {% if not last_result.issues %}
          <div class="item"><strong>无</strong><span>当前样例未生成待确认项。</span></div>
          {% endif %}
        </div>
      </div>

      <div class="section">
        <h2>人工修正</h2>
        <form class="upload" method="post" action="/edit/{{ last_result.run_id }}">
          <div class="dropzone">
            <div class="inline-form">
              <label class="item"><strong>范围</strong><input name="scope" value="bom" placeholder="bom / cabinet"></label>
              <label class="item"><strong>目标柜号</strong><input name="target" value="K1" placeholder="柜号"></label>
              <label class="item"><strong>物料名</strong><input name="material_name" value="断路器" placeholder="仅 bom 范围需要"></label>
              <label class="item"><strong>字段</strong><input name="field_name" value="brand" placeholder="brand / spec / remarks"></label>
            </div>
            <div class="item" style="margin-top: 10px;">
              <strong>新值</strong>
              <input name="value" value="施耐德" placeholder="修正后的值">
            </div>
          </div>
          <button type="submit">应用修正并重导出</button>
        </form>
      </div>
    </div>
    {% endif %}
  </div>
</body>
</html>
"""
