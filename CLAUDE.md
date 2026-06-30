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
| 物料归一 | ✅ | 22类物料别名+13品牌别名+5单位别名 JSON外置词典，含国产品牌默认映射与规格正则，RapidFuzz 模糊回退 |
| 品牌归一化回退链 | ✅ | 精确匹配→大小写不敏感→别名映射→类别默认品牌→RapidFuzz模糊 |
| 报价生成 | ✅ | 最小闭环：单价/小计/柜体汇总/项目总价/缺价提示 |
| 校验引擎 | ✅ | 7类本地规则 + 5条跨源规则（柜号一致性/数量/冲突等） |
| 多源融合校验 | ✅ | `parsing/multi_source.py` MultiSourceParser + `validation/cross_source.py` 5条跨源规则 |
| 物料相似匹配 | ✅ | `retrieval/matcher.py` EmbeddingMaterialMatcher，基于 sentence-transformers 向量余弦相似度 |
| 导出 | ✅ | JSON + Excel 7 sheets + MinIO presigned URL |
| Web 演示壳 | ✅ | Flask，上传→运行→展示→下载→人工修正→重导出 |
| 人机协同回灌 | ✅ | Web /edit 端点，BOM/柜体字段编辑后重归一/重校验/重导出 |
| 基础设施 | ✅ | PostgreSQL 持久化 / Celery 异步任务 / MinIO 对象存储 |
| Demo 脚本 | ✅ | `scripts/demo.py` 一键演示 |
| 版本差异 Demo | ✅ | `comparison/` VersionDiffer，项目D 12 单元测试 + 3 集成测试 |
| 风险分级体系 | ✅ | `validation/risk.py` RiskClassifier + 4 升级规则 + RiskDashboard |
| 历史检索 RAG | ✅ | `retrieval/` FAISS + sentence-transformers，Pipeline 可选集成 |
| 辅材规则注入 | ✅ | `generation/rules.py` AuxMaterialInjector，柜型/接地/进出线三层叠加，86 用例 |
| HH Django 前端接线 | ✅ | `src/HH/` 外部项目 (String-Wan/HH)，analyze_file 已接入 huigongyun 流水线，PR 工作流 |

### 未完成 / 暂缓

| 模块 | 状态 | 说明 |
|------|------|------|
| 版本差异 — Web UI | ❌ | diff 可视化待做 |
| Vision LLM API Key 配置 | ⏳ | 待配置 OPENAI/ANTHROPIC/GOOGLE_API_KEY，激活 PDF CAD 图纸识别 |
| 价格表数据接入 | ⏳ | 待用户提供价格表文件，填充 unit_price + price_source |
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
输入文件(DWG/PDF/Excel/Word/图片/目录)
  → parsing/      — 格式解析器（按后缀路由，MultiSourceParser 目录感知分发），输出 ProjectDocument
  → normalization/— 物料名/品牌/规格/单位归一（词典映射 + RapidFuzz 模糊 + 品牌回退链）
  → generation/   — 逐柜BOM + 项目汇总BOM
  → pricing/      — 基于汇总BOM二次报价计算（不耦合解析层）
  → validation/   — 7类本地规则 + 5条跨源规则 + 风险分级
  → export/       — JSON + Excel 7 sheets + MinIO presigned URL
  → comparison/   — 版本差异比较（VersionDiffer）
  → retrieval/    — 历史案例检索 (FAISS) + 物料相似匹配 (EmbeddingMaterialMatcher)
  → webapp.py     — Web演示壳 + 人工修正回灌
