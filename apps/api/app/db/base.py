"""ORM 基类。

W3 阶段用 `Base.metadata.create_all()` 建表（简单）；
W4 会换成 Alembic 迁移，那时删掉 create_all 调用即可。
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass