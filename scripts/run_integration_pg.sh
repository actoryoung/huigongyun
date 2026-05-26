#!/usr/bin/env bash
set -euo pipefail

# 1. venv + deps
if [ -z "${VIRTUAL_ENV:-}" ]; then
  if [ ! -d ".venv" ]; then
    python3 -m venv .venv
  fi
  source .venv/bin/activate
else
  echo "Using active virtualenv: $VIRTUAL_ENV"
fi
# 2. 启动 Postgres 容器
docker run --name hg-pg -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=huigongyun -p 5432:5432 -d postgres:15

# 3. 等待 DB 就绪（最多 30s）
for i in {1..30}; do
  docker exec hg-pg pg_isready -U postgres && break
  sleep 1
done

# 4. 设置 env（供测试使用）
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/huigongyun

# 5. 确保 runs 表存在（可选，代码可能自建）
docker exec -i hg-pg psql -U postgres -d huigongyun -c "\
CREATE TABLE IF NOT EXISTS runs ( \
  run_id TEXT PRIMARY KEY, \
  summary JSONB, \
  created_at TIMESTAMP DEFAULT now(), \
  updated_at TIMESTAMP DEFAULT now() \
);"

# 6. 运行集成测试（或全部测试）
pytest -q tests/integration || pytest -q

# 7. 清理（按需）
docker stop hg-pg && docker rm hg-pg