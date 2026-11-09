"""文档：上传的原始文件及其解析状态。

设计要点：
1. `content_hash` + 唯一约束 → 同一租户重复上传同一文件不会产生两条记录（幂等）；
2. `status` 用字符串而不是枚举类型（PG enum 改起来要迁移，字符串+应用层校验更灵活）；
3. `deleted_at` 软删除：向量块可以保留一段时间，误删可恢复；
4. `acl_tags` 用 JSONB：权限标签可能随业务变化，不适合拆成关联表；
5. **W5 新增**：`progress` / `chunk_count` / `storage_path`，
   前端靠 progress 画进度条，worker 靠 storage_path 找到原文件。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Document(Base):
    __tablename__ = "document"
    __table_args__ = (
        # 幂等键：同租户下，内容哈希唯一
        UniqueConstraint("tenant_id", "content_hash", name="uq_document_tenant_hash"),
        # 队列查询：按租户 + 状态捞待处理任务
        Index("ix_document_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(100), default="")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    # pending / parsing / chunking / ready / failed
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- W5 ----
    progress: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    storage_path: Mapped[str] = mapped_column(String(500), default="")

    acl_tags: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )