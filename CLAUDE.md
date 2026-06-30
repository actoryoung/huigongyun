# 汇工云 (HuiGongYun) — CLAUDE.md

## 项目定位

低压电气成套智能报价清单生成系统 MVP。从非结构化资料（DWG/PDF/Excel/Word/图片）自动生成逐柜 BOM、项目汇总 BOM、报价清单与校验报告。目标是输出可追溯、支持人工修正、可导出的结构化结果。

## 当前状态 (2026-06-30)

**Phase 1 & 2 已完成。Phase 3a/3b/3c 已交付。Phase 3d 已实现（可选依赖）。**

### 已交付模块

| 模块 | 状态 | 验收指标 |
|------|------|---------|
| Excel 解析 | ✅ | 项目B:34柜体/379BOM, 项目C:192柜体/1643BOM |
| Word 约束抽取 | ✅ | 项目B:32约束, 项目C:43约束 (品牌/防护等级/接地方式等) |
| DWG 图纸识别 | ✅ | AC1015/1018 格式，项目A:86%质量, 项目D:61%质量 |
| DWG 验证脚本 | ✅ | `scripts/validate_dwg.py` |
| PDF 解析 | ✅ | 五级回退链：文本层→Marker→VisionLLM→ocrmypdf→Tesseract |
| Vision LLM 适配器 | ✅ | OpenAI GPT-4o / Claude / Gemini 三后端 |
| Marker 本地适配器 | ✅ | CPU 可跑，~89%表格精度，免费兜底 |
| 物料归一 | ✅ | 85物料别名+38品牌别名 JSON外置词典，RapidFuzz 模糊回退 |
| 报价生成 | ✅ | 最小闭环：单价/小计/柜体汇总/项目总价/缺价提示 |
| 校验引擎 | ✅ | 7类规则：缺项/重复/品牌冲突/长交期/缺价/pending_* |
| 导出 | ✅ | JSON + Excel 7 sheets + MinIO presigned URL |
| Web 演示壳 | ✅ | Flask，上传→运行→展示→下载→人工修正→重导出 |
| HH Django 前端接线 | ✅ | `src/HH/` git submodule，analyze_file 接入 huigongyun 流水线，Celery 异步+同步回退 |
| 人机协同回灌 | ✅ | Web /edit 端点，BOM/柜体字段编辑后重归一/重校验/重导出 |
| 基础设施 | ✅ | PostgreSQL 持久化 / Celery 异步任务 / MinIO 对象存储 |
| Demo 脚本 | ✅ | `scripts/demo.py` 一键演示 |
| 版本差异 Demo | ✅ | `comparison/` VersionDiffer，项目D 12 单元测试 + 3 集成测试 |
| 风险分级体系 | ✅ | `validation/risk.py` RiskClassifier + 4 升级规则 + RiskDashboard |
| 历史检索 RAG | ✅ | `retrieval/` FAISS + sentence-transformers，Pipeline 可选集成 |

### 未完成 / 暂缓

| 模块 | 状态 | 说明 |
|------|------|------|
| 版本差异 — Web UI | ❌ | diff 可视化待做 |
| Vision LLM API Key 配置 | ⏳ | 待配置 OPENAI/ANTHROPIC/GOOGLE_API_KEY，激活 PDF CAD 图纸识别 |
| 价格表数据接入 | ⏳ | 待用户提供价格表文件，填充 unit_price + price_source |
| SimilarMaterialMatcher 实现 | ❌ | 基于向量检索的物料相似匹配，接口已预留 |
| 多源融合校验 | ❌ | Excel+DWG+Word跨源柜号一致性，等待三模块各自稳定 |
| DWG AC1032 | ⏸ | 需ODA Converter (商业许可)，LibreDWG不支持 |
| 复杂商务报价 | ⏸ | 税率/折扣/运费/利润模型，不在当前scope |
| CI/CD 自动测试 | ⏸ | 暂不启用，测试手动运行 `pytest` |

### 当前优先级（按顺序）

