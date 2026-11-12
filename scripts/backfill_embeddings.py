"""回填：把"没有向量的旧文档"重新走一遍解析+向量化。

背景：W11 之前的文档只切了块、没有 embedding，检索会把它们当成不存在。
新版本靠 SHA256 幂等，重复上传会直接返回旧记录（不会重跑），
所以需要这个脚本把状态改回 pending 并重新投递任务。

在容器内执行：
    docker cp /tmp/backfill.py ih-api:/tmp/backfill.py
    docker compose exec -T api python /tmp/backfill.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.session import SessionLocal, tenant_session
from app.repos import document_repo
from app.services import task_queue


def find_targets() -> list[tuple[str, str]]:
    """找出"有块但没向量"的文档。表开了 RLS，所以要按租户逐个查。"""
    targets: list[tuple[str, str]] = []

    with SessionLocal() as db:
        tenant_ids = [str(r[0]) for r in db.execute(text("SELECT id FROM tenant")).all()]

    for tid in tenant_ids:
        with tenant_session(tid) as db:
            rows = db.execute(
                text(
                    """
                    SELECT DISTINCT d.id, d.tenant_id
                    FROM document d
                    JOIN chunk c ON c.doc_id = d.id
                    WHERE c.embedding IS NULL
                    """
                )
            ).all()
            for doc_id, tenant_id in rows:
                # 状态改回 pending，否则 worker 会因为 already_ready 直接返回
                document_repo.update_state(db, doc_id, status="pending", progress=0)
                targets.append((str(doc_id), str(tenant_id)))

    return targets


async def main() -> None:
    targets = find_targets()
    print(f"待回填文档：{len(targets)}")
    if not targets:
        return

    # **分批投递**：一次全投会把 worker 的队列塞满，1.7 GB 的机器扛不住。
    # 每批 3 个，等队列消化完再投下一批。
    ok = 0
    BATCH = 3
    for i in range(0, len(targets), BATCH):
        batch = targets[i : i + BATCH]
        for doc_id, tenant_id in batch:
            if await task_queue.enqueue_parse(doc_id, tenant_id):
                ok += 1
                print(f"  {doc_id[:8]} 投递 ok")
        # 等这批处理完（worker 串行，单个文档通常 1–5 秒）
        await asyncio.sleep(20 * len(batch))

    print(f"已投递 {ok} 个任务")


if __name__ == "__main__":
    asyncio.run(main())