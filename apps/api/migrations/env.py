"""Alembic 运行环境。

三件事：
1. 让 alembic 能 import 到 `app` 包（sys.path 补上项目根）；
2. 数据库连接串从 app 的配置读，**不写死在 alembic.ini 里**（避免两处不一致）；
3. 给 pgvector 的 Vector 类型加渲染器，否则 autogenerate 生成不出 `Vector(1024)`。
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# 让 `import app.*` 生效（alembic 从 apps/api 目录运行）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
import app.models  # noqa: F401,E402  必须 import，否则 metadata 里没有表

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 连接串只有一个来源：app 的配置（读 .env / 环境变量）
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def render_item(type_, obj, autogen_context):  # type: ignore[no-untyped-def]
    """把 pgvector 的类型渲染成 `pgvector.sqlalchemy.Vector(1024)`。

    autogenerate 默认不认识第三方类型，会写成类型名导致迁移失败。
    """
    if type_ == "type" and obj.__class__.__module__.startswith("pgvector"):
        autogen_context.imports.add("import pgvector.sqlalchemy")
        return f"pgvector.sqlalchemy.Vector({getattr(obj, 'dim', None)})"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_item=render_item,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()