"""租户：多租户的隔离单位。

隔离方案选择：**共享表 + tenant_id + RLS**
- 独立库/独立 schema：隔离最彻底，但运维成本随租户数线性增长；
- 共享表：成本最低、迁移简单，代价是所有查询都必须带 tenant_id。

我们选共享表，并用 **行级安全（RLS）** 在数据库层兜底——
应用层忘了加条件时，数据库仍然不会把别人的数据给你。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Tenant(Base):
    __tablename__ = "tenant"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100))
    plan: Mapped[str] = mapped_column(String(20), default="free")
    # 月度 token 配额；0 表示不限（开发期）
    quota_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )