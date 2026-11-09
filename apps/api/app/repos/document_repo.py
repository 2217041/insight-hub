"""文档数据访问层。"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document


def get(db: Session, doc_id: uuid.UUID) -> Document | None:
    return db.get(Document, doc_id)


def get_by_hash(db: Session, tenant_id: uuid.UUID, content_hash: str) -> Document | None:
    return db.scalar(
        select(Document).where(
            Document.tenant_id == tenant_id,
            Document.content_hash == content_hash,
        )
    )


def list_by_tenant(db: Session, tenant_id: uuid.UUID, limit: int = 50) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.tenant_id == tenant_id, Document.deleted_at.is_(None))
            .order_by(Document.created_at.desc())
            .limit(limit)
        )
    )


def create(
    db: Session,
    *,
    doc_id: uuid.UUID,
    tenant_id: uuid.UUID,
    name: str,
    mime: str,
    size_bytes: int,
    content_hash: str,
    storage_path: str,
    status: str = "pending",
) -> Document:
    """id 由调用方生成：磁盘文件名用的就是它，两边必须一致。"""
    doc = Document(
        id=doc_id,
        tenant_id=tenant_id,
        name=name,
        mime=mime,
        size_bytes=size_bytes,
        content_hash=content_hash,
        storage_path=storage_path,
        status=status,
        acl_tags=[],
    )
    db.add(doc)
    # 只 flush 不 commit：commit 会结束事务，导致 SET LOCAL 的租户上下文失效
    db.flush()
    db.refresh(doc)
    return doc


def update_state(
    db: Session,
    doc_id: uuid.UUID,
    *,
    status: str | None = None,
    progress: int | None = None,
    chunk_count: int | None = None,
    error_reason: str | None = None,
) -> None:
    doc = db.get(Document, doc_id)
    if doc is None:
        return
    if status is not None:
        doc.status = status
    if progress is not None:
        doc.progress = progress
    if chunk_count is not None:
        doc.chunk_count = chunk_count
    if error_reason is not None:
        doc.error_reason = error_reason
    db.flush()


def count_by_tenant(db: Session, tenant_id: uuid.UUID) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.tenant_id == tenant_id, Document.deleted_at.is_(None))
    ) or 0