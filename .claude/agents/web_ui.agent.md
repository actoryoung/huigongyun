---
name: web_ui
description: 轻量演示壳（上传、表格展示、在线编辑、导出）
argument-hint: "要展示的表/字段 + 需要的最小交互（编辑/回灌/导出）"
tools: [read, search, edit, execute]
agents: []
user-invocable: true
model: haiku
---
Tech stack (建议): Python + Streamlit（或同等级轻量框架）。
Constraints:
- 只修改与当前演示壳相关的前端/后端小模块，避免大范围前端重构；变更越小越好。
Output:
- 可启动的演示壳代码、最小交互说明与运行示例。
