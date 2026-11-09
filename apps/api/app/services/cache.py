"""Redis 缓存与限流（W5）。

两个都要注意"缓存不该成为故障源"：
- 缓存读失败 → 回源数据库，不让请求失败；
- 限流读失败 → fail-open（放行），宁可多放几个也不要整站不可用。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.deps import get_redis

logger = logging.getLogger(__name__)


def cache_get(key: str) -> Any | None:
    try:
        raw = get_redis().get(key)
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001
        logger.warning("cache_get_failed key=%s", key, exc_info=True)
        return None


def cache_set(key: str, value: Any, ttl: int = 30) -> None:
    try:
        get_redis().set(key, json.dumps(value, ensure_ascii=False, default=str), ex=ttl)
    except Exception:  # noqa: BLE001
        logger.warning("cache_set_failed key=%s", key, exc_info=True)


def cache_delete_prefix(prefix: str) -> None:
    """按前缀失效。数据量大时应改用 SCAN；当前 key 很少，keys 足够。"""
    try:
        client = get_redis()
        for key in client.keys(f"{prefix}*"):
            client.delete(key)
    except Exception:  # noqa: BLE001
        logger.warning("cache_delete_failed prefix=%s", prefix, exc_info=True)


def rate_limit(key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
    """固定窗口限流。返回 (是否放行, 当前计数)。

    简单够用，但有临界问题：窗口边界处可能瞬时放行 2 倍流量。
    更严谨的是滑动窗口或令牌桶（W18 再优化，那时会有真实压测数据）。
    """
    try:
        client = get_redis()
        current = client.incr(key)
        if current == 1:
            client.expire(key, window_seconds)
        return current <= limit, int(current)
    except Exception:  # noqa: BLE001
        logger.warning("rate_limit_failed key=%s", key, exc_info=True)
        return True, 0  # fail-open