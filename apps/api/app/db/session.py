"""数据库连接与会话。

依赖方向：db ← repos ← services ← routers
db 层不知道上面任何东西，这样才能被复用和测试。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    echo=False,
    # 数据库没起时要**快速失败**，而不是让请求挂到超时：
    # 没有 connect_timeout 时 psycopg 会一直等，健康检查表现为"超时"而不是"数据库不可用"。
    connect_args={"connect_timeout": 3},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：每个请求一个 session，用完自动关闭。

    必须是生成器（yield），不能 return —— 否则请求结束后 session 不会释放。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def set_tenant(db: Session, tenant_id) -> None:
    """设置 RLS 的租户上下文。

    **必须用事务级设置**（第三个参数 `true` = is_local，等价于 SET LOCAL）：
    会话级设置会随连接回到池子，下一个请求就可能读到上一个租户的数据。

    **为什么不用 `SET LOCAL app.tenant_id = :tid`**：
    PostgreSQL 的 SET 语句不接受参数绑定，写成 `$1` 会直接语法报错。
    `set_config(name, value, is_local)` 是函数调用，可以正常绑定参数。
    """
    db.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )


@contextmanager
def tenant_session(tenant_id) -> Iterator[Session]:
    """一次性租户会话：自动 SET LOCAL、提交/回滚、关闭。

    worker 里每个步骤开一个，避免"commit 之后 SET LOCAL 失效"的坑——
    `SET LOCAL` 随事务结束而失效，长事务里中间 commit 会丢掉租户上下文。
    """
    db = SessionLocal()
    try:
        set_tenant(db, tenant_id)
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()