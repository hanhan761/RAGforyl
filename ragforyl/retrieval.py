from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from ragforyl.io import read_json, read_jsonl


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def _terms(text: str) -> set[str]:
    lowered = text.lower()
    terms = set(re.findall(r"[a-z0-9_\-]{2,}", lowered))
    for run in re.findall(r"[\u4e00-\u9fff]+", lowered):
        if len(run) <= 4:
            terms.add(run)
        for size in (2, 3, 4):
            terms.update(run[index : index + size] for index in range(max(0, len(run) - size + 1)))
    return terms


def lexical_score(query: str, text: str) -> float:
    query_terms = _terms(query)
    if not query_terms or not text:
        return 0.0
    text_terms = _terms(text)
    coverage = len(query_terms & text_terms) / len(query_terms)
    exact = 1.0 if _normalize(query) and _normalize(query) in _normalize(text) else 0.0
    return min(1.0, coverage * 0.78 + exact * 0.35)


class KnowledgeBase:
    def __init__(self, index_dir: Path) -> None:
        manifest_path = index_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Knowledge graph index not found: {manifest_path}")
        self.index_dir = index_dir
        self.manifest = read_json(manifest_path)
        self.graph = read_json(index_dir / "graph.json")
        self.runtime_graph = read_json(index_dir / "runtime_graph.json")
        self.chunks = read_jsonl(index_dir / "chunks.jsonl")
        self.node_lookup = {node["id"]: node for node in self.graph["nodes"]}
        self.evidence_lookup = {chunk["evidence_id"]: chunk for chunk in self.chunks}

    def search(self, question: str, *, top_k: int = 6) -> dict[str, Any]:
        question = question.strip()
        if not question:
            raise ValueError("question cannot be empty")
        top_k = max(1, min(int(top_k), 20))
        direct_scores: dict[str, float] = {}
        for node in self.graph["nodes"]:
            aliases = " ".join(node.get("aliases") or [])
            name_score = lexical_score(question, f"{node['name']} {aliases}")
            body_score = lexical_score(
                question, f"{node.get('description', '')} {node.get('type', '')}"
            )
            score = min(1.0, name_score * 0.78 + body_score * 0.32)
            if _normalize(node["name"]) in _normalize(question):
                score = max(score, 0.92)
            if score > 0:
                direct_scores[node["id"]] = score

        seeds = sorted(direct_scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]
        expanded_scores = dict(seeds)
        for seed_id, seed_score in seeds:
            for neighbor in self.runtime_graph.get("adjacency", {}).get(seed_id, [])[:24]:
                target_id = neighbor["target"]
                relation_score = float(neighbor.get("confidence", 0.7))
                target_direct = direct_scores.get(target_id, 0.0)
                candidate = seed_score * 0.55 + relation_score * 0.25 + target_direct * 0.2
                expanded_scores[target_id] = max(expanded_scores.get(target_id, 0.0), candidate)

        ranked_ids = [
            node_id
            for node_id, _ in sorted(expanded_scores.items(), key=lambda item: (-item[1], item[0]))[
                :top_k
            ]
        ]
        selected = set(ranked_ids)
        nodes = [
            {
                **self.node_lookup[node_id],
                "score": round(expanded_scores[node_id], 4),
            }
            for node_id in ranked_ids
        ]
        edges = [
            edge
            for edge in self.graph["edges"]
            if edge["source"] in selected and edge["target"] in selected
        ][: max(8, top_k * 3)]

        supporting_evidence: dict[str, float] = defaultdict(float)
        for node in nodes:
            for evidence_id in node.get("evidence_ids") or []:
                supporting_evidence[evidence_id] = max(
                    supporting_evidence[evidence_id], node["score"]
                )
        chunk_scores = []
        for chunk in self.chunks:
            lexical = lexical_score(question, chunk["text"])
            graph_support = supporting_evidence.get(chunk["evidence_id"], 0.0)
            score = min(1.0, lexical * 0.62 + graph_support * 0.48)
            if score > 0.02:
                chunk_scores.append((score, chunk))
        chunk_scores.sort(key=lambda item: (-item[0], item[1]["id"]))

        sources = []
        context_parts = []
        for index, (score, chunk) in enumerate(chunk_scores[: max(4, top_k)], start=1):
            reference = f"S{index}"
            sources.append(
                {
                    "reference": reference,
                    "evidence_id": chunk["evidence_id"],
                    "source_path": chunk["source_path"],
                    "source_title": chunk["source_title"],
                    "section": chunk["section"],
                    "text": chunk["text"],
                    "score": round(score, 4),
                }
            )
            context_parts.append(
                f"[{reference}] {chunk['source_title']} / {chunk['section']}\n{chunk['text']}"
            )
        confidence = nodes[0]["score"] if nodes else (sources[0]["score"] if sources else 0.0)
        return {
            "question": question,
            "confidence": round(float(confidence), 4),
            "nodes": nodes,
            "edges": edges,
            "sources": sources,
            "context": "\n\n".join(context_parts),
            "build_id": self.manifest["build_id"],
        }
