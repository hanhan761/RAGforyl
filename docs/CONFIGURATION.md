# Configuration

所有配置来自环境变量或项目根目录 `.env`。真实密钥只写入 `.env`，该文件已被 Git 忽略。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `RAGFORYL_DATA_DIR` | `./data` | 资料与索引根目录 |
| `RAGFORYL_EXTRACTION_MODE` | `auto` | `auto` / `llm` / `heuristic` |
| `RAGFORYL_CHUNK_SIZE` | `1200` | 单个分块目标字符数 |
| `RAGFORYL_CHUNK_OVERLAP` | `120` | 相邻分块重叠字符数 |
| `RAGFORYL_MAX_UPLOAD_MB` | `30` | 网页单文件上传上限 |
| `LLM_API_KEY` | 空 | OpenAI-compatible API Key |
| `LLM_BASE_URL` | OpenAI API | 兼容接口的 `/v1` 根地址 |
| `LLM_MODEL` | 空 | 模型名；留空表示不调用模型 |
| `LLM_TIMEOUT_SECONDS` | `90` | 单次模型请求超时 |

## 正式数据建议

1. 先用 `heuristic` 跑通目录、解析和质量报告。
2. 再切换 `llm` 重建，确保模型异常不会被自动回退掩盖。
3. 检查 `quality_report.json`、随机抽查关系的 `evidence_id`。
4. 固定 `.env` 中的模型名与分块参数后再批量生产。

## 公网部署

当前 Web 服务是本机工具，不含账号系统。公网部署至少应增加反向代理 HTTPS、身份认证、请求限流、恶意文件扫描、独立租户目录和模型费用配额。
