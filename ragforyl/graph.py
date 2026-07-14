from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from ragforyl.extraction import clean_relation_type, normalize_entity_key
from ragforyl.models import Chunk, ExtractionResult


def _node_id(key: str) -> str:
    return f"N_{hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]}"


def _edge_id(source: str, target: str, relation: str) -> str:
    token = hashlib.sha1(f"{source}:{target}:{relation}".encode()).hexdigest()[:12]
    return f"E_{token}"


def build_graph(extractions: list[tuple[Chunk, ExtractionResult]]) -> dict[str, Any]:
    node_records: dict[str, dict[str, Any]] = {}
    edge_records: dict[tuple[str, str, str], dict[str, Any]] = {}

    def ensure_node(
        name: str, chunk: Chunk, entity_type: str = "concept", description: str = ""
    ) -> str:
        key = normalize_entity_key(name)
        if not key:
            return ""
        node_id = _node_id(key)
        record = node_records.get(key)
        if record is None:
            record = {
                "id": node_id,
                "name": name.strip(),
                "type": clean_relation_type(entity_type) or "concept",
                "description": description.strip(),
                "aliases": set(),
                "evidence_ids": set(),
                "source_ids": set(),
            }
            node_records[key] = record
        else:
            if name.strip() != record["name"]:
                record["aliases"].add(name.strip())
            if description and len(description) > len(record["description"]):
                record["description"] = description.strip()
            if record["type"] in {"concept", "term"} and entity_type not in {"concept", "term"}:
                record["type"] = clean_relation_type(entity_type)
        record["evidence_ids"].add(chunk.evidence_id)
        record["source_ids"].add(chunk.source_id)
        return node_id

    for chunk, result in extractions:
        local_nodes: dict[str, str] = {}
        for entity in result.entities:
            node_id = ensure_node(entity.name, chunk, entity.type, entity.description)
            if not node_id:
                continue
            record = node_records[normalize_entity_key(entity.name)]
            record["aliases"].update(
                alias for alias in entity.aliases if alias and alias != record["name"]
            )
            local_nodes[normalize_entity_key(entity.name)] = node_id
            for alias in entity.aliases:
                alias_key = normalize_entity_key(alias)
                if alias_key:
                    local_nodes[alias_key] = node_id

        for relation in result.relations:
            source_key = normalize_entity_key(relation.source)
            target_key = normalize_entity_key(relation.target)
            source_id = local_nodes.get(source_key) or ensure_node(relation.source, chunk)
            target_id = local_nodes.get(target_key) or ensure_node(relation.target, chunk)
            relation_type = clean_relation_type(relation.type)
            if not source_id or not target_id or source_id == target_id:
                continue
            key = (source_id, target_id, relation_type)
            record = edge_records.get(key)
            if record is None:
                record = {
                    "id": _edge_id(*key),
                    "source": source_id,
                    "target": target_id,
                    "relation": relation_type,
                    "statement": relation.statement.strip(),
                    "confidence": max(0.0, min(float(relation.confidence), 1.0)),
                    "evidence_ids": set(),
                }
                edge_records[key] = record
            elif relation.statement and len(relation.statement) > len(record["statement"]):
                record["statement"] = relation.statement.strip()
            record["confidence"] = max(record["confidence"], relation.confidence)
            record["evidence_ids"].add(chunk.evidence_id)

    nodes = []
    for record in node_records.values():
        nodes.append(
            {
                **{
                    key: value
                    for key, value in record.items()
                    if key not in {"aliases", "evidence_ids", "source_ids"}
                },
                "aliases": sorted(record["aliases"]),
                "evidence_ids": sorted(record["evidence_ids"]),
                "source_ids": sorted(record["source_ids"]),
            }
        )
    edges = []
    for record in edge_records.values():
        edges.append(
            {
                **{key: value for key, value in record.items() if key != "evidence_ids"},
                "confidence": round(float(record["confidence"]), 4),
                "evidence_ids": sorted(record["evidence_ids"]),
            }
        )
    nodes.sort(key=lambda item: (item["type"], item["name"], item["id"]))
    edges.sort(key=lambda item: (item["relation"], item["source"], item["target"]))
    return {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "nodes": nodes,
        "edges": edges,
    }


def build_runtime_graph(graph: dict[str, Any]) -> dict[str, Any]:
    adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in graph["edges"]:
        common = {
            "edge_id": edge["id"],
            "relation": edge["relation"],
            "statement": edge.get("statement", ""),
            "confidence": edge.get("confidence", 0.75),
            "evidence_ids": edge.get("evidence_ids", []),
        }
        adjacency[edge["source"]].append({**common, "target": edge["target"], "direction": "out"})
        adjacency[edge["target"]].append({**common, "target": edge["source"], "direction": "in"})
    return {
        "schema_version": graph["schema_version"],
        "created_at": graph["created_at"],
        "adjacency": {key: value for key, value in sorted(adjacency.items())},
    }


def build_mappings(graph: dict[str, Any], chunks: list[Chunk]) -> dict[str, Any]:
    node_to_evidence = {node["id"]: node["evidence_ids"] for node in graph["nodes"]}
    evidence_to_nodes: dict[str, list[str]] = defaultdict(list)
    for node in graph["nodes"]:
        for evidence_id in node["evidence_ids"]:
            evidence_to_nodes[evidence_id].append(node["id"])
    evidence_to_chunk = {chunk.evidence_id: chunk.id for chunk in chunks}
    return {
        "node_to_evidence": node_to_evidence,
        "evidence_to_nodes": {
            key: sorted(value) for key, value in sorted(evidence_to_nodes.items())
        },
        "evidence_to_chunk": evidence_to_chunk,
    }


def validate_graph(graph: dict[str, Any], chunks: list[Chunk]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    node_ids = [node["id"] for node in graph["nodes"]]
    edge_ids = [edge["id"] for edge in graph["edges"]]
    node_id_set = set(node_ids)
    evidence_ids = {chunk.evidence_id for chunk in chunks}

    if not graph["nodes"]:
        errors.append("graph has no nodes")
    if len(node_ids) != len(node_id_set):
        errors.append("duplicate node ids")
    if len(edge_ids) != len(set(edge_ids)):
        errors.append("duplicate edge ids")

    degree = defaultdict(int)
    for node in graph["nodes"]:
        unknown = set(node.get("evidence_ids") or []) - evidence_ids
        if unknown:
            errors.append(f"node {node['id']} references unknown evidence")
        if not node.get("evidence_ids"):
            errors.append(f"node {node['id']} has no evidence")
    for edge in graph["edges"]:
        if edge["source"] not in node_id_set or edge["target"] not in node_id_set:
            errors.append(f"edge {edge['id']} has a dangling endpoint")
        if edge["source"] == edge["target"]:
            errors.append(f"edge {edge['id']} is a self-loop")
        unknown = set(edge.get("evidence_ids") or []) - evidence_ids
        if unknown or not edge.get("evidence_ids"):
            errors.append(f"edge {edge['id']} has invalid evidence")
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1

    orphan_count = sum(1 for node_id in node_id_set if degree[node_id] == 0)
    orphan_ratio = orphan_count / max(1, len(node_id_set))
    if orphan_ratio > 0.35:
        warnings.append(f"orphan node ratio is high: {orphan_ratio:.1%}")
    return {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
            "chunk_count": len(chunks),
            "orphan_node_count": orphan_count,
            "orphan_ratio": round(orphan_ratio, 4),
            "evidence_coverage": 1.0 if graph["nodes"] else 0.0,
        },
    }
