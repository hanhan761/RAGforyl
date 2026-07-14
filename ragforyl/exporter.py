from __future__ import annotations

import csv
from pathlib import Path
from xml.sax.saxutils import escape

from ragforyl.io import read_json


def export_graph(index_dir: Path, output_dir: Path, export_format: str) -> list[Path]:
    graph = read_json(index_dir / "graph.json")
    output_dir.mkdir(parents=True, exist_ok=True)
    if export_format == "csv":
        return _export_csv(graph, output_dir)
    if export_format == "graphml":
        target = output_dir / "knowledge_graph.graphml"
        target.write_text(_graphml(graph), encoding="utf-8")
        return [target]
    raise ValueError("format must be csv or graphml")


def _export_csv(graph: dict, output_dir: Path) -> list[Path]:
    nodes_path = output_dir / "nodes.csv"
    edges_path = output_dir / "edges.csv"
    with nodes_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "name", "type", "description", "aliases"])
        writer.writeheader()
        for node in graph["nodes"]:
            writer.writerow(
                {
                    "id": node["id"],
                    "name": node["name"],
                    "type": node["type"],
                    "description": node.get("description", ""),
                    "aliases": "|".join(node.get("aliases") or []),
                }
            )
    with edges_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "source", "target", "relation", "statement", "confidence"],
        )
        writer.writeheader()
        for edge in graph["edges"]:
            writer.writerow({key: edge.get(key, "") for key in writer.fieldnames})
    return [nodes_path, edges_path]


def _graphml(graph: dict) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '  <key id="name" for="node" attr.name="name" attr.type="string"/>',
        '  <key id="type" for="node" attr.name="type" attr.type="string"/>',
        '  <key id="description" for="node" attr.name="description" attr.type="string"/>',
        '  <key id="relation" for="edge" attr.name="relation" attr.type="string"/>',
        '  <key id="statement" for="edge" attr.name="statement" attr.type="string"/>',
        '  <graph id="knowledge-graph" edgedefault="directed">',
    ]
    for node in graph["nodes"]:
        lines.extend(
            [
                f'    <node id="{escape(node["id"])}">',
                f'      <data key="name">{escape(node["name"])}</data>',
                f'      <data key="type">{escape(node["type"])}</data>',
                f'      <data key="description">{escape(node.get("description", ""))}</data>',
                "    </node>",
            ]
        )
    for edge in graph["edges"]:
        edge_open = (
            f'    <edge id="{escape(edge["id"])}" '
            f'source="{escape(edge["source"])}" '
            f'target="{escape(edge["target"])}">'
        )
        lines.extend(
            [
                edge_open,
                f'      <data key="relation">{escape(edge["relation"])}</data>',
                f'      <data key="statement">{escape(edge.get("statement", ""))}</data>',
                "    </edge>",
            ]
        )
    lines.extend(["  </graph>", "</graphml>", ""])
    return "\n".join(lines)
