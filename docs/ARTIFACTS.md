# Artifact contracts

## `manifest.json`

记录构建版本、时间、来源数、分块数、节点数、边数、抽取模式和产物路径。不会包含 API Key、模型请求或原始环境变量。

## `chunks.jsonl`

每行一个证据块：

```json
{
  "id": "CHK_xxx",
  "evidence_id": "EV_xxx",
  "source_id": "SRC_xxx",
  "source_path": "demo.md",
  "source_title": "demo",
  "section": "升力",
  "ordinal": 0,
  "text": "原文内容",
  "sha256": "..."
}
```

## `graph.json`

节点字段：`id`、`name`、`type`、`description`、`aliases`、`evidence_ids`、`source_ids`。

关系字段：`id`、`source`、`target`、`relation`、`statement`、`confidence`、`evidence_ids`。

`statement` 是原文支持关系的短说明；不能替代 `evidence_ids`。

## `runtime_graph.json`

将正式边转换成双向邻接表。反向项仅用于遍历，`direction` 标识原边方向，不会篡改语义方向。

## `mappings.json`

- `node_to_evidence`
- `evidence_to_nodes`
- `evidence_to_chunk`

这些映射用于审计、检索和未来迁移到 Neo4j、PostgreSQL 或向量数据库。

## `quality_report.json`

`passed=false` 时索引不会发布。当前硬错误包括空图、重复 ID、悬空边、自环、无证据节点和无效证据引用；孤立节点比例作为警告保留。
