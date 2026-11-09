"""数据库连接与会话。

依赖方向：db ← repos ← services ← routers
db 层不知道上面任何东西，这样才能被复用和测试。
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    echo=False,
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


def set_tenant(db: Session, tenant_id: str) -> None:
    """设置 RLS 的租户上下文。

    **必须用 SET LOCAL**：它的作用域是当前事务。
    用 SET 是会话级的，连接放回池子后下一个请求会继承上一个租户的上下文——
    那是最危险的串租户 bug，而且极难复现。
    """
    db.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(tenant_id)})