"""OpenAI 兼容协议的流式客户端。

DeepSeek / Qwen(DashScope 兼容模式) / Moonshot / 本地 vLLM / Ollama 都支持这套协议，
所以一个实现能覆盖绝大多数场景——**这就是"兼容层"的价值**。

协议要点：
    POST {base}/chat/completions
    {"model": ..., "messages": [...], "stream": true}
    -> 逐行返回 `data: {...}`，最后一行是 `data: [DONE]`
    -> 文本在 choices[0].delta.content
    -> 用量在最后一个 chunk 的 usage 字段（需要 stream_options.include_usage）
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import httpx

logger = logging.getLogger(__name__)


class OpenAICompatProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
    ) -> None:
        self.name = "openai-compat"
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._model = model
        self._timeout = timeout
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
        payload: dict = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            # 让服务端在最后一帧返回用量，用于成本统计
            "stream_options": {"include_usage": True},
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"

        self._last_usage = {"prompt": 0, "completion": 0}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                f"{self._base}/chat/completions",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")[:300]
                    raise RuntimeError(f"模型服务返回 {resp.status_code}: {body}")

                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    usage = obj.get("usage")
                    if usage:
                        self._last_usage = {
                            "prompt": int(usage.get("prompt_tokens", 0)),
                            "completion": int(usage.get("completion_tokens", 0)),
                        }

                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    text = delta.get("content")
                    if text:
                        yield text