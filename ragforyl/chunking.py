from __future__ import annotations

import hashlib
import re

from ragforyl.io import sha256_text
from ragforyl.models import Chunk, SourceDocument

HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+.+|第[一二三四五六七八九十百\d]+[章节篇]\s*.+|[一二三四五六七八九十]+[、.]\s*.+|\d+(?:\.\d+){0,3}\s+\S.+)$"
)
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[。！？；.!?;])\s*")


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _sections(document: SourceDocument) -> list[tuple[str, str]]:
    section = document.title
    blocks: list[tuple[str, str]] = []
    paragraph_lines: list[str] = []

    def flush() -> None:
        if paragraph_lines:
            text = " ".join(paragraph_lines).strip()
            if text:
                blocks.append((section, text))
            paragraph_lines.clear()

    for raw_line in _clean_text(document.text).splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if HEADING_RE.match(line) and len(line) <= 100:
            flush()
            section = re.sub(r"^#{1,6}\s+", "", line).strip()
            continue
        paragraph_lines.append(line)
    flush()
    return blocks or [(document.title, _clean_text(document.text))]


def _split_long_block(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    sentences = [item.strip() for item in SENTENCE_BOUNDARY_RE.split(text) if item.strip()]
    if len(sentences) == 1:
        return [text[index : index + limit] for index in range(0, len(text), limit)]
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > limit:
            pieces.append(current)
            current = ""
        if len(sentence) > limit:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(
                sentence[index : index + limit] for index in range(0, len(sentence), limit)
            )
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_document(document: SourceDocument, chunk_size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    ordinal = 0
    for section, block in _sections(document):
        pieces = _split_long_block(block, chunk_size)
        current = ""
        for piece in pieces:
            candidate = f"{current}\n\n{piece}".strip() if current else piece
            if current and len(candidate) > chunk_size:
                chunks.append(_make_chunk(document, section, ordinal, current))
                ordinal += 1
                prefix = current[-overlap:].lstrip() if overlap else ""
                current = f"{prefix}\n\n{piece}".strip() if prefix else piece
            else:
                current = candidate
        if current:
            chunks.append(_make_chunk(document, section, ordinal, current))
            ordinal += 1
    return chunks


def _make_chunk(document: SourceDocument, section: str, ordinal: int, text: str) -> Chunk:
    digest = sha256_text(text)
    token = hashlib.sha1(f"{document.id}:{section}:{ordinal}:{digest}".encode()).hexdigest()[:14]
    chunk_id = f"CHK_{token}"
    return Chunk(
        id=chunk_id,
        evidence_id=f"EV_{token}",
        source_id=document.id,
        source_path=document.relative_path,
        source_title=document.title,
        section=section,
        ordinal=ordinal,
        text=text,
        sha256=digest,
    )


def chunk_documents(documents: list[SourceDocument], chunk_size: int, overlap: int) -> list[Chunk]:
    chunks = []
    for document in documents:
        chunks.extend(chunk_document(document, chunk_size, overlap))
    return chunks
