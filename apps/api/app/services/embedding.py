"""向量化：把文本变成向量。

两个实现：
- **local**：fastembed（ONNX 运行时）+ bge-small-zh-v1.5，512 维，不需要任何 API key；
- **openai**：任意兼容 `/embeddings` 的服务（阿里百炼 / 硅基流动 / OpenAI）。

为什么默认本地：
1. DeepSeek 没有 embedding 接口（实测 `/v1/embeddings` 404）；
2. 额外注册一个 key 是摩擦，本地模型够用且无网络依赖；
3. ONNX 比 torch 轻一个数量级（服务器只有 1.7 GB 内存）。

代价：512 维、small 规模，语义精度不如 bge-m3（1024 维）。
**换模型必须同步迁移 `chunk.embedding` 的列维度**，否则插入会报类型错误。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LocalEmbedder:
    name = "local"

    def __init__(self, model_name: str, cache_dir: str) -> None:
        # 延迟加载：只有真正用到时才下载/加载模型（首次约 100 MB）
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._model = None

    def _ensure(self):
        if self._model is None:
            from fastembed import TextEmbedding

            logger.info("loading_embedding_model model=%s", self._model_name)
            self._model = TextEmbedding(
                model_name=self._model_name, cache_dir=self._cache_dir
            )
        return self._model

    @property
    def dim(self) -> int:
        return get_settings().embedding_dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """同步方法（CPU 密集）：在异步环境里请用 asyncio.to_thread 包一层。"""
        model = self._ensure()
        return [list(map(float, v)) for v in model.embed(list(texts))]


class OpenAICompatEmbedder:
    name = "openai"

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._model = model

    @property
    def dim(self) -> int:
        return get_settings().embedding_dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{self._base}/embeddings",
                headers=headers,
                json={"model": self._model, "input": list(texts)},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
        # 按 index 排序，保证与输入顺序一致
        data.sort(key=lambda d: d.get("index", 0))
        return [d["embedding"] for d in data]


_embedder = None


def get_embedder():
    global _embedder
    if _embedder is not None:
        return _embedder

    s = get_settings()
    if (s.embedding_provider or "local").lower() == "openai":
        if not s.llm_api_key:
            logger.warning("embedding_provider=openai 但没有 api_key，降级为 local")
            _embedder = LocalEmbedder(s.embedding_model, s.embedding_cache_dir)
        else:
            _embedder = OpenAICompatEmbedder(
                s.llm_base_url, s.llm_api_key, s.embedding_model
            )
    else:
        _embedder = LocalEmbedder(s.embedding_model, s.embedding_cache_dir)
    return _embedder