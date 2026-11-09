"""鉴权业务逻辑：注册、登录、换发 token。

这一层是"该不该"的地方：邮箱重复怎么办、密码错了怎么算、用户被禁用怎么拒。
它不知道 HTTP 状态码，只抛 AppError（由全局处理器翻译）。
"""

from __future__ import annotations

import uuid

import jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repos import tenant_repo, user_repo
from app.schemas.auth import TokenResponse


def register(db: Session, *, email: str, password: str, name: str = "") -> User:
    if user_repo.get_by_email(db, email):
        # 409 而不是 400：这是"资源已存在"，不是参数错误
        raise AppError(ErrorCode.CONFLICT, "该邮箱已注册", http_status=409)

    # W4 起用户必须属于某个租户。注册即创建一个个人租户（团队版由邀请流程加入）。
    # 两个插入放在同一个事务里：任一步失败都不能留下"有租户没用户"的脏数据。
    display = name or email.split("@")[0]
    tenant = tenant_repo.create(db, name=f"{display} 的空间")
    user = user_repo.create(
        db,
        tenant_id=tenant.id,
        email=email,
        name=display,
        password_hash=hash_password(password),
        role="owner",
        commit=False,
    )
    db.commit()
    db.refresh(user)
    return user


def login(db: Session, *, email: str, password: str) -> TokenResponse:
    user = user_repo.get_by_email(db, email)
    # 注意：邮箱不存在和密码错误返回同一个提示，避免被用来枚举账号
    if not user or not verify_password(user.password_hash, password):
        raise AppError(ErrorCode.UNAUTHORIZED, "邮箱或密码错误", http_status=401)
    if not user.is_active:
        raise AppError(ErrorCode.FORBIDDEN, "账号已被禁用", http_status=403)
    return issue_tokens(user)


def issue_tokens(user: User) -> TokenResponse:
    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=settings.access_token_minutes * 60,
    )


def refresh(db: Session, refresh_token: str) -> TokenResponse:
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
        user_id = uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise AppError(ErrorCode.UNAUTHORIZED, "刷新令牌无效或已过期", http_status=401)

    user = user_repo.get_by_id(db, user_id)
    if not user or not user.is_active:
        raise AppError(ErrorCode.UNAUTHORIZED, "用户不存在或已禁用", http_status=401)
    return issue_tokens(user)


def authenticate(db: Session, token: str) -> User:
    """供 get_current_user 依赖调用：把 access token 换成用户。"""
    try:
        payload = decode_token(token, expected_type="access")
        user_id = uuid.UUID(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise AppError(ErrorCode.UNAUTHORIZED, "登录已过期，请重新登录", http_status=401)
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise AppError(ErrorCode.UNAUTHORIZED, "无效的登录凭证", http_status=401)

    user = user_repo.get_by_id(db, user_id)
    if not user or not user.is_active:
        raise AppError(ErrorCode.UNAUTHORIZED, "用户不存在或已禁用", http_status=401)
    return user