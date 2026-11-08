"""统一错误码与异常处理器。

设计目标：无论哪种错误，前端拿到的响应体形状都一样：

    {"code": "AUTH_401", "message": "邮箱或密码错误", "request_id": "...", "detail": null}

为什么要统一：
1. 前端只写一次错误处理逻辑，不用为每个接口写 if；
2. request_id 能直接把线上报错定位到日志；
3. HTTP 状态码粒度太粗（401 里还分"没带 token"和"token 过期"），业务需要更细的码。
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_request_id

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    OK = "OK"
    VALIDATION = "VALIDATION_422"
    UNAUTHORIZED = "AUTH_401"
    FORBIDDEN = "AUTH_403"
    NOT_FOUND = "NOT_FOUND_404"
    CONFLICT = "CONFLICT_409"
    RATE_LIMITED = "RATE_429"
    INTERNAL = "INTERNAL_500"


class AppError(Exception):
    """业务异常。service 层只管抛，由全局处理器翻译成标准响应。"""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        http_status: int = 400,
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.detail = detail


def error_body(code: ErrorCode, message: str, detail: Any = None) -> dict:
    return {
        "code": str(code),
        "message": message,
        "request_id": get_request_id(),
        "detail": detail,
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        # 业务异常是"预期内"的，用 info 级别，不要刷 error 日志
        logger.info("app_error code=%s message=%s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.http_status,
            content=error_body(exc.code, exc.message, exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 把 Pydantic 的错误压平，只留人能看懂的字段
        detail = [
            {"field": ".".join(str(p) for p in e.get("loc", [])), "msg": e.get("msg")}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_body(ErrorCode.VALIDATION, "参数校验失败", detail),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # 未捕获异常：日志要带堆栈，但响应体不能暴露内部细节
        logger.exception("unhandled_exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content=error_body(ErrorCode.INTERNAL, "服务器内部错误，请稍后重试"),
        )