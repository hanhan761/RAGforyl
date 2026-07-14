# Pipeline

## 目标

RAGforyl 将原教学平台中课程专用的多阶段知识图谱流程，收敛成普通用户可以执行的三个动作：上传资料、构建图谱、开始提问。

## 端到端链路

```text
PDF / DOCX / Markdown / TXT
          │
          ▼
来源清单与 SHA-256 去重
          │
          ▼
正文解析（扫描页可选 OCR）
          │
          ▼
标题识别与章节感知分块
          │
          ▼
LLM 抽取 ──失败回退──► 离线规则抽取
          │
          ▼
实体归一、关系合并、证据回链
          │
          ▼
运行时邻接表与映射
          │
          ▼
完整性质量门禁
          │
          ▼
原子发布 data/index
          │
          ▼
词法召回种子 ─► 一跳图扩展 ─► 证据分块重排
          │
          ▼
检索摘要 / 带 [S1] 引用的模型回答
```

## 与航院智课原链路的对应关系

| 原阶段 | RAGforyl | 变化 |
|---|---|---|
| source inventory | `io.load_source_documents` | 改为任意目录与通用格式 |
| extraction and normalization | `io.extract_text` | 去除课程固定路径，保留编码和空文档失败 |
| reconstruct structure | `chunking._sections` | 用标题规则恢复章节 |
| semantic units / parent chunks | `chunking.chunk_documents` | 合并成章节感知证据块 |
| candidate graph | `extraction` + `graph.build_graph` | 增加 OpenAI-compatible 与离线双通道 |
| mappings | `graph.build_mappings` | 保留节点、证据、分块双向映射 |
| runtime graph | `graph.build_runtime_graph` | 输出双向邻接表 |
| release validation | `graph.validate_graph` | 自动门禁后原子发布 |
| runtime retrieval | `retrieval.KnowledgeBase` | 保留词法种子与有界扩图思想 |

## 证据不变量

1. 每个节点至少关联一个 `evidence_id`。
2. 每条边至少关联一个 `evidence_id`。
3. 所有 `evidence_id` 必须存在于 `chunks.jsonl`。
4. LLM 输出不能直接成为正式图；必须经过规范化、去重和质量门禁。
5. 回答中的来源编号来自本次检索的证据块，而不是模型自行生成。

## 构建模式

### heuristic

完全离线。识别定义句、包含关系、用途、影响、因果、依赖、归属以及章节共现关系。适合作为快速试跑和模型不可用时的兜底。

### llm

每个证据块调用一次 OpenAI-compatible Chat Completions。模型只返回 JSON 候选，候选仍需通过本地清洗和门禁。任何模型错误都会中止正式构建。

### auto

配置模型时优先 LLM；单个分块调用失败时回退 heuristic，并在 `extraction_warnings.json` 中记录，不记录密钥和完整请求头。

## 检索

1. 对问题与节点名称、别名、说明计算中文字符 n-gram 覆盖分数。
2. 选择高分节点作为种子。
3. 按关系置信度做一跳有界扩展，避免无控制扩图。
4. 汇总节点证据，结合问题与原文分块的词法分数重排。
5. 返回节点、关系、证据和可直接供模型使用的上下文。
