"""请求级日志上下文：给每个请求一个 request_id，串起日志与响应体。"""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_request_id: ContextVar[str] = ContextVar("request_id", default="-")

logger = logging.getLogger("insight.request")


def get_request_id() -> str:
    return _request_id.get()


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-5s [%(request_id)s] %(name)s | %(message)s",
    )
    # 让每条日志自动带上 request_id，不用手动传
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):  # type: ignore[no-untyped-def]
        record = old_factory(*args, **kwargs)
        record.request_id = _request_id.get()
        return record

    logging.setLogRecordFactory(record_factory)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """为每个请求生成 request_id，写进响应头，并在日志里输出耗时。

    为什么会话里能查到：前端报错时把 request_id 抄给后端，后端一搜就知道是哪一次请求。
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        token = _request_id.set(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # 注意：异常路径**不要** reset 上下文。
            # 全局异常处理器在中间件之外运行，reset 了它就拿不到 request_id，
            # 错误体里会变成 "-"，线上根本无法定位。
            logger.exception("request_failed %s %s", request.method, request.url.path)
            raise
        _request_id.reset(token)

        cost_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-Id"] = rid
        logger.info(
            "%s %s -> %s  %.0fms",
            request.method,
            request.url.path,
            response.status_code,
            cost_ms,
        )
        return response