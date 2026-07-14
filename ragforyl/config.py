from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

SUPPORTED_EXTENSIONS = (".txt", ".md", ".markdown", ".pdf", ".docx")


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    source_dir: Path
    index_dir: Path
    extraction_mode: str
    chunk_size: int
    chunk_overlap: int
    max_upload_mb: int
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    llm_timeout_seconds: int

    @classmethod
    def from_env(
        cls,
        *,
        data_dir: str | Path | None = None,
        source_dir: str | Path | None = None,
        index_dir: str | Path | None = None,
    ) -> Settings:
        load_dotenv(Path.cwd() / ".env", override=False)
        resolved_data = Path(data_dir or os.getenv("RAGFORYL_DATA_DIR", "./data")).resolve()
        mode = os.getenv("RAGFORYL_EXTRACTION_MODE", "auto").strip().lower()
        if mode not in {"auto", "llm", "heuristic"}:
            raise ValueError("RAGFORYL_EXTRACTION_MODE must be auto, llm, or heuristic")
        chunk_size = _bounded_int("RAGFORYL_CHUNK_SIZE", 1200, 300, 8000)
        chunk_overlap = _bounded_int("RAGFORYL_CHUNK_OVERLAP", 120, 0, 1000)
        if chunk_overlap >= chunk_size:
            raise ValueError("RAGFORYL_CHUNK_OVERLAP must be smaller than chunk size")
        return cls(
            data_dir=resolved_data,
            source_dir=Path(source_dir or resolved_data / "source").resolve(),
            index_dir=Path(index_dir or resolved_data / "index").resolve(),
            extraction_mode=mode,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            max_upload_mb=_bounded_int("RAGFORYL_MAX_UPLOAD_MB", 30, 1, 500),
            llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
            llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/"),
            llm_model=os.getenv("LLM_MODEL", "").strip(),
            llm_timeout_seconds=_bounded_int("LLM_TIMEOUT_SECONDS", 90, 5, 600),
        )

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key and self.llm_model)

    @property
    def effective_extraction_mode(self) -> str:
        if self.extraction_mode == "heuristic":
            return "heuristic"
        if self.llm_enabled:
            return "llm"
        if self.extraction_mode == "llm":
            raise ValueError("LLM extraction requires both LLM_API_KEY and LLM_MODEL")
        return "heuristic"

    def ensure_directories(self) -> None:
        self.source_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.parent.mkdir(parents=True, exist_ok=True)

    def public_summary(self) -> dict[str, object]:
        return {
            "data_dir": str(self.data_dir),
            "source_dir": str(self.source_dir),
            "index_dir": str(self.index_dir),
            "configured_extraction_mode": self.extraction_mode,
            "effective_extraction_mode": self.effective_extraction_mode,
            "llm_configured": self.llm_enabled,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "max_upload_mb": self.max_upload_mb,
        }
