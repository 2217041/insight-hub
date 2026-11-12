"""Provider 工厂：按配置选择实现。

设计取舍：
- 只做"选哪个实现"，不做重试/降级（那是路由层的事）；
- 没有 key 就降级到 mock **并打日志**——静默降级会让人以为接了模型。
"""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.services.llm.base import LLMProvider, SYSTEM_PROMPT, build_messages
from app.services.llm.mock import MockProvider
from app.services.llm.openai_compat import OpenAICompatProvider

logger = logging.getLogger(__name__)

__all__ = ["LLMProvider", "SYSTEM_PROMPT", "build_messages", "get_provider"]


def get_provider() -> LLMProvider:
    s = get_settings()
    name = (s.llm_provider or "mock").lower()

    if name == "mock":
        return MockProvider()

    if name in ("openai", "ollama", "vllm"):
        if not s.llm_api_key and name != "ollama":
            # ollama 本地服务通常不校验 key，其他都需要
            logger.warning(
                "llm_provider=%s 但没有配置 LLM_API_KEY，降级为 mock", name
            )
            return MockProvider()
        return OpenAICompatProvider(
            base_url=s.llm_base_url,
            api_key=s.llm_api_key,
            model=s.llm_model,
        )

    logger.warning("未知的 llm_provider=%s，降级为 mock", name)
    return MockProvider()