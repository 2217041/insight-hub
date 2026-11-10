"""会话接口：列表 / 创建 / 详情（含消息）/ 删除。

所有查询都走 `get_tenant_db`，它负责设置 RLS 的租户上下文。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_tenant_db
from app.core.errors import AppError, ErrorCode
from app.models.user import User
from app.repos import conversation_repo
from app.schemas.conversation import (
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    CreateConversationRequest,
    MessageResponse,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=ConversationListResponse)
def list_conversations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
) -> ConversationListResponse:
    items = conversation_repo.list_conversations(
        db, tenant_id=user.tenant_id, user_id=user.id
    )
    return ConversationListResponse(
        items=[ConversationResponse.model_validate(c) for c in items],
        total=len(items),
    )


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: CreateConversationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
) -> ConversationResponse:
    conv = conversation_repo.create_conversation(
        db, tenant_id=user.tenant_id, user_id=user.id, title=payload.title
    )
    return ConversationResponse.model_validate(conv)


@router.get("/{conv_id}", response_model=ConversationDetailResponse)
def get_conversation(
    conv_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
) -> ConversationDetailResponse:
    conv = conversation_repo.get_conversation(db, conv_id)
    # 越权访问统一返回 404：不告诉对方"这个会话存在但不属于你"
    if conv is None or conv.user_id != user.id:
        raise AppError(ErrorCode.NOT_FOUND, "会话不存在", http_status=404)

    messages = conversation_repo.list_messages(db, conversation_id=conv_id)
    return ConversationDetailResponse(
        conversation=ConversationResponse.model_validate(conv),
        messages=[MessageResponse.model_validate(m) for m in messages],
    )


@router.delete("/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conv_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
) -> None:
    conv = conversation_repo.get_conversation(db, conv_id)
    if conv is None or conv.user_id != user.id:
        raise AppError(ErrorCode.NOT_FOUND, "会话不存在", http_status=404)
    conversation_repo.delete_conversation(db, conv_id)