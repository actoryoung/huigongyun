from src.models import BomLine, MaterialRecord, ProjectDocument, ProjectResult
from src.normalization.default import DefaultMaterialNormalizer


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
    assert bom_material.brand == "Schneider"          # 原始值保留
    assert bom_material.normalized_brand == "施耐德"   # 归一化结果
    assert bom_material.brand_source == "explicit"
    assert bom_material.unit == "米"
    assert bom_material.normalized_spec == "MCCB-250A"

    summary_material = normalized.summary[0]
    assert summary_material.normalized_name == "接触器"
    assert summary_material.brand == "SIEMENS"         # 原始值保留
    assert summary_material.normalized_brand == "西门子" # 归一化结果
    assert summary_material.brand_source == "explicit"
    assert summary_material.normalized_spec == "LC1D/32"


def test_normalized_brand_field_preserves_original():
    """brand 保留原始值，normalized_brand 承载归一化结果。"""
    result = ProjectResult(
        project=ProjectDocument(project_name="test"),
        bom_lines=[
            BomLine(
                cabinet_no="K1",
                material=MaterialRecord(
                    name="断路器", spec="NSX250", brand="Schneider",
                ),
            )
        ],
    )
    normalized = DefaultMaterialNormalizer().normalize(result)
    m = normalized.bom_lines[0].material
    assert m.brand == "Schneider"          # 原始保留
    assert m.normalized_brand == "施耐德"   # 归一化
    assert m.brand_source == "explicit"


def test_brand_fallback_to_category_inference():
    """品牌为空→类别推断；国产→类别推断→具体品牌。"""
    result = ProjectResult(
        project=ProjectDocument(project_name="test"),
        bom_lines=[
            BomLine(cabinet_no="K1", material=MaterialRecord(
                name="测量电流互感器", spec="LMK-0.66", brand=None,
            )),
            BomLine(cabinet_no="K2", material=MaterialRecord(
                name="塑壳断路器", spec="NSX250", brand="国产",
            )),
        ],
    )
    normalized = DefaultMaterialNormalizer().normalize(result)
    ct = normalized.bom_lines[0].material
    brk = normalized.bom_lines[1].material
    assert ct.normalized_brand == "正泰"     # 互感器→正泰
    assert ct.brand_source == "inferred"
    assert brk.normalized_brand == "常熟"     # 塑壳断路器→常熟
    assert brk.brand_source == "inferred"


def test_brand_fallback_when_no_category_match():
    """无法匹配类别→brand_source=pending, normalized_brand=None。"""
    result = ProjectResult(
        project=ProjectDocument(project_name="test"),
        bom_lines=[
            BomLine(cabinet_no="K1", material=MaterialRecord(
                name="未知器件XYZ", brand=None,
            )),
        ],
    )
    normalized = DefaultMaterialNormalizer().normalize(result)
    m = normalized.bom_lines[0].material
    assert m.normalized_brand is None
    assert m.brand_source == "pending"


def test_brand_fallback_triggers_inference():
    """国产/甲供触发类别推断，主母线类保留结构件通用标记。"""
    result = ProjectResult(
        project=ProjectDocument(project_name="test"),
        bom_lines=[
            BomLine(cabinet_no="K1", material=MaterialRecord(
                name="熔断器", brand="国产",
            )),
            BomLine(cabinet_no="K2", material=MaterialRecord(
                name="主母线", brand="国产",
            )),
        ],
    )
    normalized = DefaultMaterialNormalizer().normalize(result)
    fuse = normalized.bom_lines[0].material
    busbar = normalized.bom_lines[1].material
    assert fuse.normalized_brand == "茗熔"       # 熔断器→茗熔
    assert fuse.brand_source == "inferred"
    assert busbar.normalized_brand is None       # 主母线→结构件，无具体品牌
    assert busbar.brand_source == "pending"
