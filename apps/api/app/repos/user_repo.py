"""用户数据访问层：只碰数据库，不写业务判断。

这一层唯一的职责是"怎么取/存"，不回答"该不该"。
比如"邮箱是否重复"属于业务判断，放 service。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def get_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def create(db: Session, *, email: str, name: str, password_hash: str) -> User:
    user = User(email=email.lower(), name=name, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user