# 低压电气成套智能报价清单生成系统

这是一个面向低压电气成套项目的 MVP 原型。当前项目已经完成 Excel 主流程最小闭环，并开始把非 Excel 输入、OCR、检索与相似匹配能力以接口和骨架的方式预留出来，方便后续逐步接入：

- 项目资料解析
- 柜体识别与逐柜 BOM 生成
- 物料归一与相似匹配
- 报价汇总与校验报告
- 人机协同修正与导出

## 当前进度

- 已完成 Excel 主元器件清单解析、柜体清单生成、逐柜 BOM、项目汇总 BOM、基础校验、报价最小闭环、JSON / Excel 导出。
- 已完成轻量 Web 演示壳与最小人机协同回灌闭环，可对 BOM / 柜体字段做人工修正后重导出。
- 已完成 PDF、Word、图片、DWG 的解析适配器骨架，以及 OCR / 文档抽取 / 历史检索 / 相似匹配的接口预留。
- 暂未实现的部分主要是图纸深度识别、多模态 OCR、RAG 检索、复杂商务报价和高级版本差异分析。

## 当前能力

- 核心流程：输入接入 → 结构化解析 → 柜体/BOM 生成 → 归一 → 报价 → 校验 → 导出
- 模块化设计：解析、归一、生成、报价、校验、导出均通过接口协议连接，便于替换实现
- 资料覆盖：Excel 已正式实现，PDF / Word / 图片 / DWG 已预留骨架
- 检索与匹配：已预留 OCR、文档抽取、历史案例检索、相似物料匹配接口
- 追溯能力：保留来源行号、来源文件、价格来源和 `pending_*` 记号
- 交互能力：支持 CLI 与轻量 Web 演示壳，支持最小人工修正回灌

## 模块简介

- `src/huigongyun/models.py`: 核心数据结构，承载项目、柜体、物料、报价、校验与导出结果
- `src/huigongyun/interfaces.py`: 全局协议层，定义解析、抽取、归一、生成、校验、导出与检索接口
- `src/huigongyun/parsing/`: 输入解析层，Excel 为正式实现，其余格式为骨架实现
- `src/huigongyun/retrieval/`: 历史案例检索与相似匹配接口预留
- `src/huigongyun/normalization/`: 物料名称、规格、品牌和单位的轻量归一
- `src/huigongyun/generation/`: 柜体与 BOM 生成与汇总
- `src/huigongyun/pricing/`: 报价最小闭环与价格表读取
- `src/huigongyun/validation/`: 基础校验、待确认记号和风险提示
- `src/huigongyun/export/`: JSON / Excel 导出
- `src/huigongyun/webapp.py`: 轻量 Web 演示壳与回灌入口
- `tests/`: 当前最小闭环的回归测试

## 运行方式

```bash
python -m pip install -e .
huigongyun --help
```

## 目录说明

- `src/huigongyun/models.py`: 项目、柜体、物料、报价、校验和导出结果的数据模型
- `src/huigongyun/interfaces.py`: 主流程接口与二级抽取/检索接口
- `src/huigongyun/bootstrap.py`: 默认流水线组装
- `src/huigongyun/pipeline.py`: 端到端编排
- `src/huigongyun/adapters/`: 默认适配器与未来替换入口
- `src/huigongyun/parsing/`: Excel、PDF、Word、图片、DWG 的解析入口与骨架
- `src/huigongyun/retrieval/`: 历史案例检索与相似匹配接口
- `src/huigongyun/normalization/`: 轻量归一层
- `src/huigongyun/generation/`: 柜体与 BOM 生成层
- `src/huigongyun/pricing/`: 报价生成层
- `src/huigongyun/validation/`: 校验层
- `src/huigongyun/export/`: 导出层
- `src/huigongyun/cli.py`: 命令行入口
- `tests/`: 当前回归测试

## 下一步

1. 接入 OCR / 文档抽取的真实实现
2. 接入历史案例检索与相似物料匹配
3. 扩展图纸 / PDF / 图片输入的真实解析逻辑
4. 补充更完整的人机协同回灌、演示脚本和性能评估

## 当前计划进程

- 已完成：Excel 解析、柜体清单、逐柜 BOM、项目汇总、归一、报价最小闭环、基础校验、JSON/Excel 导出、Web 演示壳、最小回灌闭环。
- 已预留：PDF / Word / 图片 / DWG 解析骨架，OCR / 文档抽取 / 历史检索 / 相似匹配接口。
- 未完成：真实多格式解析、复杂商务报价、高级校验、变更分析、演示脚本与完整评估报告。
- 暂缓：复杂支持和高级校验先不做，保留接口与 `pending_*` 记号，等待后续数据格式正式下发。

### 近期进展（2026-05-26）

- 已实现：Postgres 写入与 upsert（参见 src/huigongyun/storage/postgres_store.py），用于持久化运行/审计记录。
- 已实现：任务层支持 Celery 异步任务并内建同步回退与重试策略（参见 src/huigongyun/tasks.py）。
- 已实现：OCR PoC（TesseractAdapter）与演示脚本（src/huigongyun/parsing/ocr_adapter.py、scripts/ocr_poc.py）。
- 已实现：导出器对 MinIO presigned URL 的 host/scheme 重写（参见 src/huigongyun/export/spreadsheet.py），支持 MINIO_PUBLIC_URL 环境变量。
- 已实现：基本 CI 工作流已添加（.github/workflows/ci.yml）并推送到远端。
- 本地测试：近期本地单元测试显示通过（历史记录：17 → 15 tests），但在自动化 runner 中多次遇到 pytest 或系统依赖不可用的情况（建议在 CI 中安装 tesseract、poppler-utils 以支持 OCR/integration tests）。
- 待办：确认并移除/归档仓库中的大文件（例如 get-pip.py、huigongyun.egg-info、output/），并把 runtime 依赖同步到 pyproject.toml；在 CI 中增加系统包安装步骤以保证集成测试可运行。

