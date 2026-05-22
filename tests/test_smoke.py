import json

from huigongyun.bootstrap import build_context, build_default_pipeline


def test_default_pipeline_smoke(tmp_path):
    pipeline = build_default_pipeline()
    result = pipeline.run(build_context(input_path=str(tmp_path / "demo.xlsx"), output_dir=str(tmp_path / "out")))

    assert result.project.project_name == "demo"
    assert result.cabinets
    assert result.bom_lines
    assert result.outputs["json"].endswith("demo_result.json")

    payload = json.loads((tmp_path / "out" / "demo_result.json").read_text(encoding="utf-8"))
    assert payload["outputs"]["json"].endswith("demo_result.json")
