from __future__ import annotations

from pathlib import Path

import pytest

from ragforyl.config import Settings


@pytest.fixture
def settings_factory(tmp_path: Path):
    def factory(*, mode: str = "heuristic") -> Settings:
        data_dir = tmp_path / "data"
        return Settings(
            data_dir=data_dir,
            source_dir=data_dir / "source",
            index_dir=data_dir / "index",
            extraction_mode=mode,
            chunk_size=500,
            chunk_overlap=50,
            max_upload_mb=2,
            llm_api_key="",
            llm_base_url="https://example.invalid/v1",
            llm_model="",
            llm_timeout_seconds=10,
        )

    return factory