## 给 qi 的简要总结

- 项目已经跑通 Excel 主闭环，能够生成柜体、逐柜 BOM、项目汇总、报价和导出文件。
- 当前的重点不在“再堆功能”，而在“把后续能力的接口和边界定清楚”，这样多格式输入、OCR、检索和大模型都能按需插入。
- 现在适合总结的关键词是：可运行原型、分层架构、接口预留、可追溯、最小报价闭环、Web 回灌、逐步扩展。

## 运行验证

```bash
python -m pip install -e .[dev]
pytest
python -m huigongyun /path/to/input.xlsx --output-dir ./output
huigongyun-web
```

Web 演示壳也可以用下面方式安装和启动：

```bash
python -m pip install -e .[web]
huigongyun-web
```

## 当前输出

- `*_result.json`: 项目结构化结果，包含柜体、BOM、汇总、校验和导出路径
- `*_result.xlsx`: 结构化 Excel 结果，包含 `Project`、`Cabinets`、`BOM`、`Summary`、`Issues` 工作表

## Postgres: 配置、持久化与备份（开发/演示用）

项目在 `docker-compose.yml` 中包含了一个 `postgres` 服务，用于保存异步任务的运行记录和审计信息。

- 密码与凭据：当前示例使用环境变量 `POSTGRES_PASSWORD`（在 `docker-compose.yml` 中为 `secret`）。**上线前请更改该密码，并使用 Docker secrets 或外部密钥管理服务来注入凭据，切勿把明文凭据提交到版本库。**

- 持久化：数据库数据存储在名为 `postgres_data` 的 Docker 卷中（映射到容器内 `/var/lib/postgresql/data`）。此卷在 `docker-compose.yml` 中声明以保证容器重启/重建时数据不丢失。

- 备份与恢复：可使用逻辑备份（pg_dump）或卷归档两种方式。

 逻辑备份（推荐）：

```bash
# 在宿主机上导出数据库（生成 SQL 文件）
docker compose exec -T postgres pg_dump -U huigongyun huigongyun > backup.sql

# 恢复
docker compose exec -T postgres psql -U huigongyun -d huigongyun < backup.sql
```

 卷级别归档（备份原始文件）：

```bash
# 将卷内容打包到宿主当前目录
docker run --rm -v huigongyun_postgres_data:/data -v $(pwd):/backup alpine \
	sh -c "cd /data && tar czf /backup/postgres_data.tgz ."

# 恢复（将归档复制到新卷）
docker volume create restore_tmp
docker run --rm -v restore_tmp:/data -v $(pwd):/backup alpine \
	sh -c "cd /data && tar xzf /backup/postgres_data.tgz"
```

注意：卷级别备份直接操作底层数据文件，可能在 Postgres 活动期间出现一致性问题；对于生产环境，请优先使用 `pg_dump` 或 PostgreSQL 提供的物理备份工具（如 `pg_basebackup`）并在维护窗口内进行。

更多：`docker-compose.yml` 中包含了注释说明，指出了密码更改、数据卷和备份示例的用法。
## MinIO 与导出（Presigned URL）

导出器会将 JSON/Excel 工件上传至 MinIO 并生成 presigned URL。若你需要在宿主机/浏览器中通过不同的 host/scheme 访问这些链接，请设置环境变量 `MINIO_PUBLIC_URL`（例如 `http://localhost:9000`）。当设置该变量时，导出器会用 `MINIO_PUBLIC_URL` 的 scheme 和 host 替换 presigned URL 的 scheme/host，从而使链接在宿主环境中可访问。

关键环境变量：
- `MINIO_ENDPOINT`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`
- `MINIO_BUCKET`
- `MINIO_PUBLIC_URL`（可选 — 用于替换 presigned URL 的 host/scheme）

示例使用（本地运行）：
```bash
export MINIO_ENDPOINT=minio:9000
export MINIO_ACCESS_KEY=minioadmin
export MINIO_SECRET_KEY=minioadmin
export MINIO_BUCKET=exports
export MINIO_PUBLIC_URL=http://localhost:9000
# 运行导出流程（示例）
python -m huigongyun --export --output-bucket $MINIO_BUCKET
```

## OCR PoC（Tesseract）

仓库包含 OCR PoC，使用 Tesseract + `pdf2image`，adapter 位于 `src/huigongyun/parsing/ocr_adapter.py`，演示脚本为 `scripts/ocr_poc.py`。运行前需在系统级安装 `tesseract` 和 `poppler`（例如 `pdftoppm` 可用）。示例：
```bash
python scripts/ocr_poc.py tests/fixtures/ocr_sample.png
```

## 依赖说明

- `requirements.txt`/`requirements-dev.txt`：列出用于本地开发与 CI 的常用依赖。建议用于快速安装与本地运行。
- `pyproject.toml`：包含打包/发布元数据；当前可能未列出全部 runtime extras。建议在发布前将 runtime 依赖同步到 `pyproject.toml` 的 `project.dependencies`，或在 README 中明确说明两者的用途。

本地快速安装示例：
```bash
python -m pip install -r requirements-dev.txt
python -m pip install -e .
```