```

**核心原则：** Parser → Normalizer → Generator → Pricer → Validator → Exporter 均可独立替换，通过 `interfaces.py` 协议连接。

## 目录结构

```
src/huigongyun/
  models.py              # 数据模型 (ProjectDocument/ProjectResult/CabinetRecord/
                         #   MaterialRecord/BomLine/QuoteLine/ValidationIssue/SourceRef)
  interfaces.py          # 主流程接口 + 二级抽取/检索接口协议 (10个Protocol)
  config.py              # 应用配置 dataclass (AppConfig/ParsingConfig/MatchingConfig/ExportConfig)
  pipeline.py            # 默认流水线编排
  bootstrap.py           # 依赖组装
  exceptions.py          # 自定义异常
  cli.py                 # 命令行入口
  webapp.py              # Flask轻量Web演示壳
  tasks.py               # Celery 异步任务 + 同步回退 (process_project)
  __main__.py            # python -m huigongyun 入口

  parsing/
    base.py              # 解析器基类 ScaffoldFormatParser
    registry.py          # 解析器注册表（按后缀路由）
    multi_source.py      # 多源解析器（目录感知分发 + 元数据合并）
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
    dictionaries/        # 外置JSON词典 (materials.json: 物料别名/品牌别名/单位别名/默认品牌/规格正则)

  generation/            # 逐柜BOM与项目汇总生成 (excel_bom.py)
  pricing/               # 报价计算（最小闭环: 单价/小计/汇总/总价/缺价提示）
  validation/            # 校验引擎 (default.py: 7类本地规则 + cross_source.py: 5条跨源规则 + risk.py: 风险分级)
  export/                # JSON + Excel 7 sheets 导出 (spreadsheet.py 含 MinIO presigned URL)
  comparison/            # 版本差异比较 (differ.py VersionDiffer + models.py VersionDiff/CabinetDiff/DiffItem)
  storage/               # PostgreSQL 持久化 (postgres_store.py，无 __init__.py，命名空间包)
  retrieval/             # 历史检索 RAG (faiss_index.py FaissCaseRetriever + embeddings/indexer + matcher.py SimilarMaterialMatcher，可选依赖)
  indexing/              # 柜体索引 (cabinets.py)
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
  unit/                  # 单元测试 (256 个用例，31 个测试文件)
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
| 向量检索 | FAISS, sentence-transformers | 历史案例检索 + 物料相似匹配 |
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

**当前测试状态 (2026-06-30):** 278 collected, 274 passed, 2 failed, 2 skipped
- 2 个 webapp e2e 测试失败（需要 Flask 测试环境配置）
- 2 个 retrieval/ocr 慢测试标记为 skip

### 测试组织规范

- `tests/unit/` — 单元测试，按模块组织（如 `tests/unit/parsing/`）
- `tests/integration/` — 集成测试，按功能域组织（如 `validation`, `indexing`）
- `tests/e2e/` — 端到端/系统测试
- `tests/fixtures/` — 共享测试样例数据
- 文件命名: `test_<功能描述>.py`，函数命名: `test_<期望行为>()`
- 每函数 1-3 个单元测试，每关键功能 1-5 个集成测试覆盖正常/错误路径

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
| `CLAUDE.md` (本文件) | 项目权威文档：架构/状态/约定/环境 | 每次工作前 |
| `任务需求.md` | 赛题原文，验收的最终依据 | 理解需求背景时 |
| `设计提案.md` | 原始技术提案与路线图 | 架构级变更时 |
| `系统架构设计文档.md` | 生产级架构蓝图 | 基础设施变更时 |
| `任务拆解.md` | Phase 1 & 2 详细任务与验收记录 | 理解历史决策 |
| `examples/样例数据说明.md` | 4 个样例项目的用途说明 | 选择测试数据时 |
| `docs/初赛创意提案.md` | 初赛提交材料 | 外部参考 |

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

## 模型使用原则

为控制 token 消耗，重要工作使用 Pro 模型（deepseek-v4-pro），其余全部使用 Flash 模型（deepseek-v4-flash）。Flash 成本远低于 Pro。

### 主对话（Pro）职责

主对话使用 Pro 模型，聚焦高杠杆工作：

| 场景 | 理由 |
|------|------|
| 架构设计与方案评审 | 跨模块全局视角，tradeoff 决策 |
| 核心数据模型变更 (`models.py`, `interfaces.py`) | 影响全项目数据契约，出错成本高 |
| 复杂业务逻辑（pipeline 编排、归一化链、校验规则） | 多步骤因果推理 |
| 跨 3+ 模块的横切变更 | 需理解模块间交互和副作用 |
| 安全敏感代码 | 不可出错 |
| 复杂 Bug 诊断 | 假设-验证循环，深层原因分析 |
| 审查 Pro 产出代码 | 审查者能力不应低于作者 |
| 模糊需求澄清 | 需判断力和用户沟通 |

