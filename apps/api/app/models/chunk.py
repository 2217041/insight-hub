"""文档块：RAG 的检索单位。

几个关键决策：

1. **父子块**：子块（256 token）用于检索，父块（1024 token）用于生成上下文。
   `parent_id` 指回父块，检索命中子块后按 parent_id 回填父块内容。

2. **embedding 维度固定 1024**（bge-m3）。改维度意味着全量重算，
   所以建表时就定死，并写进文档。

3. **tsv（tsvector）**：为 W11 的混合检索准备。中文 PostgreSQL 没有内置分词，
   W11 会用 2-gram 方案填充这个字段，这里先把列和 GIN 索引建好。

4. **page / section_path**：引用溯源的关键。没有它们，"点击跳转原文"做不了。
   这是最常见的返工点——建表时忘了，做完 RAG 才发现要重来。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.db.base import Base

EMBEDDING_DIM = 1024


class Chunk(Base):
    __tablename__ = "chunk"
    __table_args__ = (
        Index("ix_chunk_doc", "doc_id"),
        Index("ix_chunk_tenant_doc", "tenant_id", "doc_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), index=True
    )
    doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="CASCADE")
    )
    # 父块：子块指向父块；父块自身为 NULL
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunk.id", ondelete="CASCADE"), nullable=True
    )

    content: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(20), default="text")
    page: Mapped[int] = mapped_column(Integer, default=0)
    section_path: Mapped[str] = mapped_column(String(500), default="")
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    # 同一文档内的顺序：父块与子块都参与排序，W12 组装上下文时按它拼
    order_index: Mapped[int] = mapped_column(Integer, default=0, index=True)

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )
    tsv: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )