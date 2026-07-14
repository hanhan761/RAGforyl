from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from ragforyl.config import Settings
from ragforyl.llm import ModelError, OpenAICompatibleClient, parse_json_object
from ragforyl.models import Chunk, EntityCandidate, ExtractionResult, RelationCandidate

SENTENCE_RE = re.compile(r"[^。！？!?\n]+[。！？!?]?")
NAME_CHARS = r"A-Za-z0-9_\-·\u4e00-\u9fff"
DEFINITION_RE = re.compile(
    rf"^\s*(?P<name>[{NAME_CHARS}]{{2,32}}?)\s*(?:是指|指的是|定义为|可定义为|是)\s*(?P<description>.{{4,160}})$"
)
ENUMERATION_RE = re.compile(
    rf"(?P<source>[{NAME_CHARS}]{{2,28}}?)\s*(?:主要)?(?:包括|包含|由)\s*(?P<targets>[^。！？!?]{{2,120}}?)(?:组成)?(?:[。！？!?]|$)"
)
RELATION_PATTERNS = (
    (
        "used_for",
        re.compile(
            rf"(?P<source>[{NAME_CHARS}]{{2,28}}?)\s*(?:可)?用于\s*(?P<target>[{NAME_CHARS}]{{2,32}})"
        ),
    ),
    (
        "causes",
        re.compile(
            rf"(?P<source>[{NAME_CHARS}]{{2,28}}?)\s*(?:会)?导致\s*(?P<target>[{NAME_CHARS}]{{2,32}})"
        ),
    ),
    (
        "affects",
        re.compile(
            rf"(?P<source>[{NAME_CHARS}]{{2,28}}?)\s*(?:会)?影响\s*(?P<target>[{NAME_CHARS}]{{2,32}})"
        ),
    ),
    (
        "depends_on",
        re.compile(
            rf"(?P<source>[{NAME_CHARS}]{{2,28}}?)\s*(?:依赖于|依赖)\s*(?P<target>[{NAME_CHARS}]{{2,32}})"
        ),
    ),
    (
        "part_of",
        re.compile(
            rf"(?P<source>[{NAME_CHARS}]{{2,28}}?)\s*属于\s*(?P<target>[{NAME_CHARS}]{{2,32}})"
        ),
    ),
)
TERM_SUFFIX_RE = re.compile(
    r"[\u4e00-\u9fff]{2,12}(?:理论|方法|模型|算法|系统|结构|概念|技术|流程|指标|节点|关系|方程|定律)"
)


def normalize_entity_key(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())


def clean_name(value: Any) -> str:
    text = re.sub(r"[*#`_]+", "", str(value or "")).strip(" \t\r\n，,。；;：:（）()[]【】\"'")
    text = re.sub(r"\s+", " ", text)
    if len(text) < 2 or len(text) > 80:
        return ""
    if len(re.findall(r"[，。！？!?；;]", text)) > 0:
        return ""
    return text


def clean_relation_type(value: Any) -> str:
    text = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "related_to").strip().lower())
    return text.strip("_")[:40] or "related_to"


class HeuristicExtractor:
    def extract(self, chunk: Chunk) -> ExtractionResult:
        entities: OrderedDict[str, EntityCandidate] = OrderedDict()
        relations: list[RelationCandidate] = []

        def add_entity(name: Any, entity_type: str = "concept", description: str = "") -> str:
            cleaned = clean_name(name)
            key = normalize_entity_key(cleaned)
            if not cleaned or not key:
                return ""
            if key not in entities:
                entities[key] = EntityCandidate(
                    name=cleaned,
                    type=clean_relation_type(entity_type) or "concept",
                    description=description.strip()[:420],
                )
            elif description and len(description) > len(entities[key].description):
                entities[key].description = description.strip()[:420]
            return cleaned

        anchor = add_entity(chunk.section or chunk.source_title, "topic", chunk.text[:240])
        sentences = [match.group(0).strip() for match in SENTENCE_RE.finditer(chunk.text)]
        for sentence in sentences:
            body = sentence.rstrip("。！？!?").strip()
            definition = DEFINITION_RE.match(body)
            if definition:
                add_entity(definition.group("name"), "concept", definition.group("description"))

            for match in ENUMERATION_RE.finditer(sentence):
                source = add_entity(match.group("source"), "concept", sentence)
                target_text = re.sub(r"(?:等|组成)$", "", match.group("targets")).strip()
                targets = re.split(r"[、,，/]|以及|和|与", target_text)
                for target_value in targets[:8]:
                    target = add_entity(target_value, "concept", sentence)
                    if source and target and source != target:
                        relations.append(
                            RelationCandidate(source, target, "includes", sentence, confidence=0.82)
                        )

            for relation_type, pattern in RELATION_PATTERNS:
                for match in pattern.finditer(sentence):
                    source = add_entity(match.group("source"), "concept", sentence)
                    target = add_entity(match.group("target"), "concept", sentence)
                    if source and target and source != target:
                        relations.append(
                            RelationCandidate(
                                source, target, relation_type, sentence, confidence=0.8
                            )
                        )

        for value in re.findall(r"\*\*([^*\n]{2,60})\*\*", chunk.text):
            add_entity(value, "concept")
        for value in TERM_SUFFIX_RE.findall(chunk.text):
            add_entity(value, "concept")
        for value in re.findall(r"\b[A-Z][A-Za-z0-9_-]{1,24}\b", chunk.text):
            if value.lower() not in {"page", "http", "https"}:
                add_entity(value, "term")

        entity_list = list(entities.values())[:18]
        allowed = {normalize_entity_key(item.name) for item in entity_list}
        relations = [
            item
            for item in relations
            if normalize_entity_key(item.source) in allowed
            and normalize_entity_key(item.target) in allowed
        ]
        if anchor and len(entity_list) > 1:
            linked = {
                normalize_entity_key(item.target)
                for item in relations
                if normalize_entity_key(item.source) == normalize_entity_key(anchor)
            }
            for entity in entity_list[1:8]:
                key = normalize_entity_key(entity.name)
                if key not in linked and key != normalize_entity_key(anchor):
                    relations.append(
                        RelationCandidate(
                            anchor, entity.name, "contains", "同一章节中的知识点", confidence=0.55
                        )
                    )
        return ExtractionResult(entity_list, _deduplicate_relations(relations), mode="heuristic")


class LLMExtractor:
    def __init__(self, settings: Settings) -> None:
        self.client = OpenAICompatibleClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    def extract(self, chunk: Chunk) -> ExtractionResult:
        payload = self.client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是知识图谱工程师。只输出合法 JSON，不要 Markdown。"
                        "实体必须是文本中明确出现或明确定义的概念；"
                        "关系必须能由文本直接支持，不得补充常识。使用简短 snake_case 关系类型。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "从下面文本抽取实体和有方向的关系。输出格式："
                        '{"entities":[{"name":"","type":"concept","description":"","aliases":[]}],'
                        '"relations":[{"source":"","target":"","type":"related_to","statement":""}]}。'
                        f"\n章节：{chunk.section}\n文本：\n{chunk.text}"
                    ),
                },
            ],
            temperature=0.0,
            max_tokens=2400,
        )
        return _result_from_payload(parse_json_object(payload))


class ExtractionEngine:
    def __init__(self, settings: Settings) -> None:
        self.configured_mode = settings.extraction_mode
        self.effective_mode = settings.effective_extraction_mode
        self.heuristic = HeuristicExtractor()
        self.llm = LLMExtractor(settings) if self.effective_mode == "llm" else None
        self.fallback_count = 0
        self.warnings: list[str] = []

    def extract(self, chunk: Chunk) -> ExtractionResult:
        if self.llm is None:
            return self.heuristic.extract(chunk)
        try:
            return self.llm.extract(chunk)
        except ModelError as exc:
            if self.configured_mode == "llm":
                raise
            self.fallback_count += 1
            warning = f"{chunk.id}: {exc}"
            self.warnings.append(warning)
            fallback = self.heuristic.extract(chunk)
            fallback.warning = warning
            return fallback


def _result_from_payload(payload: dict[str, Any]) -> ExtractionResult:
    entities: list[EntityCandidate] = []
    for raw in payload.get("entities") or []:
        if not isinstance(raw, dict):
            continue
        name = clean_name(raw.get("name"))
        if not name:
            continue
        aliases = [clean_name(item) for item in raw.get("aliases") or []]
        entities.append(
            EntityCandidate(
                name=name,
                type=clean_relation_type(raw.get("type") or "concept"),
                description=str(raw.get("description") or "").strip()[:420],
                aliases=[item for item in aliases if item and item != name][:8],
            )
        )
    relations = []
    for raw in payload.get("relations") or []:
        if not isinstance(raw, dict):
            continue
        source = clean_name(raw.get("source"))
        target = clean_name(raw.get("target"))
        if source and target and source != target:
            relations.append(
                RelationCandidate(
                    source=source,
                    target=target,
                    type=clean_relation_type(raw.get("type")),
                    statement=str(raw.get("statement") or "").strip()[:420],
                    confidence=0.85,
                )
            )
    if not entities:
        raise ModelError("Model JSON did not contain valid entities")
    return ExtractionResult(entities[:24], _deduplicate_relations(relations[:40]), mode="llm")


def _deduplicate_relations(items: list[RelationCandidate]) -> list[RelationCandidate]:
    unique: OrderedDict[tuple[str, str, str], RelationCandidate] = OrderedDict()
    for item in items:
        key = (
            normalize_entity_key(item.source),
            normalize_entity_key(item.target),
            clean_relation_type(item.type),
        )
        if key[0] and key[1] and key[0] != key[1]:
            unique.setdefault(key, item)
    return list(unique.values())