1. ~~PDF矢量图识别~~ ✅ (vision_llm.py + marker_adapter.py + pdf.py 五级回退链)
2. ~~版本差异 Demo~~ ✅ (comparison/differ.py + scripts/demo_version_diff.py)
3. ~~风险分级体系~~ ✅ (validation/risk.py RiskClassifier + ValidationIssue.risk_level)
4. ~~历史检索 RAG~~ ✅ (retrieval/faiss_index.py FaissCaseRetriever)
5. **价格表数据接入** — 待用户提供价格表文件
6. **Vision LLM API Key 配置** — 激活 PDF CAD 图纸 Vision LLM 识别路径

## 架构概览

```
输入文件(DWG/PDF/Excel/Word/图片)
  → parsing/      — 格式解析器（按后缀路由），输出 ProjectDocument
  → normalization/— 物料名/品牌/规格/单位归一
  → generation/   — 逐柜BOM + 项目汇总BOM
  → pricing/      — 基于汇总BOM二次报价计算（不耦合解析层）
  → validation/   — 7类校验规则
  → export/       — JSON + Excel 7 sheets
  → webapp.py     — Web演示壳 + 人工修正回灌
```

**核心原则：** Parser → Normalizer → Generator → Pricer → Validator → Exporter 均可独立替换，通过 `interfaces.py` 协议连接。

## 目录结构

```
src/huigongyun/
  models.py              # 数据模型 (ProjectDocument/ProjectResult/CabinetRecord/
                         #   MaterialRecord/BomLine/QuoteLine/ValidationIssue/SourceRef)
  interfaces.py          # 主流程接口 + 二级抽取/检索接口协议
  config.py              # 应用配置 dataclass (AppConfig/ParsingConfig/MatchingConfig/ExportConfig)
  pipeline.py            # 默认流水线编排
  bootstrap.py           # 依赖组装
  exceptions.py          # 自定义异常
  cli.py                 # 命令行入口
  webapp.py              # Flask轻量Web演示壳
  __main__.py            # python -m huigongyun 入口

  parsing/
    base.py              # 解析器基类 ScaffoldFormatParser
    registry.py          # 解析器注册表（按后缀路由）
    excel.py             # Excel 解析（正式，多模板自适应：表头检测/元数据提取/噪声过滤）
    word.py              # Word 解析（段落/表格抽取）
    constraint_extractor.py  # Word 约束字段抽取（品牌/防护等级/接地方式/柜型/IP等级）
    dwg.py               # DWG 解析（LibreDWG→DXF→ezdxf 文本提取）
    pdf.py               # PDF 解析（文本层检测 + 五级回退路由）
    vision_llm.py        # Vision LLM 适配器（OpenAI/Anthropic/Google 三后端）
    marker_adapter.py    # Marker 本地 PDF→Markdown 适配器（免费CPU，~89%表格精度）
    ocr_adapter.py       # Tesseract OCR 适配器（pdf2image + pytesseract）
    image.py             # 图片解析骨架（待OCR接入）
    price_retriever.py   # 价格表读取 (LocalPriceTable，孤立工具，待接入 pricing/)

  normalization/         # 物料归一 (default.py: 词典映射 + RapidFuzz 模糊回退)
  generation/            # 逐柜BOM与项目汇总生成
  pricing/               # 报价计算（最小闭环: 单价/小计/汇总/总价/缺价提示）
  validation/            # 7类校验 (default.py: DefaultProjectValidator)
  export/                # JSON + Excel 7 sheets 导出 (spreadsheet.py 含 MinIO)
  storage/               # PostgreSQL 持久化 (postgres_store.py，无 __init__.py，命名空间包)
  retrieval/             # 历史检索 RAG (faiss_index.py FaissCaseRetriever + embeddings/indexer，可选依赖)
  indexing/              # 柜体索引
  adapters/              # 默认适配器

scripts/
  demo.py                # 一键演示（默认项目B，支持 --project C / --web / --input）
  demo_retrieval.py      # RAG 历史检索演示（索引样例 + 相似搜索）
  demo_version_diff.py   # 项目D 两版本物料清单差异对比演示
  validate_dwg.py        # DWG图纸识别质量评估
  ocr_poc.py             # Tesseract OCR 单文件 PoC
  run_integration_pg.sh  # 启动 Postgres 集成测试环境
  check_worker_nonroot.sh # 检查 worker 非 root 运行

tests/
  unit/                  # 单元测试 (112 个用例)
  integration/           # 集成测试
  e2e/                   # 端到端测试
  fixtures/              # 共享测试样例数据

docs/                    # 设计文档 + 初赛提案
examples/                # 样例数据（大文件，不提交Git）
reference/               # 参考开源项目（MinerU/marker，不提交Git）
.claude/                 # Claude Code 配置（settings/agents/workflows/memory）
```

