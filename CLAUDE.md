# 汇工云 (HuiGongYun) — CLAUDE.md

## 项目定位
低压电气成套智能报价清单生成系统 MVP。从非结构化资料（DWG/PDF/Excel/Word/图片）自动生成逐柜 BOM、项目汇总 BOM、报价清单与校验报告。

## 当前状态 (2026-06-14)
**Phase 1 & 2 已完成。Phase 3a PDF识别模块已交付。**

已完成闭环：`Excel/Word/DWG输入 → 解析 → 柜体/BOM → 归一 → 报价 → 校验 → JSON/Excel导出 → Web演示壳 + 人工修正回灌`

新增模块：`PDF Vision LLM OCR（GPT-4o/Claude/Gemini）+ Marker本地兜底（免费CPU）`

**当前优先级（按顺序）：**
1. ~~PDF矢量图识别~~ ✅ 已完成（vision_llm.py + marker_adapter.py + pdf.py五级回退链）
2. 版本差异Demo（项目D双版本Excel，投入低回报高）
3. 风险分级体系（在现有7类校验上叠加分级标签）
4. 历史检索RAG（待技术选型）

**暂缓/后推：** 多源融合校验、CI/CD自动测试

## 目录结构
```
src/huigongyun/
  models.py          # 数据模型 (Project/Cabinet/BomLine/QuoteLine/ValidationIssue)
  interfaces.py      # 主流程接口 + 二级抽取/检索接口协议
  parsing/
    base.py          # 解析器基类 ScaffoldFormatParser
    registry.py      # 解析器注册表（按后缀路由）
    excel.py         # Excel 解析（正式，多模板自适应）
    word.py          # Word 解析（段落/表格/约束抽取）
    dwg.py           # DWG 解析（LibreDWG→DXF→ezdxf 文本提取）
    pdf.py           # PDF 解析（五级回退：文本层→Marker→VisionLLM→ocrmypdf→Tesseract）
    vision_llm.py    # Vision LLM 适配器（OpenAI GPT-4o / Claude / Gemini）
    marker_adapter.py# Marker 本地 PDF→Markdown 适配器（免费CPU，~89%表格精度）
    ocr_adapter.py   # Tesseract OCR 适配器（pdf2image + pytesseract）
    constraint_extractor.py  # Word 约束字段抽取（品牌/防护等级/接地方式）
    image.py         # 图片解析骨架（待OCR接入）
  normalization/     # 物料归一（85别名+38品牌 JSON外置词典，RapidFuzz回退）
  generation/        # 逐柜BOM与项目汇总生成
  pricing/           # 报价计算（最小闭环: 单价/小计/汇总/总价/缺价提示）
  validation/        # 7类校验: 缺项/重复/品牌冲突/长交期/缺价/pending_*
  export/            # JSON + Excel 7 sheets导出
  storage/           # PostgreSQL持久化
  retrieval/         # 历史检索接口（预留，未实现）
  indexing/          # 柜体索引
  adapters/          # 默认适配器
  config.py          # 应用配置 dataclass
  tasks.py           # Celery异步任务
  webapp.py          # Flask轻量Web演示壳
  pipeline.py        # 默认流水线编排
scripts/
  demo.py            # 一键演示
  validate_dwg.py    # DWG质量评估
tests/
  unit/              # 单元测试 (99个)
  integration/       # 集成测试
  e2e/               # 端到端测试
docs/                # 设计文档 + 初赛提案
examples/            # 样例数据（大文件，不提交Git）
.claude/             # Claude Code 配置（settings/agents/workflows）
```

## PDF 解析流水线（五级回退）

```
PdfOcrParser.parse(pdf_path)
  1. 文本层检测 (pdfminer)     → 有文本层 → Marker增强提取（免费ML，表格89%精度）
  2. Marker 本地 OCR           → 免费CPU，无文本层也可尝试（内部渲染+ML）
  3. Vision LLM                → GPT-4o/Claude/Gemini，CAD矢量PDF主力（需API Key）
  4. ocrmypdf                  → 扫描件OCR（可选依赖）
  5. Tesseract                 → 传统OCR最终兜底（可选依赖）
```

环境变量配置：
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` → Vision LLM 后端选择
- `VISION_LLM_PROVIDER` → 指定后端（openai/anthropic/google，默认 openai）
- `VISION_LLM_MODEL` → 覆盖默认模型名
- 无 API Key 时自动跳过 Vision LLM，使用免费路径

## 工程原则
1. **MVP优先** — 最小可运行闭环先于全覆盖，每次只推进一个闭环
2. **模块化接口** — parser/normalizer/generator/validator/exporter 可独立替换
3. **可追溯** — 每条BOM记录保留来源文件、置信度、规则名
4. **人工确认优先** — 人工修正覆盖自动识别，保留AuditLog
5. **先骨架后规则** — 先可运行骨架，再补业务规则，每步补测试
6. **报价后置** — 报价不耦合解析层，基于汇总BOM二次计算
7. **依赖可选** — 重型依赖（OCR/ML/大模型SDK）lazy import + 优雅回退

## Agent 体系 (`.claude/agents/`)
- `orchestrator` — 统筹排期分派 (read/search/todo/agent)
- `etl_ingestion` — 资料解析与字段映射 (read/search/edit/execute)
- `algorithm` — BOM生成与归一 (read/search/edit/execute)
- `code_guardian` — 审查与回滚 (read/search/execute)
- `web_ui` — 轻量演示壳 (read/search/edit/execute)
- `release_docs` — 交付文档 (read/search/edit)
- `research` — 只读调研 (read/search)

原则：权限最小化，实现类agent只改相关模块，code_guardian在合入前审查。

## 技术栈
- 核心: Python>=3.10, Flask, openpyxl, RapidFuzz
- PDF: pdfminer.six, pdfplumber, pdf2image, pytesseract (可选)
- PDF ML: marker-pdf (可选，~5GB模型首次下载，CPU可跑)
- Vision LLM: openai / anthropic / google-generativeai (可选，需API Key)
- DWG: LibreDWG(系统依赖) + ezdxf
- 基础设施: Celery, Redis, PostgreSQL, MinIO
- 测试: pytest, ruff (line-length=120)
- 部署: Docker Compose (API + Worker + DB + Redis + MinIO)

## 大文件/样例数据
- `examples/` 目录含样例DWG/PDF/Excel文件，较大文件不提交Git（已在.gitignore）
- 原 `example0516.` 目录已删除（git: 5817738），Windows下目录名不能以`.`结尾
- Marker 模型缓存: `C:\Users\<user>\AppData\Local\datalab` (Windows) / `~/.cache/huggingface` (Linux)

## 关键约定
- 修改代码前先读 `项目核心文档.md` 确认需求
- 查看 `工作流确认.md` 了解已完成/未完成清单
- 新增功能从最小闭环开始，不同时扩展多个方向
- 所有关键决定保留证据链
- 价格优先级: 人工确认 > 价格表 > 样例价格 > 缺价占位
- CI/CD 自动测试暂不启用，测试手动运行 (`pytest tests/unit/`)
- Heavy deps 通过 lazy import 加载，缺失时优雅回退不崩溃
