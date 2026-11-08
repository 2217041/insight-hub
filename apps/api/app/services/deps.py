"""共享依赖：Redis 客户端（懒加载 + 单例）。"""

from __future__ import annotations

from functools import lru_cache

import redis

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    return redis.from_url(
        get_settings().redis_url, socket_connect_timeout=2, decode_responses=True
    )