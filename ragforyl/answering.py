from __future__ import annotations

from typing import Any

from ragforyl.config import Settings
from ragforyl.llm import OpenAICompatibleClient
from ragforyl.retrieval import KnowledgeBase


class AnswerService:
    def __init__(self, settings: Settings, knowledge_base: KnowledgeBase) -> None:
        self.settings = settings
        self.knowledge_base = knowledge_base

    def answer(self, question: str, *, top_k: int = 6) -> dict[str, Any]:
        retrieval = self.knowledge_base.search(question, top_k=top_k)
        if self.settings.llm_enabled and retrieval["context"]:
            client = OpenAICompatibleClient(
                api_key=self.settings.llm_api_key,
                base_url=self.settings.llm_base_url,
                model=self.settings.llm_model,
                timeout_seconds=self.settings.llm_timeout_seconds,
            )
            answer = client.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是严谨的知识库助手。只依据给定资料回答；"
                            "每个关键结论使用 [S1] 形式标注来源。"
                            "资料不足时明确说明，不得编造。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"问题：{question}\n\n检索资料：\n{retrieval['context']}",
                    },
                ],
                temperature=0.1,
                max_tokens=1800,
            )
            mode = "llm"
        else:
            answer = _offline_answer(retrieval)
            mode = "retrieval_only"
        return {"answer": answer, "answer_mode": mode, "retrieval": retrieval}


def _offline_answer(retrieval: dict[str, Any]) -> str:
    if not retrieval["nodes"] and not retrieval["sources"]:
        return "当前知识库中没有找到足够相关的内容。请补充资料或换一种问法。"
    lines = ["未配置生成模型，已完成知识图谱检索。相关内容如下："]
    for node in retrieval["nodes"][:5]:
        description = str(node.get("description") or "").strip()
        line = f"- {node['name']}"
        if description:
            line += f"：{description}"
        lines.append(line)
    if retrieval["sources"]:
        refs = "、".join(f"[{item['reference']}]" for item in retrieval["sources"][:4])
        lines.append(
            f"可核对原文证据：{refs}。配置 LLM_API_KEY 与 LLM_MODEL 后可生成带引用的完整回答。"
        )
    return "\n".join(lines)