## PDF 解析流水线（五级回退）

```
PdfSourceParser.parse(pdf_path)
  1. 文本层检测 (pdfminer.six)
     ├─ 有文本层 → Marker 增强提取（免费ML，表格~89%精度）
     └─ 无文本层（CAD矢量/扫描件）→ 2-5 逐级回退
  2. Marker 本地 OCR   — 免费CPU，内部渲染+ML，无文本层也可尝试
  3. Vision LLM        — GPT-4o/Claude/Gemini，CAD矢量PDF主力（需API Key）
  4. ocrmypdf          — 扫描件OCR引擎（可选依赖）
  5. Tesseract         — 传统OCR最终兜底（可选依赖，pdf2image + pytesseract）
```

**环境变量配置：**
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` → Vision LLM 后端选择
- `VISION_LLM_PROVIDER` → 指定后端 (openai/anthropic/google，默认 openai)
- `VISION_LLM_MODEL` → 覆盖默认模型名
- `VISION_LLM_MAX_TOKENS` → 最大输出 token (默认 4096)
- `VISION_LLM_TEMPERATURE` → 采样温度 (默认 0.0)
- 无 API Key 时自动跳过 Vision LLM，使用免费路径 (Marker/Tesseract)

## 工程原则

1. **MVP优先** — 最小可运行闭环先于全覆盖，每次只推进一个闭环
2. **模块化接口** — Parser/Normalizer/Generator/Validator/Exporter 均可独立替换
3. **可追溯** — 每条BOM记录保留来源文件、置信度、规则名
4. **人工确认优先** — 人工修正覆盖自动识别，保留 AuditLog（事件溯源）
5. **先骨架后规则** — 先可运行骨架，再补业务规则，每步补测试
6. **报价后置** — 报价不耦合解析层，基于汇总BOM二次计算
7. **依赖可选** — 重型依赖（OCR/ML/Vision LLM SDK）lazy import + 优雅回退
8. **价格优先级** — 人工确认价格 > 明确价格表 > 样例价格 > 缺价占位

## 技术栈

| 类别 | 技术 | 备注 |
|------|------|------|
| 语言 | Python >= 3.10 | |
| Web框架 | Flask | 轻量演示壳 |
| Excel处理 | openpyxl | |
| 模糊匹配 | RapidFuzz | 物料归一/品牌映射 |
| PDF文本 | pdfminer.six, pdfplumber | |
| PDF OCR | pdf2image, pytesseract | 可选依赖 |
| PDF ML | marker-pdf | 可选，~5GB模型首次下载，CPU可跑 |
| Vision LLM | openai / anthropic / google-generativeai | 可选，需API Key |
| DWG | LibreDWG(系统依赖) + ezdxf | |
| 异步队列 | Celery + Redis | |
| 数据库 | PostgreSQL | JSONB审计记录 |
| 对象存储 | MinIO | S3兼容，presigned URL |
| 重试策略 | tenacity | |
| 测试 | pytest, ruff (line-length=120) | |
| 部署 | Docker Compose (API + Worker + DB + Redis + MinIO) | |

## 开发环境关键知识

### 包结构与 PYTHONPATH

项目使用**嵌套结构** `src/huigongyun/`（非 flat `src/`）：
- 开发时使用 `PYTHONPATH=src`，无需 `pip install`
- `pip install -e .` 的 editable 模式**不可用**（setuptools build-backend 缺少 `build_editable` hook）
- `pyproject.toml` 中 `[tool.pytest.ini_options] pythonpath = ["src"]` 确保 pytest 能找到包

### 测试运行

```bash
# 注意：必须排除 reference/ 目录（内含 marker/MinerU 的测试会被误收集）
# ROS 2 humble 的 launch_testing 插件会导致 collection 报错，需要 -p no:launch_testing

PYTHONPATH=src pytest -p no:launch_testing --ignore=reference

