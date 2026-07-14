from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from ragforyl.answering import AnswerService
from ragforyl.config import Settings
from ragforyl.pipeline import BuildPipeline
from ragforyl.retrieval import KnowledgeBase


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="ragforyl-smoke-") as temporary:
        data_dir = Path(temporary) / "data"
        source_dir = data_dir / "source"
        source_dir.mkdir(parents=True)
        shutil.copy2(project_root / "examples" / "sources" / "flight_basics.md", source_dir)
        settings = Settings(
            data_dir=data_dir,
            source_dir=source_dir,
            index_dir=data_dir / "index",
            extraction_mode="heuristic",
            chunk_size=700,
            chunk_overlap=70,
            max_upload_mb=30,
            llm_api_key="",
            llm_base_url="https://example.invalid/v1",
            llm_model="",
            llm_timeout_seconds=10,
        )
        result = BuildPipeline(settings).build()
        answer = AnswerService(settings, KnowledgeBase(settings.index_dir)).answer(
            "攻角为什么会导致失速？"
        )
        assert result.quality["passed"] is True
        assert answer["retrieval"]["nodes"]
        assert answer["retrieval"]["sources"]
        print(
            "SMOKE PASS | "
            f"nodes={result.manifest['node_count']} "
            f"edges={result.manifest['edge_count']} "
            f"sources={len(answer['retrieval']['sources'])}"
        )


if __name__ == "__main__":
    main()
