"""FastAPI 依赖：把 token 换成当前用户。

用法：受保护路由加一行

    def me(user: User = Depends(get_current_user)) -> ...:

`auto_error=False` 是为了让"没带 token"也走我们自己的统一错误体，
而不是 FastAPI 默认的 `{"detail": "Not authenticated"}`。
"""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.db.session import get_db
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