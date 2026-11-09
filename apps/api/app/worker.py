"""arq 后台 worker：文档解析。

启动：
    cd apps/api
    .\\.venv\\Scripts\\python.exe -m arq app.worker.WorkerSettings

设计要点：
1. **每个步骤一个短事务**（`tenant_session`）：`SET LOCAL app.tenant_id` 随事务结束失效，
   长事务中间 commit 会丢掉租户上下文，后续写入被 RLS 拒绝。
2. **幂等**：重跑同一个任务时先删掉旧 chunk，不会产生重复数据。
3. **失败可诊断**：把原因写进 `error_reason`，而不是只打日志。
"""

from __future__ import annotations

import logging
import uuid

from arq.connections import RedisSettings
from sqlalchemy import delete, insert

from app.core.config import get_settings
from app.db.session import tenant_session
from app.models.chunk import Chunk
from app.repos import document_repo
from app.services import ingest, storage

logger = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    """粗估 token：中文约 1 字 1 token，英文约 4 字符 1 token。
    这里按 2 字符 ≈ 1 token 折中，W10 会用真正的 tokenizer。
    """
    return max(1, len(text) // 2)


async def parse_document(ctx: dict, document_id: str, tenant_id: str) -> str:
    doc_uuid = uuid.UUID(document_id)
    tenant_uuid = uuid.UUID(tenant_id)

    # ---- 1. 标记解析中 ----
    with tenant_session(tenant_uuid) as db:
        doc = document_repo.get(db, doc_uuid)
        if doc is None:
            logger.warning("doc_missing id=%s", document_id)
            return "missing"
        if doc.status == "ready":
            return "already_ready"  # 幂等：重复投递不重做
        filename, path = doc.name, doc.storage_path
        document_repo.update_state(db, doc_uuid, status="parsing", progress=10)

    # ---- 2. 读文件 + 抽文本（这一段的异常要落到 error_reason）----
    try:
        raw = storage.read(path)
        text, note = ingest.extract_text(raw, filename)
        if not text.strip():
            raise ValueError("文件里没有可提取的文本")
    except Exception as exc:  # noqa: BLE001
        logger.warning("extract_failed id=%s err=%s", document_id, exc)
        with tenant_session(tenant_uuid) as db:
            document_repo.update_state(
                db, doc_uuid, status="failed", progress=0, error_reason=str(exc)[:500]
            )
        return "failed"

    # ---- 3. 分块 ----
    with tenant_session(tenant_uuid) as db:
        document_repo.update_state(db, doc_uuid, status="chunking", progress=60)

    chunks = ingest.split_chunks(text)

    # ---- 4. 落块（先删旧的，保证重跑幂等）----
    with tenant_session(tenant_uuid) as db:
        db.execute(delete(Chunk).where(Chunk.doc_id == doc_uuid))
        if chunks:
            db.execute(
                insert(Chunk),
                [
                    {
                        "id": uuid.uuid4(),
                        "tenant_id": tenant_uuid,
                        "doc_id": doc_uuid,
                        "parent_id": None,
                        "content": c.content,
                        "content_type": "text",
                        "page": c.page,
                        "section_path": c.section_path,
                        "token_count": _estimate_tokens(c.content),
                    }
                    for c in chunks
                ],
            )
        document_repo.update_state(
            db,
            doc_uuid,
            status="ready",
            progress=100,
            chunk_count=len(chunks),
            error_reason="",
        )

    logger.info("parsed doc=%s chunks=%d", document_id, len(chunks))
    return f"ok:{len(chunks)}"


class WorkerSettings:
    functions = [parse_document]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    # 单个任务最长 5 分钟（大文件解析），超时会被标记失败
    job_timeout = 300
    max_tries = 3
    keep_result = 3600
    health_check_interval = 30