# 单独运行单元测试
PYTHONPATH=src pytest tests/unit/ -p no:launch_testing --ignore=reference
```

**当前测试状态 (2026-06-23):** 112 collected, 106 passed, 5 failed, 1 skipped
- 3 个 marker_adapter 测试失败（需 `pip install marker-pdf`）
- 2 个 webapp e2e 测试失败（需要 Flask 测试环境配置）

### 已知环境问题

1. **ROS 2 `launch_testing` 插件冲突** — `/opt/ros/humble/lib/python3.10/site-packages/launch_testing/pytest/hooks.py` 干扰 pytest collection，必须使用 `-p no:launch_testing`
2. **`reference/` 目录测试干扰** — `reference/marker/tests/` 需要 `datasets` 等依赖，pytest 会误收集。解决：`--ignore=reference` 或配置 `[tool.pytest.ini_options] norecursedirs = ["reference"]`
3. **Editable install 不可用** — 使用 `PYTHONPATH=src` 代替

## 关键业务规则

- **柜号一致性** — 图纸/清单/配置说明可建立一一对应
- **柜型影响 BOM** — 不同柜型对应典型物料集合
- **额定电流影响规格** — 影响断路器/互感器/母排等
- **接地方式、进出线方式** — 影响辅材配置
- **品牌优先级** — 技术说明指定品牌优先于清单品牌
- **长交期提示** — 在清单中单独标注并提示风险
- **人员确认优先** — 人工修正覆盖自动识别结果

## 关键项目文档

| 文档 | 用途 | 何时阅读 |
|------|------|---------|
| `项目核心文档.md` | 需求与验收的单一事实源 (SoR) | 修改任何业务逻辑前 |
| `工作流确认.md` | 已完成/未完成清单、闭环记录 | 确认当前进度 |
| `任务拆解.md` | Phase 1 & 2 详细任务与验收 | 理解历史决策 |
| `设计提案.md` | 完整的技术提案与路线图 | 架构级变更时 |
| `系统架构设计文档.md` | 生产级架构蓝图 | 基础设施变更时 |
| `解析与检索接口约定.md` | 解析器/检索器接口协议 | 新增解析器/检索能力 |
| `TESTS_GUIDELINES.md` | 测试命名与组织规范 | 写新测试时 |
| `SAMPLE_COMPARISON_REPORT.md` | 样例数据比对报告 | 理解样例数据时 |

## Agent 体系

项目定义了 7 个专用 agent（`.claude/agents/` 和 `.github/agents/`）：

| Agent | 职责 | 权限 |
|-------|------|------|
| `orchestrator` | 统筹排期分派 | read/search/todo/agent |
| `etl_ingestion` | 资料解析与字段映射 | read/search/edit/execute |
| `algorithm` | BOM生成与归一 | read/search/edit/execute |
| `code_guardian` | 审查与回滚 | read/search/execute |
| `web_ui` | 轻量演示壳 | read/search/edit/execute |
| `release_docs` | 交付文档 | read/search/edit |
| `research` | 只读调研 | read/search |

**原则：** 权限最小化，实现类 agent 只改相关模块，`code_guardian` 在合入前审查。

## Memory 系统

项目 Memory 文件（`.claude/memory/`）记录跨对话持久化事实：

| Memory | 类型 | 内容 |
|--------|------|------|
| `pdf-processing-strategy` | project | Vision LLM 主 + Marker 兜底的选型决策 |
| `project-priorities` | project | 当前优先级排序与暂缓事项 |

**Memory 优先级低于 CLAUDE.md** — CLAUDE.md 是项目级权威指令，Memory 是辅助上下文。

## 关键约定（速查）

- 修改代码前先读 `项目核心文档.md` 确认需求
- 新增功能从最小闭环开始，不同时扩展多个方向
- 所有关键决定保留证据链（来源文件/页/行号/规则名）
- 价格优先级: 人工确认 > 价格表 > 样例价格 > 缺价占位
- 重型依赖 (OCR/ML/Vision LLM) lazy import，缺失时优雅回退不崩溃
- CI/CD 自动测试暂不启用，手动运行 `pytest`
- DWG AC1032 (AutoCAD 2018+) 需要 ODA Converter，当前不可用
- `examples/` 和 `reference/` 不提交 Git（已在 .gitignore）
- Marker 模型缓存: `~/.cache/huggingface` (Linux) / `C:\Users\<user>\AppData\Local\datalab` (Windows)
