from ragforyl.extraction import HeuristicExtractor
from ragforyl.models import Chunk


def make_chunk(text: str) -> Chunk:
    return Chunk(
        id="CHK_demo",
        evidence_id="EV_demo",
        source_id="SRC_demo",
        source_path="demo.md",
        source_title="飞行力学",
        section="升力与攻角",
        ordinal=0,
        text=text,
        sha256="abc",
    )


def test_heuristic_extractor_finds_definitions_and_relations() -> None:
    result = HeuristicExtractor().extract(
        make_chunk(
            "升力系数是描述机翼产生升力能力的无量纲指标。攻角影响升力系数。过大的攻角会导致失速。"
        )
    )

    names = {entity.name for entity in result.entities}
    relation_types = {relation.type for relation in result.relations}

    assert "升力系数" in names
    assert "攻角" in names
    assert "affects" in relation_types
    assert "causes" in relation_types


def test_heuristic_extractor_limits_section_cooccurrence() -> None:
    result = HeuristicExtractor().extract(make_chunk("飞机的基本受力包括升力、重力、推力和阻力。"))

    assert len(result.entities) <= 18
    assert any(relation.type == "includes" for relation in result.relations)
    assert all(relation.source != relation.target for relation in result.relations)
