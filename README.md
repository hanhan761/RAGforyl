# RAGforyl

<p align="center">
  <img src="docs/assets/ragforyl-hero.png" alt="RAGforyl 从中文文档到可追溯知识图谱问答的端到端流程" width="100%" />
</p>

RAGforyl 是一个面向中文资料的端到端知识图谱 RAG 工具。把 PDF、Word、Markdown 或文本文件放入系统，即可完成：

1. 文档解析与来源清单
2. 章节感知分块
3. 实体与关系抽取
4. 节点去重和证据回链
5. 图谱质量门禁
6. 图扩展检索
7. 带原文引用的问答
8. 网页预览及 GraphML / CSV 导出

> 这里的“训练”是知识图谱构建、索引和质量校验，不会修改大模型参数。

## 特点

- **拿来即用**：不配置模型也能用离线规则完成 Demo 构建与检索。
- **模型可选**：支持任意 OpenAI-compatible Chat Completions 接口增强实体关系抽取与回答。
- **证据优先**：每个节点和关系都必须关联原始文档分块 `evidence_id`。
- **安全发布**：新索引通过完整性检查后才替换旧索引，构建失败不会破坏可用版本。
- **无需数据库**：默认使用可审计的 JSON / JSONL 文件，适合个人、课程和小团队。
- **中文工作台**：上传、构建、提问、证据核验和图谱预览都在一个页面完成。

## 30 秒启动

### Windows

需要 Python 3.10 或更高版本。双击：

```text
start.bat
```

脚本会自动创建虚拟环境、安装依赖、载入示例资料、构建索引并打开 `http://127.0.0.1:8000`。

### macOS / Linux

```bash
chmod +x start.sh
./start.sh
```

## 手动运行

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

python -m pip install -e .
python -m ragforyl doctor
python -m ragforyl build --source examples/sources --index data/index
python -m ragforyl ask "攻角为什么会影响升力？" --index data/index
python -m ragforyl serve --open-browser
```

将自己的文件放进 `data/source/`，然后重新执行：

```bash
python -m ragforyl build
```

## 启用大模型增强

复制配置模板：

```powershell
Copy-Item .env.example .env
```

或：

```bash
cp .env.example .env
```

编辑 `.env`：

```dotenv
RAGFORYL_EXTRACTION_MODE=auto
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://your-provider.example/v1
LLM_MODEL=your-model-name
```

- `auto`：模型可用时使用模型；请求失败时回退离线抽取并记录警告。
- `llm`：强制使用模型；模型失败则中止构建，适合正式数据生产。
- `heuristic`：始终离线运行，不发起网络请求。

`.env` 已被 Git 忽略。不要把 API Key 写进代码、文档或提交记录。

## 扫描版 PDF

普通文本型 PDF 默认可解析。扫描版 PDF 需要可选 OCR 依赖：

```bash
python -m pip install -e ".[ocr]"
```

安装后，无法提取文本的页面会自动进入 RapidOCR。OCR 结果仍会按页保留来源标记。

## 命令行

```bash
# 环境检查
ragforyl doctor

# 构建
ragforyl build --source data/source --index data/index

# 只检索，不调用生成模型
ragforyl query "问题" --top-k 6

# 检索 + 回答；未配置模型时返回可核验的检索摘要
ragforyl ask "问题" --top-k 6

# 启动网页
ragforyl serve --host 127.0.0.1 --port 8000 --open-browser

# 导出给 Gephi / Cytoscape
ragforyl export --format graphml --output exports

# 导出节点和边表格
ragforyl export --format csv --output exports
```

## Docker

```bash
docker compose up --build
```

访问 `http://127.0.0.1:8000`。资料和索引保存在宿主机 `data/`，删除容器不会丢失。

## 构建产物

```text
data/index/
├── manifest.json           构建版本、模式和数量统计
├── source_inventory.json   来源文件及 SHA-256
├── chunks.jsonl            可检索证据块
├── graph.json              节点、关系和证据 ID
├── runtime_graph.json      双向邻接表
├── mappings.json           节点、证据、分块映射
├── quality_report.json     质量门禁结果
└── extraction_warnings.json  自动回退记录（如有）
```

详细格式见 [docs/ARTIFACTS.md](docs/ARTIFACTS.md)。

## API

启动网页后可访问 `http://127.0.0.1:8000/docs` 查看 OpenAPI 文档。主要接口：

- `GET /api/status`：环境、资料和索引状态
- `POST /api/sources`：上传资料
- `DELETE /api/sources/{filename}`：删除资料
- `POST /api/build`：构建并发布图谱
- `POST /api/query`：检索或生成回答
- `GET /api/graph`：读取图谱预览
- `GET /api/health`：健康检查

## 质量原则

- 节点和关系不能引用不存在的证据。
- 关系两端必须存在，禁止自环和重复 ID。
- 解析不到正文时明确失败，不能生成“看起来成功”的空图谱。
- LLM 只能抽取原文支持的事实；系统提示明确禁止补充常识。
- 构建在临时目录完成；质量门禁通过后原子替换正式索引。
- 回答模型只看到召回的证据，并被要求使用 `[S1]` 格式引用。

## 项目结构

```text
ragforyl/
├── io.py           文档解析与安全文件名
├── chunking.py     章节感知分块
├── extraction.py   LLM / 离线实体关系抽取
├── graph.py        图构建、映射与质量门禁
├── pipeline.py     端到端构建和原子发布
├── retrieval.py    词法种子 + 有界图扩展
├── answering.py    带来源回答
├── server.py       FastAPI
└── web/            零构建中文前端
```

流水线设计与原项目映射见 [docs/PIPELINE.md](docs/PIPELINE.md)。

## 已知边界

- 离线抽取适合结构清晰、定义和关系表达明确的资料；复杂语义建议配置模型。
- 当前检索使用轻量中文字符 n-gram 与图扩展，不依赖向量数据库；百万级语料应迁移到专用搜索或向量引擎。
- 网页默认面向本机可信环境，没有用户认证。公开部署前必须增加鉴权、HTTPS、限流和文件隔离。
- OCR 会提高安装体积和构建耗时，因此作为可选依赖提供。

## 开发与检查

```bash
python -m pip install -e ".[dev]"
ruff check .
pytest
python scripts/check_secrets.py
python scripts/smoke_test.py
# `scripts/clean_install_check.py` is used after installing the built wheel.
```

## License

[MIT](LICENSE)
