"""LLM Provider 抽象。

为什么要抽象：
- 今天用 DeepSeek，明天可能换 Qwen / 本地 vLLM / Ollama；
- 路由层只依赖 `stream()` 这个协议，换实现不用改业务代码；
- 没有 API key 时自动降级到 mock，保证开发和演示不被卡住。

统一约定：`stream()` 产出**纯文本片段**（不是 token，也不是事件），
用量信息放在 `last_usage` 里，流结束后由调用方读取。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class LLMProvider(Protocol):
    name: str

    @property
    def last_usage(self) -> dict[str, int]:
        """最近一次调用的 token 用量：{"prompt": int, "completion": int}。"""
        ...

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """流式产出文本片段。"""
        ...


SYSTEM_PROMPT = (
    "你是 Insight Hub 的企业知识库助手。"
    "回答要简洁、准确、结构清晰；不确定时明确说明，不要编造。"
    "可以使用 Markdown（标题、列表、代码块）。"
)

# 有检索结果时追加的系统提示：约束"只依据资料回答 + 必须标引用"
RAG_PROMPT = """下面的【资料】是从企业知识库检索到的片段，每条以 [编号] 开头。

回答规则（必须遵守）：
1. **只能依据资料回答**；资料里没有的内容，直接说"知识库中未找到相关内容"，不要猜测或编造；
2. 每个事实性结论后面用 [1]、[2] 标注来源编号；
3. 不要自己编造文档名、页码，引用编号即可，系统会自动映射；
4. 如果多条资料冲突，指出冲突并分别标注来源。

【资料】
{context}
"""


def build_messages(
    history: list[dict[str, str]], user_text: str, context: str = ""
) -> list[dict[str, str]]:
    """组装发给模型的消息列表。

    history 只包含**本次之前**的消息（role/content），由调用方裁剪长度。
    context 为空表示没检索到资料（此时按普通对话处理）。
    """
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context:
        messages.append(
            {"role": "system", "content": RAG_PROMPT.replace("{context}", context)}
        )
    for m in history:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        # 空消息和"被中断"的占位不要喂给模型，会污染上下文
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_text})
    return messages