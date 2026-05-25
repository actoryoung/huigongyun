from huigongyun.models import BomLine, MaterialRecord, ProjectDocument, ProjectResult
from huigongyun.normalization.default import DefaultMaterialNormalizer


def test_material_normalizer_maps_aliases_and_cleans_fields():
    result = ProjectResult(
        project=ProjectDocument(project_name="demo"),
        bom_lines=[
            BomLine(
                cabinet_no="K1",
                material=MaterialRecord(
                    name="空气开关",
                    spec="MCCB - 250A",
                    unit="M",
                    brand="Schneider",
                    manufacturer="Schneider",
                ),
            )
        ],
        summary=[
            MaterialRecord(
                name="交流接触器",
                spec=" LC1D / 32 ",
                unit="只",
                brand="SIEMENS",
                manufacturer="SIEMENS",
            )
        ],
    )

    normalized = DefaultMaterialNormalizer().normalize(result)

    bom_material = normalized.bom_lines[0].material
    assert bom_material.normalized_name == "断路器"
    assert bom_material.brand == "施耐德"
    assert bom_material.unit == "米"
    assert bom_material.normalized_spec == "MCCB-250A"

    summary_material = normalized.summary[0]
    assert summary_material.normalized_name == "接触器"
    assert summary_material.brand == "西门子"
    assert summary_material.normalized_spec == "LC1D/32"
