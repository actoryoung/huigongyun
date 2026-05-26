测试指南（简短）

目录约定
- tests/unit/: 单元测试，按模块组织（例如 tests/unit/parsing/）
- tests/integration/: 集成测试，按功能域组织（例如 validation, indexing）
- tests/e2e/: 端到端/系统测试
- tests/fixtures/: 共享测试样例数据

命名规则
- 文件：test_<功能描述>.py
- 测试函数：test_<期望行为>()

每功能 1-5 测试规则
- 对单一函数或方法写 1-3 个单元测试
- 对关键功能写 1-5 个集成测试覆盖正常/错误路径
- E2E 测试覆盖真实用户流程（上传 -> 生成 -> 下载）

运行测试
- 单元测试：`pytest -q tests/unit`
- 集成测试：`pytest -q -m integration`
- 端到端：`pytest -q -m e2e`

将真实样例数据放入 `tests/fixtures/`，并在 `tests/conftest.py` 中提供相应 fixture。

