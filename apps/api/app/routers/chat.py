"""对话接口：SSE 流式输出 + 消息落库。

W5 收尾的关键变化：**消息不再只存浏览器，而是写进 `message` 表**。
落库策略：
1. 请求开始前（流式返回之前）先写用户消息——不能等流结束，用户可能中途关页面；
2. 流结束后写助手消息；中途断开也要写（标注"被中断"），否则上下文会断片。

会话与消息表开了 RLS，所以每个写操作都要带租户上下文（`tenant_session`）。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.models.user import User
from app.repos import conversation_repo
from app.services import chat_service
from app.services.db_ops import run_in_tenant_session

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None


def _ensure_conversation(user: User, conversation_id: str | None, first_message: str) -> str:
    """确保会话存在；不存在就建一个，标题取首条消息。"""
    if conversation_id:
        try:
            conv_id = uuid.UUID(conversation_id)
            conv = run_in_tenant_session(
                user.tenant_id, lambda db: conversation_repo.get_conversation(db, conv_id)
            )
            if conv is not None and conv.user_id == user.id:
                return str(conv.id)
        except ValueError:
            pass

    conv = run_in_tenant_session(
        user.tenant_id,
        lambda db: conversation_repo.create_conversation(
            db,
            tenant_id=user.tenant_id,
            user_id=user.id,
            title=first_message[:20] or "新对话",
        ),
    )
    return str(conv.id)


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """SSE 流式对话。

    事件：
        data: {"type":"start","message_id":"...","conversation_id":"..."}
        data: {"type":"delta","text":"..."}
        data: {"type":"done","message_id":"...","usage":{...}}
        data: {"type":"error","message":"..."}
    """
    conversation_id = _ensure_conversation(user, req.conversation_id, req.message)

    # 用户消息先落库：这样即便后面崩了，也能看到"我问过什么"
    run_in_tenant_session(
        user.tenant_id,
        lambda db: conversation_repo.add_message(
            db,
            tenant_id=user.tenant_id,
            conversation_id=uuid.UUID(conversation_id),
            role="user",
            content=req.message,
        ),
    )

    message_id = str(uuid.uuid4())
    answer = chat_service.mock_answer(req.message)

    async def gen() -> AsyncIterator[str]:
        started = time.perf_counter()
        sent = 0
        parts: list[str] = []
        completed = False
        try:
            yield chat_service.sse(
                {
                    "type": "start",
                    "message_id": message_id,
                    "conversation_id": conversation_id,
                }
            )

            step = 4
            for i in range(0, len(answer), step):
                if await request.is_disconnected():
                    return
                chunk = answer[i : i + step]
                parts.append(chunk)
                yield chat_service.sse({"type": "delta", "text": chunk})
                sent += len(chunk)
                await asyncio.sleep(0.02)

            completed = True
            yield chat_service.sse(
                {
                    "type": "done",
                    "message_id": message_id,
                    "conversation_id": conversation_id,
                    "usage": {
                        "chars": sent,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000),
                    },
                }
            )
        except asyncio.CancelledError:
            raise
        finally:
            # 中断也要存（内容截断），否则下次打开会话会缺一轮
            content = "".join(parts)
            if content:
                elapsed = round((time.perf_counter() - started) * 1000)
                if not completed:
                    content += "\n\n（生成被中断）"

                def _save(db: Session) -> None:
                    conversation_repo.add_message(
                        db,
                        tenant_id=user.tenant_id,
                        conversation_id=uuid.UUID(conversation_id),
                        role="assistant",
                        content=content,
                        completion_tokens=len(content) // 2,
                        latency_ms=elapsed,
                    )
                    conversation_repo.touch_conversation(db, uuid.UUID(conversation_id))

                try:
                    run_in_tenant_session(user.tenant_id, _save)
                except Exception:  # noqa: BLE001
                    # 落库失败不能影响已经流出去的内容
                    pass

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )