"""文档接口的请求/响应模型。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    mime: str
    size_bytes: int
    status: str
    progress: int
    chunk_count: int
    error_reason: str | None = None
    created_at: datetime


class UploadResponse(BaseModel):
    document: DocumentResponse
    """true 表示命中了幂等键，没有重复解析"""
    deduplicated: bool = False
    """是否真的投递了后台任务（命中幂等时为 false）"""
    queued: bool = False


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    """是否来自缓存，前端/调试时可观察缓存是否生效"""
    cached: bool = False