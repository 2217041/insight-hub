"""W4 索引实验：同一条查询，分别在没有索引 / 有索引时测量执行时间。

做法：
1. 先清掉目标表上所有非主键索引 → 同一查询跑 3 次取中位数；
2. 建回索引 → 再跑 3 次；
3. 输出 markdown 表格到 scripts/bench-result.md。

为什么不用 `SET enable_indexscan=off` 模拟"没索引"：
那样只是让优化器不走索引，执行计划仍受统计信息影响，测出来和真实"没有这个索引"不一样。
**宁愿真的删了再加回来。**

用法：
    cd apps/api
    .\\.venv\\Scripts\\python.exe -m scripts.bench_indexes
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from textwrap import dedent

import psycopg

from app.core.config import get_settings

DSN = get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")


def _plan_label(plan: dict) -> str:
    """把执行计划压成一句人话。

    LIMIT 往往是根节点，真正干活的在下面，所以要往下一层看。
    """
    node = plan["Node Type"]
    children = plan.get("Plans", [])
    if node in ("Limit", "Aggregate", "Sort") and children:
        child = children[0]["Node Type"]
        return f"{node}({child})"
    return node


def measure(conn, sql: str, repeat: int = 3) -> tuple[float, str]:
    """返回 (中位执行时间 ms, 执行计划简述)。"""
    times: list[float] = []
    plan_type = ""
    for _ in range(repeat):
        with conn.cursor() as cur:
            cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}")
            raw = cur.fetchone()[0]
            data = json.loads(raw) if isinstance(raw, str) else raw
            plan = data[0]
            times.append(float(plan["Execution Time"]))
            plan_type = _plan_label(plan["Plan"])
    return statistics.median(times), plan_type


def pick_ids(conn) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM tenant ORDER BY name LIMIT 1")
        tenant = cur.fetchone()[0]
        cur.execute("SELECT id FROM conversation ORDER BY title LIMIT 1")
        conv = cur.fetchone()[0]
        cur.execute(
            "SELECT id FROM document WHERE tenant_id = %s AND status = 'ready' LIMIT 1",
            (tenant,),
        )
        doc = cur.fetchone()[0]
        cur.execute(
            "SELECT created_at FROM message WHERE conversation_id = %s "
            "ORDER BY created_at DESC OFFSET 5000 LIMIT 1",
            (conv,),
        )
        cursor_ts = cur.fetchone()[0]
    return {
        "tenant": str(tenant),
        "conv": str(conv),
        "doc": str(doc),
        "ts": cursor_ts.isoformat(),
    }


EXPERIMENTS: list[dict] = [
    {
        "title": "会话内最新 20 条",
        "why": "对话页一打开就拉最近消息，最高频查询",
        "table": "message",
        "creates": [
            "CREATE INDEX ix_message_conv_created ON message (conversation_id, created_at)",
            "CREATE INDEX ix_message_tenant_created ON message (tenant_id, created_at)",
            "CREATE INDEX ix_message_tenant_id ON message (tenant_id)",
        ],
        "sql": "SELECT * FROM message WHERE conversation_id = '{conv}' ORDER BY created_at DESC LIMIT 20",
    },
    {
        "title": "深分页 OFFSET 100000",
        "why": "用户翻到很后面的历史消息",
        "table": "message",
        "creates": [
            "CREATE INDEX ix_message_conv_created ON message (conversation_id, created_at)",
        ],
        "sql": "SELECT * FROM message WHERE conversation_id = '{conv}' ORDER BY created_at DESC OFFSET 100000 LIMIT 20",
    },
    {
        "title": "Keyset 分页（游标）",
        "why": "用 created_at 游标代替 OFFSET，深翻页不变慢",
        "table": "message",
        "creates": [
            "CREATE INDEX ix_message_conv_created ON message (conversation_id, created_at)",
        ],
        "sql": "SELECT * FROM message WHERE conversation_id = '{conv}' AND created_at < '{ts}' ORDER BY created_at DESC LIMIT 20",
    },
    {
        "title": "按租户 + 状态查文档",
        "why": "入库队列要捞 pending/parsing 的文档",
        "table": "document",
        "creates": [
            "CREATE INDEX ix_document_tenant_status ON document (tenant_id, status)",
            "CREATE INDEX ix_document_tenant_id ON document (tenant_id)",
            "ALTER TABLE document ADD CONSTRAINT uq_document_tenant_hash UNIQUE (tenant_id, content_hash)",
        ],
        "sql": "SELECT * FROM document WHERE tenant_id = '{tenant}' AND status = 'ready'",
    },
    {
        "title": "内容哈希查重（幂等上传）",
        "why": "同一文件重复上传时快速判重",
        "table": "document",
        "creates": [
            "ALTER TABLE document ADD CONSTRAINT uq_document_tenant_hash UNIQUE (tenant_id, content_hash)",
        ],
        "sql": "SELECT id FROM document WHERE tenant_id = '{tenant}' AND content_hash = md5('doc-5')",
    },
    {
        "title": "按文档查块（回填父块）",
        "why": "检索命中后要捞出同文档的块",
        "table": "chunk",
        "creates": [
            "CREATE INDEX ix_chunk_doc ON chunk (doc_id)",
            "CREATE INDEX ix_chunk_tenant_doc ON chunk (tenant_id, doc_id)",
            "CREATE INDEX ix_chunk_tenant_id ON chunk (tenant_id)",
        ],
        "sql": "SELECT * FROM chunk WHERE doc_id = '{doc}'",
    },
    {
        "title": "最近 7 天消息数",
        "why": "运营看板 / 成本统计",
        "table": "message",
        "creates": [
            "CREATE INDEX ix_message_tenant_created ON message (tenant_id, created_at)",
            "CREATE INDEX ix_message_conv_created ON message (conversation_id, created_at)",
            "CREATE INDEX ix_message_tenant_id ON message (tenant_id)",
        ],
        "sql": "SELECT count(*) FROM message WHERE created_at > now() - interval '7 days'",
    },
    {
        "title": "按角色统计（低选择性）",
        "why": "反例：只有 2 种取值，索引帮不上忙",
        "table": "message",
        "creates": [
            "CREATE INDEX ix_message_tenant_id ON message (tenant_id)",
        ],
        "sql": "SELECT count(*) FROM message WHERE role = 'assistant'",
    },
    {
        "title": "不带条件的排序分页",
        "why": "全站最新消息，看复合索引能否直接用上",
        "table": "message",
        "creates": [
            "CREATE INDEX ix_message_tenant_created ON message (tenant_id, created_at)",
        ],
        "sql": "SELECT * FROM message ORDER BY created_at DESC LIMIT 20",
    },
    {
        "title": "关键词模糊搜索",
        "why": "反例：LIKE '%x%' 用不上 B-tree，需要 GIN/全文索引（W11）",
        "table": None,
        "creates": [],
        "sql": "SELECT count(*) FROM message WHERE content LIKE '%报销标准%'",
    },
]


def drop_all_indexes(conn, table: str) -> list[str]:
    """删掉该表除主键外的所有索引与唯一约束。

    **坑**：`UNIQUE` 约束背后会自动建一个同名索引，直接 `DROP INDEX` 会报
    "cannot drop index ... because constraint ... requires it"。
    必须先删约束。重建时也要用 `ADD CONSTRAINT`，否则 schema 会和迁移文件不一致。
    """
    dropped: list[str] = []
    with conn.cursor() as cur:
        # 1) 先处理约束（唯一约束、外键不动）
        cur.execute(
            "SELECT conname, contype FROM pg_constraint "
            "WHERE conrelid = %s::regclass AND contype = 'u'",
            (table,),
        )
        for conname, _ in cur.fetchall():
            cur.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {conname}")
            dropped.append(f"constraint:{conname}")

        # 2) 再删普通索引
        cur.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = %s AND indexname NOT LIKE %s",
            (table, "%_pkey"),
        )
        for (idx,) in cur.fetchall():
            cur.execute(f"DROP INDEX IF EXISTS {idx}")
            dropped.append(f"index:{idx}")
    return dropped


def main() -> int:
    conn = psycopg.connect(DSN, autocommit=True)
    ids = pick_ids(conn)
    rows = []

    for i, exp in enumerate(EXPERIMENTS, 1):
        sql = dedent(exp["sql"]).format(**ids).strip()

        if exp["table"]:
            drop_all_indexes(conn, exp["table"])

        before, before_plan = measure(conn, sql)

        if exp["table"]:
            # 建回该表应有的全部索引（不是只建本次涉及的那个，
            # 否则后面的实验会跑在"缺索引"的状态上）
            for ddl in exp["creates"]:
                with conn.cursor() as cur:
                    cur.execute(ddl)

        after, after_plan = measure(conn, sql)
        speedup = before / after if after else 0.0
        rows.append((exp["title"], exp["why"], before, after, speedup, before_plan, after_plan))
        print(f"[{i:02d}] {exp['title']}: {before:.1f} -> {after:.1f} ms ({before_plan} -> {after_plan})")

    def fmt(v: float) -> str:
        return f"{v:.3f} ms" if v < 10 else f"{v:.1f} ms"

    def fmt_speed(v: float) -> str:
        return "—" if v < 1.05 else f"{v:.1f}×"

    lines = ["| # | 场景 | 没有索引 | 加索引后 | 提升 | 执行计划变化 |", "|---|---|---|---|---|---|"]
    for i, (title, _why, before, after, speedup, bp, ap) in enumerate(rows, 1):
        lines.append(
            f"| {i} | {title} | {fmt(before)} | {fmt(after)} | {fmt_speed(speedup)} | {bp} → {ap} |"
        )

    detail = ["", "## 明细", ""]
    for i, (title, why, before, after, speedup, bp, ap) in enumerate(rows, 1):
        detail.append(f"- **{i}. {title}**（{why}）：{fmt(before)} / {bp} → {fmt(after)} / {ap}")

    out = Path(__file__).parent / "bench-result.md"
    out.write_text("\n".join(lines) + "\n" + "\n".join(detail) + "\n", encoding="utf-8")
    print(f"RESULT_FILE={out}")

    # 最后确认索引恢复完整（基准测试会删/建索引，必须恢复到迁移定义的状态）
    ensure_schema(conn)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT tablename, count(*) FROM pg_indexes "
            "WHERE schemaname='public' AND indexname NOT LIKE '%_pkey' "
            "GROUP BY tablename ORDER BY tablename"
        )
        restored = cur.fetchall()
    print("RESTORED_INDEXES=" + str(restored))

    conn.close()
    return 0


CANONICAL_DDL = [
    "CREATE INDEX IF NOT EXISTS ix_users_tenant_id ON users (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_users_tenant_created ON users (tenant_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_users_email ON users (email)",
    "CREATE INDEX IF NOT EXISTS ix_document_tenant_id ON document (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_document_tenant_status ON document (tenant_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_chunk_tenant_id ON chunk (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_chunk_doc ON chunk (doc_id)",
    "CREATE INDEX IF NOT EXISTS ix_chunk_tenant_doc ON chunk (tenant_id, doc_id)",
    "CREATE INDEX IF NOT EXISTS ix_conversation_tenant_id ON conversation (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_conversation_user_id ON conversation (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_conv_tenant_updated ON conversation (tenant_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS ix_message_tenant_id ON message (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_message_conv_created ON message (conversation_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_message_tenant_created ON message (tenant_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_agent_run_tenant_id ON agent_run (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_agent_run_tenant_created ON agent_run (tenant_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_eval_run_tenant_id ON eval_run (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_eval_run_tenant_created ON eval_run (tenant_id, created_at)",
    """
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_document_tenant_hash') THEN
        ALTER TABLE document ADD CONSTRAINT uq_document_tenant_hash
          UNIQUE (tenant_id, content_hash);
      END IF;
    END $$;
    """,
]


def ensure_schema(conn) -> None:
    """把索引/约束恢复到与 Alembic 迁移一致的状态。幂等，可反复调用。"""
    with conn.cursor() as cur:
        for ddl in CANONICAL_DDL:
            cur.execute(ddl)


if __name__ == "__main__":
    sys.exit(main())