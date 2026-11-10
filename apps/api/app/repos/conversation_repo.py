"""会话与消息的数据访问层。

注意：这些表开了 RLS，调用方必须已经在事务里设置了租户上下文
（用 `tenant_session` 或 `get_tenant_db` 依赖），否则查出来是 0 行。
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message


def create_conversation(
    db: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID, title: str = "新对话"
) -> Conversation:
    conv = Conversation(tenant_id=tenant_id, user_id=user_id, title=title, summary="")
    db.add(conv)
    db.flush()
    db.refresh(conv)
    return conv


def get_conversation(db: Session, conv_id: uuid.UUID) -> Conversation | None:
    return db.get(Conversation, conv_id)


def list_conversations(
    db: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID, limit: int = 50
) -> list[Conversation]:
    return list(
        db.scalars(
            select(Conversation)
            .where(Conversation.tenant_id == tenant_id, Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
    )


def delete_conversation(db: Session, conv_id: uuid.UUID) -> None:
    db.execute(delete(Conversation).where(Conversation.id == conv_id))


def touch_conversation(db: Session, conv_id: uuid.UUID, title: str | None = None) -> None:
    conv = db.get(Conversation, conv_id)
    if conv is None:
        return
    if title:
        conv.title = title[:200]
    conv.updated_at = func.now()


def add_message(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    citations: list | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost: float = 0,
    latency_ms: int = 0,
) -> Message:
    msg = Message(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        role=role,
        content=content,
        citations=citations or [],
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost=cost,
        latency_ms=latency_ms,
    )
    db.add(msg)
    db.flush()
    db.refresh(msg)
    return msg


def list_messages(
    db: Session, *, conversation_id: uuid.UUID, limit: int = 200
) -> list[Message]:
    """按时间正序返回（对话阅读顺序）。量大时用 keyset 分页，见 docs/slow-queries.md。"""
    rows = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
    )
    return list(reversed(rows))