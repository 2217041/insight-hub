"""任务队列（arq）连接与投递。

**为什么要单独一个模块**：
`redis-py` 的 `Redis` 客户端没有 `enqueue_job`，那是 arq 的 `ArqRedis` 才有的能力。
两者连的是同一个 Redis，但客户端类型不同——这是最容易踩的坑。

连接池做成模块级懒加载：arq 的 pool 内部维护连接，每次请求新建会泄漏连接。
"""

from __future__ import annotations

import logging

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_pool: ArqRedis | None = None


async def get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _pool


async def enqueue_parse(document_id: str, tenant_id: str) -> bool:
    """投递解析任务。返回是否投递成功。

    失败时不抛给调用方：文件已经落盘落库，让用户看到"排队失败"
    比 500 更有信息量，重试也用不上。
    """
    try:
        pool = await get_pool()
        await pool.enqueue_job("parse_document", document_id, tenant_id)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("enqueue_failed document_id=%s", document_id)
        return False


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None