"""占位 Provider：没有 API key 或显式配置 mock 时使用。

它和真实 Provider 实现同一个接口，所以**上层代码完全不用区分**。
这样开发和演示不会被"没 key"卡住，也让 W9 的接入可以渐进式完成。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator


def _compose_answer(user_text: str) -> str:
    return (
        f"你问的是：**{user_text}**\n\n"
        "当前使用的是**占位回复**（未配置模型 API Key）。\n\n"
        "## 接入真实模型只需三步\n\n"
        "1. 在服务器的 `.env` 里填 `LLM_API_KEY`；\n"
        "2. 把 `LLM_PROVIDER` 改成 `openai`（任何 OpenAI 兼容服务都行）；\n"
        "3. 重启 api 容器。\n\n"
        "```bash\n"
        "# /opt/insight-hub/.env\n"
        "LLM_PROVIDER=openai\n"
        "LLM_BASE_URL=https://api.deepseek.com/v1\n"
        "LLM_MODEL=deepseek-chat\n"
        "LLM_API_KEY=sk-xxxx\n"
        "```\n\n"
        "> 代码里已经做好了 provider 抽象：换模型不用改业务逻辑。"
    )


class MockProvider:
    name = "mock"

    def __init__(self) -> None:
        self._last_usage: dict[str, int] = {"prompt": 0, "completion": 0}

    @property
    def last_usage(self) -> dict[str, int]:
        return self._last_usage

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        user_text = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        answer = _compose_answer(user_text)

        # 粗略估算：中文约 1 字 1 token，这里按 2 字符 1 token 折中
        prompt_chars = sum(len(m["content"]) for m in messages)
        self._last_usage = {
            "prompt": max(1, prompt_chars // 2),
            "completion": max(1, len(answer) // 2),
        }

        for i in range(0, len(answer), 6):
            yield answer[i : i + 6]
            await asyncio.sleep(0.02)