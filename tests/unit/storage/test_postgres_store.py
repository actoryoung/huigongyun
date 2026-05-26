import types
import pytest


def test_upsert_sql_contains_on_conflict(monkeypatch, fake_db_mem):
    # simulate configured PG environment
    from huigongyun.storage import postgres_store as pg

    monkeypatch.setattr(pg, "_HAS_PG", True)
    monkeypatch.setattr(pg, "_get_dsn", lambda: "dsn")
    monkeypatch.setattr(pg, "psycopg2", types.SimpleNamespace(extras=types.SimpleNamespace(Json=lambda v: v)), raising=False)

    executed = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=None):
            executed.append(sql if isinstance(sql, str) else str(sql))

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(pg, "_get_conn", lambda dsn: FakeConn(), raising=False)

    ok = pg.save_run_summary("run-123", "/tmp/run", {"project_name": "p"})
    assert ok is True

    joined = " ".join(executed).upper()
    assert "ON CONFLICT" in joined
    assert "RUN_ID" in joined


def test_idempotent_save_with_fake_conn(monkeypatch, fake_db_mem):
    from huigongyun.storage import postgres_store as pg

    monkeypatch.setattr(pg, "_HAS_PG", True)
    monkeypatch.setattr(pg, "_get_dsn", lambda: "dsn")
    monkeypatch.setattr(pg, "psycopg2", types.SimpleNamespace(extras=types.SimpleNamespace(Json=lambda v: v)), raising=False)

    db = {}

    class FakeCursor:
        def __init__(self, storage):
            self._storage = storage

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=None):
            sql_text = sql if isinstance(sql, str) else str(sql)
            if "INSERT INTO runs" in sql_text:
                runid = params[0]
                raw = params[-1]
                self._storage[runid] = raw

    class FakeConn:
        def __init__(self, storage):
            self._storage = storage

        def cursor(self):
            return FakeCursor(self._storage)

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(pg, "_get_conn", lambda dsn: FakeConn(db), raising=False)

    ok1 = pg.save_run_summary("run-x", "/tmp/run", {"project_name": "p", "foo": 1})
    ok2 = pg.save_run_summary("run-x", "/tmp/run", {"project_name": "p2", "foo": 2})

    assert ok1 is True
    assert ok2 is True
    assert "run-x" in db
    assert db["run-x"]["project_name"] == "p2"


def test_save_run_summary_retries_on_transient_error(monkeypatch, fake_db_mem):
    """Simulate transient execute failure on INSERT; expect retry wrapper to retry and succeed."""
    from huigongyun.storage import postgres_store as pg

    monkeypatch.setattr(pg, "_HAS_PG", True)
    monkeypatch.setattr(pg, "_get_dsn", lambda: "dsn")
    monkeypatch.setattr(pg, "psycopg2", types.SimpleNamespace(extras=types.SimpleNamespace(Json=lambda v: v)), raising=False)

    call_state = {"execute_calls": 0}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=None):
            sql_text = sql if isinstance(sql, str) else str(sql)
            # count insert attempts specifically
            if "INSERT INTO runs" in sql_text:
                call_state["execute_calls"] += 1
                if call_state["execute_calls"] == 1:
                    raise Exception("transient db error")
                # on subsequent calls succeed (store not required for this test)
            else:
                # CREATE TABLE and other statements succeed
                pass

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(pg, "_get_conn", lambda dsn: FakeConn(), raising=False)

    # Expecting a retrying wrapper named `save_run_summary_with_retry` to be present.
    assert hasattr(pg, "save_run_summary_with_retry"), "save_run_summary_with_retry not implemented yet"

    res = pg.save_run_summary_with_retry("run-retry", "/tmp/run", {"project_name": "p"})
    assert res is True
    assert call_state["execute_calls"] >= 2
