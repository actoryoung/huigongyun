# 汇工云 (HuiGongYun) — 低压电气成套智能报价清单生成系统

从非结构化资料（DWG/PDF/Excel/Word/图片）自动生成逐柜 BOM、项目汇总 BOM、报价清单与校验报告。输出可追溯、支持人工修正、可导出。

## 当前能力

- **多格式解析**: Excel / Word / DWG (AC1015/1018) / PDF (五级回退链: 文本层→Marker→VisionLLM→ocrmypdf→Tesseract)
- **多源融合**: 目录感知分发 (MultiSourceParser) + 5 条跨源柜号一致性校验
- **物料归一**: 22 类物料 + 13 品牌 + 5 单位 JSON 外置词典，RapidFuzz 模糊回退 + 品牌回退链
- **物料相似匹配**: EmbeddingMaterialMatcher，基于 sentence-transformers 向量余弦相似度
- **历史检索 RAG**: FAISS + sentence-transformers，Pipeline 可选集成
- **报价生成**: 单价/小计/柜体汇总/项目总价/缺价提示
- **校验引擎**: 7 类本地规则 + 5 条跨源规则 + 风险分级 (RiskClassifier)
- **版本差异**: VersionDiffer，柜体/BOM/汇总三级差异对比
- **导出**: JSON + Excel 7 sheets + MinIO presigned URL
- **Web 演示壳**: Flask，上传→运行→展示→下载→人工修正→重导出
- **基础设施**: PostgreSQL 持久化 / Celery 异步任务 / MinIO 对象存储

## 快速开始

```bash
# 安装依赖
pip install -r requirements-dev.txt

# 运行测试 (注意排除 reference/ 和 ROS 2 launch_testing 干扰)
PYTHONPATH=. pytest -p no:launch_testing --ignore=reference

# 命令行运行
PYTHONPATH=. python -m huigongyun /path/to/input.xlsx --output-dir ./output

# 启动 Web 演示壳
PYTHONPATH=. python -m huigongyun.webapp

# 一键演示 (默认项目B)
PYTHONPATH=. python scripts/demo.py
```

## 完整文档

项目权威文档是 **[CLAUDE.md](CLAUDE.md)** — 包含架构概览、目录结构、技术栈、开发环境配置、工程原则、业务规则和 Agent 体系。请在工作前阅读。

## 目录

| 目录 | 说明 |
|------|------|
| `huigongyun/` | 主代码 (models/interfaces/pipeline + 7 个子模块) |
| `tests/` | 187 个测试用例 (unit/integration/e2e) |
| `scripts/` | 演示与验证脚本 |
| `docs/` | 初赛提案 |
| `examples/` | 样例数据 (不提交 Git) |
| `.claude/` | Claude Code 配置 (agents/memory/workflows) |

## 技术栈

Python >= 3.10 / Flask / openpyxl / RapidFuzz / FAISS + sentence-transformers / pdfminer.six / marker-pdf / Celery + Redis / PostgreSQL / MinIO / Docker Compose
