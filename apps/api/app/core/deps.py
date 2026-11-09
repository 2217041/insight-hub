"""FastAPI 依赖：当前用户、租户会话。

`get_tenant_db` 是本文件最重要的东西：
它把 `app.tenant_id` 写进事务上下文，让 RLS 策略生效。
**没有它，document/chunk/message 这些表查出来永远是 0 行**（策略求值为 NULL）。
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.db.session import get_db, set_tenant
from app.models.user import User
from app.services import auth_service

_bearer = HTTPBearer(auto_error=False, description="Bearer <access_token>")


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise AppError(ErrorCode.UNAUTHORIZED, "未登录", http_status=401)
    return auth_service.authenticate(db, creds.credentials)


def get_tenant_db(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Iterator[Session]:
    """给数据库会话设置租户上下文，并在请求结束时统一提交。

    **为什么由依赖层提交，而不是在 repo 里 commit**：
    `set_config(..., is_local=true)` 的作用域是**当前事务**。
    repo 里一旦 commit，事务结束、上下文失效，后续任何查询都会被 RLS 挡住
    （表现为 `Could not refresh instance` 或查不到刚写入的行）。

    所以整个请求共用一个事务：进来设上下文 → 结束统一 commit/rollback。
    """
    set_tenant(db, user.tenant_id)
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise