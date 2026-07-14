from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class SourceDocument:
    id: str
    title: str
    relative_path: str
    sha256: str
    text: str
    size_bytes: int

    def to_dict(self, *, include_text: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        if not include_text:
            payload.pop("text", None)
        return payload


@dataclass(slots=True)
class Chunk:
    id: str
    evidence_id: str
    source_id: str
    source_path: str
    source_title: str
    section: str
    ordinal: int
    text: str
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EntityCandidate:
    name: str
    type: str = "concept"
    description: str = ""
    aliases: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RelationCandidate:
    source: str
    target: str
    type: str = "related_to"
    statement: str = ""
    confidence: float = 0.75


@dataclass(slots=True)
class ExtractionResult:
    entities: list[EntityCandidate]
    relations: list[RelationCandidate]
    mode: str
    warning: str = ""
