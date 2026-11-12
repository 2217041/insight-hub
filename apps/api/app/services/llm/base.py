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


def build_messages(history: list[dict[str, str]], user_text: str) -> list[dict[str, str]]:
    """组装发给模型的消息列表。

    history 只包含**本次之前**的消息（role/content），由调用方裁剪长度。
    """
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in history:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        # 空消息和"被中断"的占位不要喂给模型，会污染上下文
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_text})
    return messages