# 多租户隔离（W4）

> 目标：应用层忘了写 `WHERE tenant_id = ...` 时，数据库要兜底。

---

## 一、三种方案与取舍

| 方案 | 隔离强度 | 运维成本 | 迁移成本 | 适合 |
|---|---|---|---|---|
| 独立库 | 最高 | 每租户一套备份/监控/连接池 | 高（建库、跨库统计难） | 大客户、合规要求强 |
| 独立 schema | 高 | 中等 | 中 | 租户数不多（几十个） |
| **共享表 + tenant_id** | 靠代码 + RLS | **最低** | 低（加列即可） | 绝大多数 SaaS |

**本项目选共享表**，理由：
- 租户数会增长，独立库的运维成本线性上升；
- 单表数据量在百万级，PostgreSQL 完全撑得住；
- 用 **RLS 兜底**，把"忘记加条件"从"数据泄露"降级成"查不到数据"。

---

## 二、RLS 实现

迁移文件：`migrations/versions/b7c1e2f40a55_rls_tenant_isolation.py`

```sql
ALTER TABLE document ENABLE ROW LEVEL SECURITY;
ALTER TABLE document FORCE ROW LEVEL SECURITY;   -- 关键：owner 也要受限

CREATE POLICY tenant_isolation ON document
USING      (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
```

三个细节都是有原因的：

| 写法 | 不加会怎样 |
|---|---|
| `FORCE ROW LEVEL SECURITY` | 表 owner（我们的应用账号）**默认绕过 RLS**，策略形同虚设 |
| `current_setting(..., true)` | 第二个参数 `true` = 缺失时返回 NULL；不加会在"没设置上下文"时直接抛异常 |
| `nullif(..., '')` | 空字符串转 uuid 会报错；加上后"空值 = 没有上下文" |

**没有上下文时策略求值为 NULL → 不匹配任何行 → 返回 0 行**，而不是报错，也不是返回全部。这是安全默认。

### 为什么不给 `users` 和 `conversation` 也加

登录发生在"还不知道你是哪个租户"的时候——如果 `users` 表也强制 RLS，
登录查询会返回 0 行，用户永远登不进来。

`users`、`tenant` 靠应用层保证；`conversation` 暂未加（W5 会补）。
这是一个明确的取舍，不是漏了。

---

## 三、应用侧怎么用

每个请求开始时（事务内）：

```python
from sqlalchemy import text

def set_tenant(db: Session, tenant_id: str) -> None:
    # SET LOCAL 的作用域是当前事务，连接池复用不会串租户
    db.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(tenant_id)})
```

**必须用 `SET LOCAL` 而不是 `SET`**：
`SET` 是会话级的，连接被放回池子后下一个请求会继承上一个租户的上下文——**这是最危险的串租户 bug**。

对应的封装（W5 接入时使用）：

```python
@contextmanager
def tenant_scope(db: Session, tenant_id: str):
    set_tenant(db, tenant_id)
    try:
        yield db
    finally:
        db.execute(text("RESET app.tenant_id"))
```

---

## 四、验证结果（2026-11-09 实测）

脚本：`D:\aistudy\sql\verify-rls.sql`

| 步骤 | 操作 | 结果 |
|---|---|---|
| 1 | 不设置 `app.tenant_id` | document/chunk/message 全部 **0 行** ✅ |
| 2 | 设置成租户 A | document **200** 行、message **200,100** 行 ✅ |
| 3 | 切到租户 B | document **200** 行、message **0** 行 ✅（消息都属于 A） |
| 4 | 用 A 的上下文写入 B 的 `tenant_id` | **ERROR: new row violates row-level security policy** ✅ |
| 5 | 把上下文设为空字符串 | 返回 **0 行**，不报错 ✅ |

第 4 步是重点：**即使代码写错了 tenant_id，数据库也会拒绝写入**。
第 5 步是这次修的一个健壮性问题——最初用 `current_setting(...)::uuid` 直接转，空串会抛错。

---

## 五、注意事项

| 事项 | 说明 |
|---|---|
| 超级用户和后端进程仍可绕过 | RLS 不是绝对安全，运维账号要单独管控 |
| 索引要考虑 tenant_id | 策略会附加过滤条件，`(tenant_id, ...)` 复合索引才用得上 |
| 性能影响很小 | 策略条件是简单等值比较，走索引，实测无可见开销 |
| 迁移/备份要绕过 | 运维脚本用 superuser 或 `BYPASSRLS` 角色 |
| 测试要覆盖"忘加条件" | 断言"没设上下文时返回 0 行"，否则等于没测 |

---

## 六、面试怎么说

> "我们多租户用共享表 + `tenant_id`，DB 层加 RLS 兜底：`ENABLE` + `FORCE`（owner 也要受限），
> 策略用 `nullif(current_setting('app.tenant_id', true), '')::uuid`。
> 应用侧每个事务 `SET LOCAL app.tenant_id`，避免连接池串租户。
> 这样即使某条查询忘了带 tenant_id，最坏结果是查不到数据，而不是把别人的数据返回。"

**加分点**：能说出"`FORCE` 是必须的，否则 owner 绕过"——这细节说明真的配过。