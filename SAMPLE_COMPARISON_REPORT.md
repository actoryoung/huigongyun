# Sample Comparison Report（样例比对报告）

概览
- 报告文件：`output/sample_comparison/overall_comparison.json`
- 示例产物：
  - `output/sample_comparison/项目A_IDC机房配电/项目A_系统图_result.json`
  - `output/sample_comparison/项目B_学校配电工程/项目B_主元件清单_result.json`
  - `output/sample_comparison/项目B_学校配电工程/项目B_学校配电工程_comparison.json`

关键发现
- Excel 输入能被解析并提取表格（例如项目B 的 `主元件清单`）。
- DWG 文件通常被标记为需要外部转换（`parse_status: requires_conversion`），因为仓内未配置 DWG→DXF 的转换工具。
- PDF 多为扫描件，当前环境缺少 OCR 渲染/识别支持（缺少 `pdf2image` / `pytesseract`），因此文本层未提取。
- 参考输出（报价表/汇总表）在表结构与命名上差异较大，脚本采用启发式解析，部分参考文件未能提取出物料列表导致比对受限。

当前状态
- 已运行默认流水线并将结果写入 `output/sample_comparison/`（见 `overall_comparison.json`）。
- 已将样例比对脚本 `scripts/sample_compare.py` 与本报告加入仓库并提交。

建议与下一步（可选）
1. 在单独 feature 分支上提交并发起 PR（推荐），PR 内容应包含：说明、CI 依赖清单与回归样例。
   - 命令（示例）：
     ```bash
     git checkout -b feature/sample-comparison
     git add output/sample_comparison SAMPLE_COMPARISON_REPORT.md
     git commit -m "docs: add sample comparison report and outputs"
     git push -u origin feature/sample-comparison
     ```

2. 在本地安装 OCR 依赖并重跑，以改善 PDF 抽取质量：
   ```bash
   pip install pdf2image pytesseract Pillow
   /usr/bin/apt-get install -y poppler-utils tesseract-ocr
   python scripts/sample_compare.py
   ```

3. 强化参考输出解析规则并把失败案例加入回归测试（将 `output/sample_comparison/*_comparison.json` 中的失败条目作为 fixtures）。

复现命令
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/sample_compare.py
```

生成时间：自动化运行时记录于 `output/sample_comparison/overall_comparison.json`
