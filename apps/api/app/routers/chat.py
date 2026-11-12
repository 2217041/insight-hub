"""对话接口：SSE 流式输出 + 消息落库 + 真实模型接入（W9）。

这一版和 W5 的差别：
1. 不再是写死的占位回答，而是调用 `llm.get_provider()`；
2. **带历史**：取最近 N 条消息一起发给模型，多轮才有上下文；
3. 记录 token 用量与成本（`prompt_tokens` / `completion_tokens` / `cost`）；
4. provider 出错时**发 error 事件**而不是让流断掉——前端才能显示"重试"。
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

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.models.user import User
from app.repos import conversation_repo
from app.services import chat_service, llm, retrieval
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


def _load_history(tenant_id, conv_id: uuid.UUID, limit: int) -> list[dict[str, str]]:
    rows = run_in_tenant_session(
        tenant_id,
        lambda db: conversation_repo.list_messages(db, conversation_id=conv_id, limit=limit),
    )
    return [{"role": m.role, "content": m.content} for m in rows]


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """SSE 流式对话。

    事件：
        data: {"type":"start","message_id":"...","conversation_id":"...","provider":"..."}
        data: {"type":"delta","text":"..."}
        data: {"type":"done","message_id":"...","usage":{...}}
        data: {"type":"error","message":"..."}
    """
    settings = get_settings()
    conversation_id = _ensure_conversation(user, req.conversation_id, req.message)
    conv_uuid = uuid.UUID(conversation_id)

    # 历史要在写入本条用户消息之前取，否则会把自己也带进去
    history = _load_history(
        user.tenant_id, conv_uuid, settings.llm_max_history_messages
    )

    run_in_tenant_session(
        user.tenant_id,
        lambda db: conversation_repo.add_message(
            db,
            tenant_id=user.tenant_id,
            conversation_id=conv_uuid,
            role="user",
            content=req.message,
        ),
    )

    provider = llm.get_provider()

    # ---- W11：先检索，再生成 ----
    # 检索涉及 CPU 密集的向量化，放线程池，避免阻塞事件循环
    retrieved: list[dict] = await asyncio.to_thread(
        lambda: run_in_tenant_session(
            user.tenant_id,
            lambda db: retrieval.search(
                db, tenant_id=user.tenant_id, query=req.message
            ),
        )
    )
    context, citations = retrieval.build_context(retrieved)
    messages = llm.build_messages(history, req.message, context)
    message_id = str(uuid.uuid4())

    async def gen() -> AsyncIterator[str]:
        started = time.perf_counter()
        parts: list[str] = []
        completed = False
        error_text: str | None = None

        try:
            yield chat_service.sse(
                {
                    "type": "start",
                    "message_id": message_id,
                    "conversation_id": conversation_id,
                    "provider": provider.name,
                    "retrieved": len(citations),
                }
            )

            # 没有检索到任何块 → 直接拒答，不要浪费一次模型调用（也避免模型硬编）
            if not context:
                refusal = (
                    "知识库中未找到相关内容。\n\n"
                    "可能的原因：\n"
                    "1. 还没有上传相关文档，或文档仍在解析中；\n"
                    "2. 换个说法再问一次（试试文档里出现的具体名词/编号）。"
                )
                parts.append(refusal)
                yield chat_service.sse({"type": "delta", "text": refusal})
                completed = True
                yield chat_service.sse(
                    {
                        "type": "done",
                        "message_id": message_id,
                        "conversation_id": conversation_id,
                        "provider": "refusal",
                        "usage": {"prompt": 0, "completion": 0, "elapsed_ms": 0},
                    }
                )
                return

            async for text in provider.stream(
                messages,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            ):
                if await request.is_disconnected():
                    return
                parts.append(text)
                yield chat_service.sse({"type": "delta", "text": text})

            completed = True
            usage = provider.last_usage
            yield chat_service.sse(
                {
                    "type": "done",
                    "message_id": message_id,
                    "conversation_id": conversation_id,
                    "provider": provider.name,
                    "usage": {
                        **usage,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000),
                    },
                }
            )
        except Exception as exc:  # noqa: BLE001
            # 不要把异常直接抛给 ASGI，否则前端只看到流断了、没有任何信息
            error_text = f"{type(exc).__name__}: {exc}"[:500]
            yield chat_service.sse({"type": "error", "message": error_text})
        finally:
            content = "".join(parts)
            if content or error_text:
                elapsed = round((time.perf_counter() - started) * 1000)
                usage = provider.last_usage
                if not completed and content:
                    content += "\n\n（生成被中断）"

                prompt_tokens = usage.get("prompt", 0)
                completion_tokens = usage.get("completion", 0)
                cost = (
                    prompt_tokens * settings.llm_price_in_per_1m
                    + completion_tokens * settings.llm_price_out_per_1m
                ) / 1_000_000

                def _save(db: Session) -> None:
                    conversation_repo.add_message(
                        db,
                        tenant_id=user.tenant_id,
                        conversation_id=conv_uuid,
                        role="assistant",
                        content=content,
                        citations=citations,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        cost=cost,
                        latency_ms=elapsed,
                    )
                    conversation_repo.touch_conversation(db, conv_uuid)

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