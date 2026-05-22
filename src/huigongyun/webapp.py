from __future__ import annotations

import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path

from flask import Flask, abort, render_template_string, request, send_file, url_for

from .bootstrap import build_context, build_default_pipeline


RUN_STORAGE: dict[str, Path] = {}


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        return render_template_string(
            INDEX_TEMPLATE,
            last_result=None,
            error=None,
        )

    @app.post("/run")
    def run_pipeline() -> str:
        uploaded = request.files.get("input_file")
        if uploaded is None or not uploaded.filename:
            return render_template_string(INDEX_TEMPLATE, last_result=None, error="请先选择一个 Excel 文件。")

        run_id = uuid.uuid4().hex
        run_dir = Path(tempfile.mkdtemp(prefix=f"huigongyun-{run_id}-"))
        input_path = run_dir / uploaded.filename
        uploaded.save(input_path)

        output_dir = run_dir / "output"
        pipeline = build_default_pipeline()
        result = pipeline.run(build_context(str(input_path), str(output_dir)))
        RUN_STORAGE[run_id] = run_dir

        summary = {
          "run_id": run_id,
            "project_name": result.project.project_name,
            "cabinet_count": len(result.cabinets),
            "bom_line_count": len(result.bom_lines),
            "summary_count": len(result.summary),
            "issue_count": len(result.issues),
            "outputs": result.outputs,
          "download_links": {
            key: url_for("download_artifact", run_id=run_id, filename=Path(path).name)
            for key, path in result.outputs.items()
          },
            "issues": [asdict(issue) for issue in result.issues],
            "cabinets": [asdict(cabinet) for cabinet in result.cabinets],
            "bom_lines": [asdict(bom_line) for bom_line in result.bom_lines],
        }

        return render_template_string(
            INDEX_TEMPLATE,
            last_result=summary,
            error=None,
        )

    @app.get("/download/<run_id>/<path:filename>")
    def download_artifact(run_id: str, filename: str):
        run_dir = RUN_STORAGE.get(run_id)
        if run_dir is None:
            abort(404)
        file_path = run_dir / "output" / filename
        if not file_path.exists():
            abort(404)
        return send_file(file_path, as_attachment=True)

    return app


def main() -> int:
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=False)
    return 0


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
    </div>
    {% endif %}
  </div>
</body>
</html>
"""
