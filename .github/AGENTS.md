# Agent Roster

- `orchestrator`: coordinate tasks, planning, and delegation.
- `code_guardian`: review, testing, and rollback safety.
- `etl_ingestion`: document parsing and field extraction.
- `algorithm`: material normalization, matching, and rule logic.
- `web_ui`: lightweight UI prototyping.
- `release_docs`: README, usage, and deliverable docs.
- `research`: read-only repo exploration and issue triage.

Usage guidance:
- Keep implementation focused on the MVP path first: Excel parsing, cabinet extraction, BOM generation, validation, and export.
- Prefer small adapter interfaces so parser, normalizer, generator, validator, and exporter can be swapped independently.
# AGENTS 索引（中文）

原则：
- 权限最小化：每个 agent frontmatter 中的 `tools` 列表为其权限范围，不在其中的能力不得使用。
- 实现类 agent（etl_ingestion / algorithm / web_ui）：只允许修改与当前任务直接相关的模块/文件，避免顺手重构。
- code_guardian：作为合入前的安全网，按 orchestrator 指派在里程碑/合入点进行审查并可触发回滚步骤。

Agent Roster
- orchestrator: 统筹、排期、分派；tools: read, search, todo, agent
- code_guardian: 代码审查与回滚支持；tools: read, search, execute
- etl_ingestion: 资料解析与字段映射；tools: read, search, edit, execute
- algorithm: BOM 生成与归一逻辑；tools: read, search, edit, execute
- web_ui: 轻量演示壳；tools: read, search, edit, execute
- release_docs: 交付文档与演示材料；tools: read, search, edit
- research: 只读调研；tools: read, search

何时调用（Phase 1 推荐工作流）
1. orchestrator 拆解任务并把子任务交给相应 agent（输入模板参见下方）。
2. etl_ingestion 完成解析/字段映射后，把中间结构交给 algorithm。
3. algorithm 输出逐柜 BOM / 汇总 BOM 与校验报告，交由 web_ui 展示与 release_docs 撰写。
4. 在里程碑或合入 main 前，orchestrator 指派 code_guardian 审查（若发现阻断，按其回滚步骤执行）。
5. research 可在任何需要背景/定位时被调用（只读）。

任务交付输入模板（示例）
- 输入：{ "task":"解析 Excel","files":["样例.xlsx"], "target_fields":["cabinet","part_no","qty"], "expect":"逐柜 BOM Excel/JSON" }
- 输出期望：可运行解析模块、字段映射表、异常报告、样例导出。

Code Guardian 使用说明（简要）
- 在准备合入 main 分支前调用：提供改动范围、期望验收点（测试/lint/安全点）。
- code_guardian 会返回：审查结论、可复现命令（测试/lint 命令）、风险点、回滚/撤回步骤（git 命令）。
