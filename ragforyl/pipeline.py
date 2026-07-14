from __future__ import annotations

import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ragforyl.chunking import chunk_documents
from ragforyl.config import Settings
from ragforyl.extraction import ExtractionEngine
from ragforyl.graph import build_graph, build_mappings, build_runtime_graph, validate_graph
from ragforyl.io import load_source_documents, write_json, write_jsonl

ProgressCallback = Callable[[str, int, int], None]


@dataclass(slots=True)
class BuildResult:
    manifest: dict[str, object]
    quality: dict[str, object]
    index_dir: Path


class BuildPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build(self, progress: ProgressCallback | None = None) -> BuildResult:
        self.settings.ensure_directories()
        if self.settings.source_dir == self.settings.index_dir:
            raise ValueError("source_dir and index_dir must be different")
        documents = load_source_documents(self.settings.source_dir)
        _report(progress, "读取文档", len(documents), len(documents))
        chunks = chunk_documents(documents, self.settings.chunk_size, self.settings.chunk_overlap)
        if not chunks:
            raise RuntimeError("No chunks were produced from the source documents")

        engine = ExtractionEngine(self.settings)
        extractions = []
        for index, chunk in enumerate(chunks, start=1):
            extractions.append((chunk, engine.extract(chunk)))
            _report(progress, "抽取实体与关系", index, len(chunks))

        graph = build_graph(extractions)
        runtime_graph = build_runtime_graph(graph)
        mappings = build_mappings(graph, chunks)
        quality = validate_graph(graph, chunks)
        if not quality["passed"]:
            raise RuntimeError("Graph quality gate failed: " + "; ".join(quality["errors"]))

        build_id = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{uuid.uuid4().hex[:8]}"
        )
        mode_counts: dict[str, int] = {}
        for _, result in extractions:
            mode_counts[result.mode] = mode_counts.get(result.mode, 0) + 1
        manifest: dict[str, object] = {
            "schema_version": "1.0",
            "build_id": build_id,
            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "source_count": len(documents),
            "chunk_count": len(chunks),
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
            "extraction": {
                "configured_mode": engine.configured_mode,
                "effective_mode": engine.effective_mode,
                "mode_counts": mode_counts,
                "fallback_count": engine.fallback_count,
                "warning_count": len(engine.warnings),
            },
            "chunking": {
                "chunk_size": self.settings.chunk_size,
                "chunk_overlap": self.settings.chunk_overlap,
            },
            "files": {
                "graph": "graph.json",
                "runtime_graph": "runtime_graph.json",
                "chunks": "chunks.jsonl",
                "source_inventory": "source_inventory.json",
                "mappings": "mappings.json",
                "quality_report": "quality_report.json",
            },
        }

        target = self.settings.index_dir
        temporary = target.parent / f".{target.name}.build-{uuid.uuid4().hex}"
        backup = target.parent / f".{target.name}.backup"
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir(parents=True)
        try:
            write_json(temporary / "manifest.json", manifest)
            write_json(temporary / "graph.json", graph)
            write_json(temporary / "runtime_graph.json", runtime_graph)
            write_json(temporary / "mappings.json", mappings)
            write_json(temporary / "quality_report.json", quality)
            write_json(
                temporary / "source_inventory.json",
                [document.to_dict(include_text=False) for document in documents],
            )
            write_jsonl(temporary / "chunks.jsonl", [chunk.to_dict() for chunk in chunks])
            if engine.warnings:
                write_json(temporary / "extraction_warnings.json", engine.warnings)

            if backup.exists():
                shutil.rmtree(backup)
            if target.exists():
                target.replace(backup)
            temporary.replace(target)
            if backup.exists():
                shutil.rmtree(backup)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            if not target.exists() and backup.exists():
                backup.replace(target)
            raise
        _report(progress, "质量校验与发布", 1, 1)
        return BuildResult(manifest=manifest, quality=quality, index_dir=target)


def _report(callback: ProgressCallback | None, stage: str, current: int, total: int) -> None:
    if callback:
        callback(stage, current, total)
