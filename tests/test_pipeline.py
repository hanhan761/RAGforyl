from __future__ import annotations

import json

from ragforyl.answering import AnswerService
from ragforyl.exporter import export_graph
from ragforyl.pipeline import BuildPipeline
from ragforyl.retrieval import KnowledgeBase

DOCUMENT = """# 飞行力学基础

## 升力与攻角

升力系数是描述机翼产生升力能力的无量纲指标。攻角影响升力系数。升力系数影响升力。过大的攻角会导致失速。

## 稳定飞行

稳定平飞时，升力与重力平衡，推力与阻力平衡。配平用于减小持续操纵力。
"""


def test_end_to_end_build_search_answer_and_export(settings_factory, tmp_path) -> None:
    settings = settings_factory()
    settings.source_dir.mkdir(parents=True)
    (settings.source_dir / "flight.md").write_text(DOCUMENT, encoding="utf-8")

    result = BuildPipeline(settings).build()
    knowledge_base = KnowledgeBase(settings.index_dir)
    retrieval = knowledge_base.search("攻角为什么会影响升力？")
    answer = AnswerService(settings, knowledge_base).answer("攻角为什么会影响升力？")
    exported = export_graph(settings.index_dir, tmp_path / "exports", "graphml")

    assert result.quality["passed"] is True
    assert result.manifest["node_count"] > 0
    assert result.manifest["edge_count"] > 0
    assert retrieval["nodes"]
    assert retrieval["sources"]
    assert "攻角" in {node["name"] for node in retrieval["nodes"]}
    assert answer["answer_mode"] == "retrieval_only"
    assert "原文证据" in answer["answer"]
    assert exported[0].read_text(encoding="utf-8").startswith("<?xml")


def test_every_graph_fact_has_valid_evidence(settings_factory) -> None:
    settings = settings_factory()
    settings.source_dir.mkdir(parents=True)
    (settings.source_dir / "flight.md").write_text(DOCUMENT, encoding="utf-8")
    BuildPipeline(settings).build()

    graph = json.loads((settings.index_dir / "graph.json").read_text(encoding="utf-8"))
    chunks = [
        json.loads(line)
        for line in (settings.index_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    evidence_ids = {chunk["evidence_id"] for chunk in chunks}

    assert all(set(node["evidence_ids"]) <= evidence_ids for node in graph["nodes"])
    assert all(set(edge["evidence_ids"]) <= evidence_ids for edge in graph["edges"])
    assert all(node["evidence_ids"] for node in graph["nodes"])
    assert all(edge["evidence_ids"] for edge in graph["edges"])


def test_failed_rebuild_keeps_previous_index(settings_factory) -> None:
    settings = settings_factory()
    settings.source_dir.mkdir(parents=True)
    source = settings.source_dir / "flight.md"
    source.write_text(DOCUMENT, encoding="utf-8")
    first = BuildPipeline(settings).build()

    source.unlink()
    try:
        BuildPipeline(settings).build()
    except RuntimeError:
        pass

    manifest = json.loads((settings.index_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["build_id"] == first.manifest["build_id"]