### Flash 适用场景

以下工作全部派发给 Flash agent 执行：

| 场景 | 理由 |
|------|------|
| 文件读取/搜索/探索 | 模式匹配，不需深度推理 |
| 简单机械编辑（加字段、更新 import、重命名） | 确定性规则 |
| 为已设计接口写测试 | 测试结构已定，填充用例 |
| 文档更新（CLAUDE.md, README, 注释） | 描述性工作 |
| 样板代码/脚手架 | 复制已有模式 |
| 运行测试并解读结果 | 执行+报告 |
| 根因明确的简单 Bug 修复 | 已知原因→已知修复 |
| 导出/格式化代码 | 机械转换 |

### Agent 模型分配

根据各 agent 职责性质，分配默认模型：

| Agent | 模型 | 理由 |
|-------|------|------|
| `orchestrator` | **haiku** (Flash) | 任务规划/分派是组织性工作，不写业务代码 |
| `etl_ingestion` | **haiku** (Flash) | 解析模块已成熟，新增解析器是机械映射 |
| `algorithm` | **sonnet** (Pro) | 核心引擎：归一化/BOM生成/校验规则，影响全局 |
| `code_guardian` | **sonnet** (Pro) | 代码审查需深度理解；漏报代价高 |
| `web_ui` | **haiku** (Flash) | Flask/Django CRUD，展示层逻辑简单 |
| `release_docs` | **haiku** (Flash) | 文档是描述性、机械性工作 |
| `research` | **haiku** (Flash) | 只读探索，Flash 足够覆盖 |

注：agent frontmatter 中 `sonnet`/`haiku` 分别映射到用户配置的 `ANTHROPIC_DEFAULT_SONNET_MODEL` (Pro) / `ANTHROPIC_DEFAULT_HAIKU_MODEL` (Flash)。

### 动态升级规则

Flash agent 遇到以下情况时**不应自行决策**，应报告主对话（Pro）处理：

1. **需求模糊** — 需要设计决策或 tradeoff 判断
2. **跨模块影响** — 改动波及范围超出当前 agent 授权模块
3. **意外复杂度** — 实际工作量明显超出初始估计
4. **安全/数据完整性风险** — 涉及数据迁移、破坏性变更

### 分析类任务：两段式工作流

项目分析、文档分析等探索型任务采用 **Flash 收集 + Pro 综合** 模式：

```
阶段 1: 信息收集 → research agent (Flash)
  - 定位关键文件、提取相关段落
  - 搜索代码模式、统计分布
  - 输出结构化原始数据（文件清单、匹配行、计数）

阶段 2: 综合判断 → 主对话 (Pro)
  - 接收 Flash 收集的原始数据
  - 识别模式、发现不一致、推导结论
  - 输出分析报告或设计建议
```

**原则：** Flash 负责"找到什么"，Pro 负责"意味着什么"。Flash 不做结论性判断，Pro 不做地毯式搜索。

## Memory 系统

项目 Memory 文件（`.claude/memory/`）记录跨对话持久化事实：

| Memory | 类型 | 内容 |
|--------|------|------|
| `pdf-processing-strategy` | project | Vision LLM 主 + Marker 兜底的选型决策 |
| `project-priorities` | project | 当前优先级排序与暂缓事项 |

**Memory 优先级低于 CLAUDE.md** — CLAUDE.md 是项目级权威指令，Memory 是辅助上下文。

## 关键约定（速查）

- 新增功能从最小闭环开始，不同时扩展多个方向
- 所有关键决定保留证据链（来源文件/页/行号/规则名）
- 价格优先级: 人工确认 > 价格表 > 样例价格 > 缺价占位
- 重型依赖 (OCR/ML/Vision LLM) lazy import，缺失时优雅回退不崩溃
- CI/CD 自动测试暂不启用，手动运行 `pytest`
- DWG AC1032 (AutoCAD 2018+) 需要 ODA Converter，当前不可用
- `examples/` 和 `reference/` 不提交 Git（已在 .gitignore）
- Marker 模型缓存: `~/.cache/huggingface` (Linux) / `C:\Users\<user>\AppData\Local\datalab` (Windows)
