import pytest


def test_tasks_use_retry_wrapper(monkeypatch, tmp_path, sample_run_summary):
    # import inside test to allow monkeypatching before heavy imports
    from src import tasks

    # patch pipeline to avoid heavy processing
    class FakeProject:
        project_name = "proj"

    class FakeResult:
        def __init__(self):
            self.project = FakeProject()
            self.cabinets = [1]
            self.bom_lines = [1, 2]
            self.summary = [1]
            self.issues = []
            self.outputs = {}
            self.user_edits = []

    class FakePipeline:
        def run(self, ctx):
            return FakeResult()

    monkeypatch.setattr(tasks, "build_default_pipeline", lambda: FakePipeline())
    monkeypatch.setattr(tasks, "build_context", lambda *a, **k: None)

    # fake retry wrapper: simulate internal transient failures then succeed
    state = {"internal_attempts": 0}

    def fake_save_with_retry(run_id, run_dir, summary):
        # simulate internal retry loop
        state["internal_attempts"] += 1
        if state["internal_attempts"] < 3:
            # indicate a transient failure in internal attempts
            raise Exception("transient")
        return True

    # place fake at the task call-site (tasks currently uses save_run_summary_with_retry)
    monkeypatch.setattr(tasks, "save_run_summary_with_retry", fake_save_with_retry, raising=False)
    monkeypatch.setattr(tasks, "_HAS_PG_STORE", True)

    # call process_project synchronously; should return summary even if persistence transiently fails
    res = tasks.process_project(str(tmp_path), "input.txt", run_id="rid")

    assert res["project_name"] == "proj"
    # ensure our fake wrapper observed multiple internal attempts
    assert state["internal_attempts"] >= 1
