"""在"带租户上下文"的短事务里执行同步数据库操作。

为什么需要它：
- RLS 依赖事务级的 `app.tenant_id`，所以每个独立操作都要自己开事务；
- 路由里是异步函数，而 SQLAlchemy 的 Session 是同步的——
  直接调用会阻塞事件循环，所以提供 `run_in_tenant_session` 用线程池执行。

`run_async_in_tenant_session` 给生成器/异步上下文用。
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Session

from app.db.session import tenant_session

T = TypeVar("T")


def run_in_tenant_session(tenant_id: uuid.UUID, fn: Callable[[Session], T]) -> T:
    """同步执行：在一个设置了租户上下文的事务里跑 fn，结束后统一提交。"""
    with tenant_session(tenant_id) as db:
        return fn(db)


async def run_async_in_tenant_session(
    tenant_id: uuid.UUID, fn: Callable[[Session], T]
) -> T:
    """异步版本：把同步 DB 操作丢到线程池，避免阻塞事件循环。"""
    return await asyncio.to_thread(run_in_tenant_session, tenant_id, fn)