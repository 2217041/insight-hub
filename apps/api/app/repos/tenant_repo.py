"""租户数据访问层。"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.tenant import Tenant


def create(db: Session, *, name: str, plan: str = "free") -> Tenant:
    tenant = Tenant(name=name, plan=plan)
    db.add(tenant)
    db.flush()  # 拿到 id，但不在此时提交（和用户的创建在同一个事务里）
    return tenant


def get_by_id(db: Session, tenant_id: uuid.UUID) -> Tenant | None:
    return db.get(Tenant, tenant_id)