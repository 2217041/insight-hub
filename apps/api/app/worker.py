"""arq 后台 worker：文档解析与分块。

启动：
    cd apps/api
    .\\.venv\\Scripts\\python.exe -m arq app.worker.WorkerSettings

W10 的变化：
- 支持 PDF / DOCX（`ingest.extract_blocks`）
- 产出**父子块**：父块用于生成上下文，子块用于检索（`parent_id` 关联）
- `chunk_count` 记的是**子块数**（真正的检索单元）
- 页面、章节路径随块落库，供 W12 引用溯源

依然保持的两条：
1. **每步一个短事务**（`tenant_session`）：`SET LOCAL` 随事务结束失效，长事务中间 commit 会丢租户上下文；
2. **幂等**：重跑先删旧块。
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from arq.connections import RedisSettings
from sqlalchemy import delete, insert

from app.core.config import get_settings
from app.db.session import tenant_session
from app.models.chunk import Chunk
from app.repos import document_repo
from app.services import ingest, storage
from app.services.embedding import get_embedder

logger = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    """粗估 token：中文约 1 字 1 token，英文约 4 字符 1 token，按 2 字符 1 token 折中。
    W11 会接真正的 tokenizer（或直接用 embedding 模型的 tokenizer）。
    """
    return max(1, len(text) // 2)


def _mark_failed(tenant_id: uuid.UUID, doc_id: uuid.UUID, reason: str) -> None:
    with tenant_session(tenant_id) as db:
        document_repo.update_state(
            db, doc_id, status="failed", progress=0, error_reason=reason[:500]
        )


async def parse_document(ctx: dict, document_id: str, tenant_id: str) -> str:
    doc_uuid = uuid.UUID(document_id)
    tenant_uuid = uuid.UUID(tenant_id)

    # ---- 1. 取文件信息 ----
    with tenant_session(tenant_uuid) as db:
        doc = document_repo.get(db, doc_uuid)
        if doc is None:
            logger.warning("doc_missing id=%s", document_id)
            return "missing"
        if doc.status == "ready":
            return "already_ready"  # 幂等：重复投递不重做
        filename, path = doc.name, doc.storage_path
        document_repo.update_state(db, doc_uuid, status="parsing", progress=10)

    # ---- 2. 解析 ----
    try:
        raw = storage.read(path)
        blocks, note = ingest.extract_blocks(raw, filename)
        if note:
            logger.info("parse_note doc=%s note=%s", document_id, note)
    except Exception as exc:  # noqa: BLE001
        logger.warning("extract_failed id=%s err=%s", document_id, exc)
        _mark_failed(tenant_uuid, doc_uuid, str(exc))
        return "failed"

    # ---- 3. 分块（父 + 子）----
    with tenant_session(tenant_uuid) as db:
        document_repo.update_state(db, doc_uuid, status="chunking", progress=60)

    try:
        groups = ingest.build_chunks(blocks)
    except Exception as exc:  # noqa: BLE001
        logger.exception("chunk_failed id=%s", document_id)
        _mark_failed(tenant_uuid, doc_uuid, f"分块失败：{exc}")
        return "failed"

    # ---- 4. 落块（先删旧的，保证重跑幂等）----
    rows: list[dict] = []
    child_count = 0
    order_index = 0
    for group in groups:
        parent_id = uuid.uuid4()
        rows.append(
            {
                "id": parent_id,
                "tenant_id": tenant_uuid,
                "doc_id": doc_uuid,
                "parent_id": None,
                "content": group.parent,
                "content_type": group.kind,
                "page": group.page,
                "section_path": group.section[:500],
                "token_count": _estimate_tokens(group.parent),
                "order_index": order_index,
            }
        )
        order_index += 1
        for child in group.children:
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_uuid,
                    "doc_id": doc_uuid,
                    "parent_id": parent_id,
                    "content": child,
                    "content_type": group.kind,
                    "page": group.page,
                    "section_path": group.section[:500],
                    "token_count": _estimate_tokens(child),
                    "order_index": order_index,
                }
            )
            child_count += 1
            order_index += 1

    # ---- 4.5 向量化（只对子块做，父块用于生成不需要向量）----
    child_rows = [r for r in rows if r["parent_id"] is not None]
    if child_rows:
        with tenant_session(tenant_uuid) as db:
            document_repo.update_state(db, doc_uuid, status="embedding", progress=80)
        try:
            embedder = get_embedder()
            vectors = await asyncio.to_thread(
                embedder.embed, [r["content"] for r in child_rows]
            )
            for row, vec in zip(child_rows, vectors):
                row["embedding"] = vec
        except Exception as exc:  # noqa: BLE001
            logger.exception("embed_failed id=%s", document_id)
            _mark_failed(tenant_uuid, doc_uuid, f"向量化失败：{exc}")
            return "failed"

    # ---- 5. 落块（先删旧的，保证重跑幂等）----
    with tenant_session(tenant_uuid) as db:
        db.execute(delete(Chunk).where(Chunk.doc_id == doc_uuid))
        if rows:
            # 分批插入，避免单条 SQL 参数过多
            batch = 500
            for i in range(0, len(rows), batch):
                db.execute(insert(Chunk), rows[i : i + batch])
        document_repo.update_state(
            db,
            doc_uuid,
            status="ready",
            progress=100,
            chunk_count=child_count,
            error_reason="",
        )

    logger.info(
        "parsed doc=%s parents=%d children=%d", document_id, len(groups), child_count
    )
    return f"ok:{child_count}"


class WorkerSettings:
    functions = [parse_document]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    job_timeout = 300
    max_tries = 2
    keep_result = 3600
    health_check_interval = 30

    # **并发必须是 1**：解析 + 向量化都是 CPU/内存密集型。
    # 实测把 60 个文档一次性投递、默认并发 10 时，ONNX 模型被多线程同时跑，
    # 1.7 GB 内存的机器直接 swap 抖动到 SSH 都连不上。
    # 串行处理虽然慢一点，但稳定——"慢"比"卡死"好。
    max_jobs = 1