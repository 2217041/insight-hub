"""Insight Hub API

W1：健康检查（Web → API → PostgreSQL / Redis）
W2：SSE 流式对话接口（先用占位回复，W9 接真模型）
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from functools import lru_cache
from typing import AsyncIterator

import redis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

APP_VERSION = "0.2.0"
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://insight:insight@127.0.0.1:5432/insight"
)
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

app = FastAPI(
    title="Insight Hub API",
    version=APP_VERSION,
    description="多租户企业知识库 + AI Agent 工作台",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# 基础设施
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=5)


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    return redis.from_url(REDIS_URL, socket_connect_timeout=2, decode_responses=True)


def _check_db() -> tuple[str, str]:
    started = time.perf_counter()
    try:
        with get_engine().connect() as conn:
            version = conn.execute(text("show server_version")).scalar_one()
            has_vector = conn.execute(
                text("select count(*) from pg_extension where extname = 'vector'")
            ).scalar_one()
        cost = (time.perf_counter() - started) * 1000
        extra = f"pg {version}" + (" + pgvector" if has_vector else " (no pgvector)")
        return "ok", f"{extra} / {cost:.0f} ms"
    except Exception as exc:  # noqa: BLE001
        return "error", f"{type(exc).__name__}: {exc}"


def _check_redis() -> tuple[str, str]:
    started = time.perf_counter()
    try:
        client = get_redis()
        client.ping()
        cost = (time.perf_counter() - started) * 1000
        return "ok", f"{client.connection_pool.connection_kwargs.get('host')} / {cost:.0f} ms"
    except Exception as exc:  # noqa: BLE001
        return "error", f"{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------- #
# 运维接口
# --------------------------------------------------------------------------- #
@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"service": "insight-hub-api", "version": APP_VERSION, "docs": "/docs"}


@app.get("/api/health", tags=["ops"])
def health() -> dict:
    db_status, db_detail = _check_db()
    redis_status, redis_detail = _check_redis()
    healthy = db_status == "ok" and redis_status == "ok"
    return {
        "status": "ok" if healthy else "degraded",
        "db": db_status,
        "db_detail": db_detail,
        "redis": redis_status,
        "redis_detail": redis_detail,
        "version": APP_VERSION,
    }


# --------------------------------------------------------------------------- #
# W2：SSE 流式对话
# --------------------------------------------------------------------------- #
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None


def sse(payload: dict) -> str:
    """把一条数据编码成 SSE 帧。注意结尾必须是两个换行。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _mock_answer(question: str) -> str:
    """W2 的占位回复。

    故意包含标题、列表、行内代码和代码块，用来验证前端 Markdown 渲染。
    真正接大模型在 W9，那时把这里换成模型调用即可。
    """
    return (
        f"你问的是：**{question}**\n\n"
        "这是 W2 的占位回答，用来验证「浏览器 ← SSE ← FastAPI」这条流式链路。\n\n"
        "## 这条链路做了什么\n\n"
        "1. 前端用 `fetch` 发 POST 请求，拿到 `ReadableStream`；\n"
        "2. 后端用 `StreamingResponse` 一段段写 `data: {...}\\n\\n`；\n"
        "3. 前端按空行切帧、按 `type` 分发，拼进当前消息。\n\n"
        "> 为什么不用 `EventSource`？因为它只支持 GET，无法携带消息体。\n\n"
        "```python\n"
        "async def gen():\n"
        "    yield sse({'type': 'delta', 'text': '...'})\n"
        "    yield sse({'type': 'done'})\n"
        "```\n\n"
        "W9 会把这里的 `_mock_answer` 换成真实模型调用，其余代码不用动，这就是先定协议的好处。"
    )


@app.post("/api/chat/stream", tags=["chat"])
async def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    """SSE 流式对话。

    事件格式：
        data: {"type":"start","message_id":"...","conversation_id":"..."}
        data: {"type":"delta","text":"..."}
        data: {"type":"done","message_id":"...","usage":{...}}
        data: {"type":"error","message":"..."}
    """
    conversation_id = req.conversation_id or str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    answer = _mock_answer(req.message)

    async def gen() -> AsyncIterator[str]:
        started = time.perf_counter()
        sent = 0
        try:
            yield sse(
                {
                    "type": "start",
                    "message_id": message_id,
                    "conversation_id": conversation_id,
                }
            )

            # 按 4 个字符一段模拟逐字输出；真实模型这里是 token 流
            step = 4
            for i in range(0, len(answer), step):
                if await request.is_disconnected():
                    # 客户端点了「停止生成」或关了页面
                    return
                chunk = answer[i : i + step]
                yield sse({"type": "delta", "text": chunk})
                sent += len(chunk)
                await asyncio.sleep(0.02)

            yield sse(
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
            # 连接被取消：这里可以记录「用户中断」埋点
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