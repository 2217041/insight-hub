"""文档接口：上传 / 列表 / 详情 / SSE 进度。"""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_user, get_tenant_db
from app.core.errors import AppError, ErrorCode
from app.db.session import SessionLocal, set_tenant
from app.models.user import User
from app.repos import document_repo
from app.schemas.document import (
    DocumentListResponse,
    DocumentResponse,
    UploadResponse,
)
from app.services import cache, document_service

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
) -> UploadResponse:
    settings = get_settings()

    # 限流放在最前面：大文件不该先进内存再被拒
    allowed, current = cache.rate_limit(
        f"rl:upload:{user.tenant_id}", settings.upload_rate_per_minute
    )
    if not allowed:
        raise AppError(
            ErrorCode.RATE_LIMITED,
            f"上传过于频繁（每分钟最多 {settings.upload_rate_per_minute} 次）",
            http_status=429,
            detail={"current": current, "limit": settings.upload_rate_per_minute},
        )

    data = await file.read()
    doc, deduplicated, queued = await document_service.upload(
        db,
        tenant_id=user.tenant_id,
        filename=file.filename or "untitled",
        mime=file.content_type or "application/octet-stream",
        data=data,
    )
    return UploadResponse(
        document=DocumentResponse.model_validate(doc),
        deduplicated=deduplicated,
        queued=queued,
    )


@router.get("", response_model=DocumentListResponse)
def list_documents(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
) -> DocumentListResponse:
    items, cached = document_service.list_documents(db, tenant_id=user.tenant_id)
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(x) for x in items],
        total=len(items),
        cached=cached,
    )


@router.get("/{doc_id}", response_model=DocumentResponse)
def get_document(
    doc_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
) -> Document:
    doc = document_service.get_document(db, tenant_id=user.tenant_id, doc_id=doc_id)
    return DocumentResponse.model_validate(doc)


@router.get("/{doc_id}/progress")
async def document_progress(
    doc_id: uuid.UUID,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """SSE 推送解析进度。

    **为什么用轮询数据库而不是 Redis Pub/Sub**：
    现在只有一个 API 实例、任务几秒就结束，轮询最省事；
    多实例部署时轮询会打库，那时换 Redis Streams（W6 部署后再评估）。

    注意：每次轮询用一个**新的短事务**，避免长连接占着连接池。
    """
    tenant_id = user.tenant_id

    def read_state() -> dict | None:
        with SessionLocal() as s:
            set_tenant(s, tenant_id)
            doc = document_repo.get(s, doc_id)
            if doc is None or doc.tenant_id != tenant_id:
                return None
            return {
                "status": doc.status,
                "progress": doc.progress,
                "chunk_count": doc.chunk_count,
                "error_reason": doc.error_reason,
            }

    async def gen():
        last: str | None = None
        for _ in range(240):  # 最多等 120 秒
            state = await asyncio.to_thread(read_state)
            if state is None:
                yield f"data: {json.dumps({'type': 'error', 'message': '文档不存在'})}\n\n"
                return

            snapshot = json.dumps(state, ensure_ascii=False, sort_keys=True)
            if snapshot != last:
                last = snapshot
                yield f"data: {json.dumps({'type': 'progress', **state}, ensure_ascii=False)}\n\n"

            if state["status"] in ("ready", "failed"):
                return
            await asyncio.sleep(0.5)

        yield f"data: {json.dumps({'type': 'timeout'})}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )