"""多租户行级安全（RLS）

背景：所有租户共用同一批表，靠 `tenant_id` 区分。
应用层忘记写 `WHERE tenant_id = ...` 时，数据库必须兜底——这就是 RLS 的作用。

关键点：
1. `ENABLE` + **`FORCE`** ROW LEVEL SECURITY：
   表 owner 默认会绕过 RLS，必须 FORCE 才能连 owner 一起约束。
2. 用 `current_setting('app.tenant_id', true)`（第二个参数 true = 缺失时返回 NULL 而不是报错），
   这样"没设置租户上下文"时查询返回 0 行，而不是抛异常。
3. `nullif(..., '')` 把空字符串也当成"没有上下文"，否则 `'::uuid` 会直接报错。
   应用侧在事务里执行 `SET LOCAL app.tenant_id = '<uuid>'`；
   `SET LOCAL` 的作用域是当前事务，连接池复用时不会串租户。

Revision ID: b7c1e2f40a55
Revises: a24e454ab98f
"""

from alembic import op

revision = "b7c1e2f40a55"
down_revision = "a24e454ab98f"
branch_labels = None
depends_on = None

TENANT_TABLES = ["document", "chunk", "conversation", "message", "agent_run", "eval_run"]


def upgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
            """
        )

    # 会话与用户表也属于租户，但登录发生在"还不知道租户"的时候，
    # 所以这两张表只在应用层保证，DB 层不强制（否则登录流程会查不到用户）。


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")