"""对话路由：SSE 流式输出。"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services import chat_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None


@router.post("/stream")
async def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    """SSE 流式对话。

    事件：
        data: {"type":"start","message_id":"...","conversation_id":"..."}
        data: {"type":"delta","text":"..."}
        data: {"type":"done","message_id":"...","usage":{...}}
        data: {"type":"error","message":"..."}
    """
    conversation_id = req.conversation_id or str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    answer = chat_service.mock_answer(req.message)

    async def gen() -> AsyncIterator[str]:
        started = time.perf_counter()
        sent = 0
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
                    return  # 用户点了停止或关了页面
                chunk = answer[i : i + step]
                yield chat_service.sse({"type": "delta", "text": chunk})
                sent += len(chunk)
                await asyncio.sleep(0.02)

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

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 让 Nginx 不要缓冲
        },
    )