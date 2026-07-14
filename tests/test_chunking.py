from ragforyl.chunking import chunk_document
from ragforyl.models import SourceDocument


def test_heading_aware_chunks_are_stable_and_traceable() -> None:
    document = SourceDocument(
        id="SRC_demo",
        title="飞行力学",
        relative_path="flight.md",
        sha256="abc",
        text=(
            "# 飞行力学\n\n## 升力\n\n升力是垂直于相对来流方向的空气动力。"
            "\n\n## 阻力\n\n阻力与运动方向相反。"
        ),
        size_bytes=100,
    )

    first = chunk_document(document, chunk_size=300, overlap=30)
    second = chunk_document(document, chunk_size=300, overlap=30)

    assert [chunk.id for chunk in first] == [chunk.id for chunk in second]
    assert [chunk.section for chunk in first] == ["升力", "阻力"]
    assert all(chunk.evidence_id.startswith("EV_") for chunk in first)
    assert all(chunk.source_path == "flight.md" for chunk in first)


def test_long_paragraph_is_split_without_losing_text() -> None:
    text = "升力随速度变化。" * 100
    document = SourceDocument("SRC_long", "长文档", "long.txt", "def", text, len(text))

    chunks = chunk_document(document, chunk_size=300, overlap=20)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 320 for chunk in chunks)
    assert "升力随速度变化" in chunks[-1].text
