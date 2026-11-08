"""健康检查：分别探测 PostgreSQL 与 Redis。"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.services.deps import get_redis

router = APIRouter(tags=["ops"])


@router.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict:
    started = time.perf_counter()
    db_status, db_detail = "ok", ""
    try:
        version = db.execute(text("show server_version")).scalar_one()
        has_vector = db.execute(
            text("select count(*) from pg_extension where extname = 'vector'")
        ).scalar_one()
        db_detail = f"pg {version}" + (" + pgvector" if has_vector else "")
    except Exception as exc:  # noqa: BLE001
        db_status, db_detail = "error", f"{type(exc).__name__}: {exc}"

    redis_status, redis_detail = "ok", ""
    try:
        client = get_redis()
        client.ping()
        redis_detail = str(client.connection_pool.connection_kwargs.get("host"))
    except Exception as exc:  # noqa: BLE001
        redis_status, redis_detail = "error", f"{type(exc).__name__}: {exc}"

    healthy = db_status == "ok" and redis_status == "ok"
    return {
        "status": "ok" if healthy else "degraded",
        "db": db_status,
        "db_detail": db_detail,
        "redis": redis_status,
        "redis_detail": redis_detail,
        "version": get_settings().app_version,
        "cost_ms": round((time.perf_counter() - started) * 1000),
    }