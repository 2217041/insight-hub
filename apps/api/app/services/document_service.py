"""文档业务逻辑：上传（幂等）→ 落盘 → 落库 → 投递异步任务 → 列表（带缓存）。"""

from __future__ import annotations

import hashlib
import logging
import uuid

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.models.document import Document
from app.repos import document_repo
from app.services import cache, storage, task_queue

logger = logging.getLogger(__name__)

CACHE_PREFIX = "docs:list:"


def _cache_key(tenant_id: uuid.UUID) -> str:
    return f"{CACHE_PREFIX}{tenant_id}"


async def upload(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    filename: str,
    mime: str,
    data: bytes,
) -> tuple[Document, bool, bool]:
    """返回 (文档, 是否命中幂等, 是否投递了任务)。"""
    settings = get_settings()

    if not data:
        raise AppError(ErrorCode.VALIDATION, "文件内容为空", http_status=422)
    if len(data) > settings.upload_max_bytes:
        raise AppError(
            ErrorCode.VALIDATION,
            f"文件超过 {settings.upload_max_bytes // 1024 // 1024} MB 限制",
            http_status=422,
        )

    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in settings.allowed_extensions:
        raise AppError(
            ErrorCode.VALIDATION,
            f"不支持的格式 {ext}，允许：{', '.join(settings.allowed_extensions)}",
            http_status=422,
        )

    content_hash = hashlib.sha256(data).hexdigest()

    # 幂等：同租户同内容直接返回旧记录，不重复解析（省算力）
    existing = document_repo.get_by_hash(db, tenant_id, content_hash)
    if existing is not None:
        return existing, True, False

    doc_id = uuid.uuid4()
    # 先落盘再落库：文件写成功但数据库失败，最多留一个孤儿文件（可清理）；
    # 反过来会出现"有记录但文件不存在"，worker 直接崩。
    storage_path = storage.save(tenant_id, doc_id, filename, data)

    doc = document_repo.create(
        db,
        doc_id=doc_id,
        tenant_id=tenant_id,
        name=filename,
        mime=mime,
        size_bytes=len(data),
        content_hash=content_hash,
        storage_path=storage_path,
    )

    cache.cache_delete_prefix(CACHE_PREFIX)

    queued = await _enqueue(doc.id, doc.tenant_id)
    return doc, False, queued


async def _enqueue(document_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
    """投递解析任务（必须把 tenant_id 一起传，worker 才能设置 RLS 上下文）。"""
    return await task_queue.enqueue_parse(str(document_id), str(tenant_id))


def list_documents(
    db: Session, *, tenant_id: uuid.UUID, use_cache: bool = True
) -> tuple[list[dict], bool]:
    settings = get_settings()
    key = _cache_key(tenant_id)

    if use_cache:
        cached = cache.cache_get(key)
        if cached is not None:
            return cached, True

    docs = document_repo.list_by_tenant(db, tenant_id)
    payload = [
        {
            "id": str(d.id),
            "name": d.name,
            "mime": d.mime,
            "size_bytes": d.size_bytes,
            "status": d.status,
            "progress": d.progress,
            "chunk_count": d.chunk_count,
            "error_reason": d.error_reason,
            "created_at": d.created_at.isoformat(),
        }
        for d in docs
    ]
    cache.cache_set(key, payload, settings.doc_list_cache_ttl)
    return payload, False


def get_document(db: Session, *, tenant_id: uuid.UUID, doc_id: uuid.UUID) -> Document:
    doc = document_repo.get(db, doc_id)
    # RLS 已经在数据库层挡了一层；这里再校验一次是纵深防御
    if doc is None or doc.tenant_id != tenant_id:
        raise AppError(ErrorCode.NOT_FOUND, "文档不存在", http_status=404)
    return doc

def list_chunks(
    db: Session, *, tenant_id: uuid.UUID, doc_id: uuid.UUID, limit: int = 200
) -> list[dict]:
    """分块预览：按 order_index 返回，父块与子块都带上（子块标出 parent_id）。"""
    from sqlalchemy import select

    from app.models.chunk import Chunk

    rows = list(
        db.scalars(
            select(Chunk)
            .where(Chunk.doc_id == doc_id, Chunk.tenant_id == tenant_id)
            .order_by(Chunk.order_index)
            .limit(limit)
        )
    )
    return [
        {
            "id": str(c.id),
            "parent_id": str(c.parent_id) if c.parent_id else None,
            "content": c.content,
            "page": c.page,
            "section_path": c.section_path,
            "token_count": c.token_count,
            "content_type": c.content_type,
            "order_index": c.order_index,
        }
        for c in rows
    ]