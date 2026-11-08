"""Insight Hub API —— 应用装配入口。

这个文件只做四件事：
1. 创建 app、配置日志与中间件；
2. 注册异常处理器；
3. 注册路由；
4. 启动时建表（W4 换成 Alembic 迁移）。

**这里不应该出现任何业务逻辑。** 如果你发现自己在 main.py 里写 if，
说明该往 service 层挪了。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import RequestContextMiddleware, configure_logging
from app.db.base import Base
from app.db.session import engine
from app.routers import auth, chat, health

# 必须在建表前 import，否则 Base.metadata 里没有这些表
from app.models import user as _user_model  # noqa: F401

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    # W3 临时方案：直接建表。W4 引入 Alembic 后删掉这两行。
    Base.metadata.create_all(bind=engine)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="多租户企业知识库 + AI Agent 工作台",
        lifespan=lifespan,
    )

    # 顺序有讲究：先 request_id，再 CORS，保证错误响应也带 X-Request-Id
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(chat.router)

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {
            "service": "insight-hub-api",
            "version": settings.app_version,
            "docs": "/docs",
        }

    return app


app = create_app()