"""Insight Hub API —— W1 最小闭环

目标：把 Web → API → PostgreSQL / Redis 这条链路打通，作为后续 RAG / Agent 的骨架。

启动：
    uv run uvicorn main:app --reload --port 8000

自检：
    http://127.0.0.1:8000/api/health  ->  {"status":"ok","db":"ok","redis":"ok",...}
    http://127.0.0.1:8000/docs        ->  FastAPI 自动生成的 OpenAPI 文档
"""

from __future__ import annotations

import os
import time
from functools import lru_cache

import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

APP_VERSION = "0.1.0"
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://insight:insight@127.0.0.1:5432/insight"
)
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

app = FastAPI(
    title="Insight Hub API",
    version=APP_VERSION,
    description="多租户企业知识库 + AI Agent 工作台（W1 阶段：仅健康检查）",
)

# 前端开发服务器默认在 3000；W2 起会有客户端的跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """全局复用连接池；pool_pre_ping 避免拿到失效连接。"""
    return create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=5)


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    return redis.from_url(REDIS_URL, socket_connect_timeout=2, decode_responses=True)


def _check_db() -> tuple[str, str]:
    """返回 (状态, 补充信息)。"""
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
    except Exception as exc:  # noqa: BLE001 - 健康检查要吞掉异常并报出来
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


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"service": "insight-hub-api", "version": APP_VERSION, "docs": "/docs"}


@app.get("/api/health", tags=["ops"])
def health() -> dict:
    """聚合健康检查：任一依赖不可用则整体降级为 degraded。"""
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


@app.get("/api/echo", tags=["ops"])
def echo(q: str = "hello") -> dict:
    """最小的一跳，用来验证参数校验与 JSON 序列化链路。"""
    return {"echo": q, "length": len(q)}