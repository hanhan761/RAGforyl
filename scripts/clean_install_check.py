from __future__ import annotations

import argparse
from importlib.resources import files
from pathlib import Path

from fastapi.testclient import TestClient

from ragforyl.config import Settings
from ragforyl.retrieval import KnowledgeBase
from ragforyl.server import create_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()

    web_root = files("ragforyl").joinpath("web")
    assert web_root.joinpath("index.html").is_file()
    assert web_root.joinpath("styles.css").is_file()
    assert web_root.joinpath("app.js").is_file()

    knowledge_base = KnowledgeBase(args.index.resolve())
    result = knowledge_base.search("攻角为什么会导致失速？")
    assert result["nodes"]
    assert result["sources"]

    settings = Settings(
        data_dir=args.index.resolve().parent,
        source_dir=args.source.resolve(),
        index_dir=args.index.resolve(),
        extraction_mode="heuristic",
        chunk_size=700,
        chunk_overlap=70,
        max_upload_mb=30,
        llm_api_key="",
        llm_base_url="https://example.invalid/v1",
        llm_model="",
        llm_timeout_seconds=10,
    )
    client = TestClient(create_app(settings))
    assert client.get("/").status_code == 200
    assert client.get("/assets/styles.css").status_code == 200
    assert client.get("/api/status").json()["index_ready"] is True
    assert client.get("/api/graph").json()["total_nodes"] > 0
    print(
        "CLEAN INSTALL PASS | "
        f"nodes={len(knowledge_base.graph['nodes'])} "
        f"edges={len(knowledge_base.graph['edges'])} "
        f"evidence={len(result['sources'])}"
    )


if __name__ == "__main__":
    main()
