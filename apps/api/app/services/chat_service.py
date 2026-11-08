"""对话业务：占位回答 + SSE 帧编码。

W9 会把 `mock_answer` 换成真实模型调用，路由层一行都不用改。
"""

from __future__ import annotations

import json


def sse(payload: dict) -> str:
    """把一条数据编码成 SSE 帧。结尾必须是两个换行，否则浏览器收不到完整事件。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def mock_answer(question: str) -> str:
    """W3 阶段的占位回复，故意包含 Markdown 结构以验证前端渲染。"""
    return (
        f"你问的是：**{question}**\n\n"
        "这是 W3 的占位回答（W2 的接口已按分层重构，行为不变）。\n\n"
        "## 这次重构做了什么\n\n"
        "1. `main.py` 从 204 行缩到只做装配；\n"
        "2. 业务逻辑移到 `app/services/`，数据访问移到 `app/repos/`；\n"
        "3. 新增统一错误码与 `request_id`，前端只写一次错误处理。\n\n"
        "> 分层不是形式主义：路由层改不动业务，业务层不碰 HTTP，才好在中间加缓存、埋点、限流。\n\n"
        "```python\n"
        "def login(payload, db=Depends(get_db)):\n"
        "    return auth_service.login(db, email=payload.email, password=payload.password)\n"
        "```\n\n"
        "W9 会把这里的 `mock_answer` 换成真实模型调用，其余代码不用动。"
    )