# 数据模型（W4）

> 8 张业务表 + Alembic 迁移。目标不是"能存下来"，而是**能支撑后面 20 周的需求**。

---

## 一、表关系

```
tenant ──┬──< users ──< conversation ──< message
         │                    │
         │                    └──< agent_run
         ├──< document ──< chunk (parent_id 自引用：父子块)
         └──< eval_run
```

| 表 | 作用 | 关键点 |
|---|---|---|
| `tenant` | 租户 | 多租户的隔离单位，配额挂这里 |
| `users` | 用户 | `tenant_id` + `role`（RBAC 基础） |
| `document` | 上传的原始文件 | `content_hash` 唯一约束做幂等 |
| `chunk` | 检索单位 | `vector(1024)` + `tsvector` + `parent_id` |
| `conversation` | 会话 | `summary` 用于多轮压缩 |
| `message` | 消息 | 全库最大表，索引决定性能 |
| `agent_run` | Agent 执行轨迹 | `steps` JSONB 存每一步 |
| `eval_run` | 评测记录 | `config`/`metrics` JSONB |

---

## 二、五个设计决策（面试会问）

### 1. 时间一律用 `timestamptz`，不用 `timestamp`

`timestamp` 不带时区，存进去的是"墙上时间"。跨时区、夏令时、容器迁移时必翻车。
`timestamptz` 存 UTC，读时按会话时区转换。

本项目实测：`created_at` 返回的是 `2026-11-09T22:12:11+08:00`，带偏移量，可直接比较。

### 2. 软删除用 `deleted_at` 而不是 `is_deleted`

| | `is_deleted` 布尔 | `deleted_at` 时间戳 |
|---|---|---|
| 知道删没删 | ✅ | ✅ |
| 知道什么时候删的 | ❌ | ✅ |
| 支持"保留 30 天" | ❌ | ✅ |
| 唯一索引要加条件 | 同样要 | 同样要 |

代价：所有查询都要带 `deleted_at IS NULL`（可以封装在 repo 层）。

### 3. `content_hash` + 唯一约束 = 幂等上传

```
UNIQUE (tenant_id, content_hash)
```

同一租户重复上传同一文件时，`INSERT ... ON CONFLICT DO NOTHING` 直接返回旧记录，
不会重复解析、重复向量化（那是真金白银的算力）。

注意唯一约束是**分租户**的：A 和 B 上传同一份文件互不影响。

### 4. 父子块（`chunk.parent_id`）

- 子块 256 token：用于**检索**（更精确）
- 父块 1024 token：用于**生成**（上下文更完整）

检索命中子块后，按 `parent_id` 回填父块内容。代价是存储翻倍，收益是"检索准 + 上下文全"。

### 5. JSONB 用在这三处

| 字段 | 为什么用 JSONB |
|---|---|
| `document.acl_tags` | 权限标签随业务变化，拆成关联表过度设计 |
| `message.citations` | 引用列表结构不固定（页码/块 id/分数） |
| `agent_run.steps` | 每一步的工具、参数、结果、耗时 |

**什么时候不该用 JSONB**：需要按其中字段做高频过滤或 JOIN 的数据，应该拆表。

---

## 三、索引清单（28 个）

| 表 | 索引 | 支撑的查询 |
|---|---|---|
| `message` | `(conversation_id, created_at)` | 会话内倒序分页（最高频） |
| `message` | `(tenant_id, created_at)` | 租户维度统计 |
| `document` | `(tenant_id, status)` | 入库队列捞任务 |
| `document` | `UNIQUE(tenant_id, content_hash)` | 幂等判重 |
| `chunk` | `(tenant_id, doc_id)` | 按文档取块 |
| `conversation` | `(tenant_id, updated_at)` | 会话列表按最近排序 |
| `users` | `(tenant_id, created_at)` | 成员列表 |

**顺序很重要**：`(tenant_id, status)` 和 `(status, tenant_id)` 不是一回事——
最左前缀决定了 tenant_id 单独查询能否用上。

详见 [slow-queries.md](./slow-queries.md) 的实测数据。

---

## 四、迁移流程

```powershell
cd apps/api

# 改完模型后生成迁移
.\.venv\Scripts\alembic.exe revision --autogenerate -m "描述"

# 一定要打开生成的文件看一遍！autogenerate 会漏东西
# 应用
.\.venv\Scripts\alembic.exe upgrade head

# 回滚一个版本
.\.venv\Scripts\alembic.exe downgrade -1
```

**验收标准**：删库 → `upgrade head` → 表结构完全重建。

**注意**：`main.py` 里已移除 `create_all`，建表只走 Alembic。
部署流程变成：`alembic upgrade head` → 启动服务。

---

## 五、踩过的坑

| 坑 | 说明 |
|---|---|
| **客户端默认值对原生 SQL 不生效** | `default=True` / `default=list` 是 SQLAlchemy 在 Python 侧填的；用 `INSERT INTO ...` 直接写会变成 NULL → 违反非空约束。要么给 `server_default`，要么 SQL 里显式写值 |
| `DROP SCHEMA public CASCADE` 连扩展一起删 | pgvector 会一起没，而普通用户没权限重建，必须用 `postgres` 超级用户 |
| `psql -c 'A; B; C;'` 是一个事务 | 最后一条失败会全部回滚，看着像"执行了"其实没有 |
| 唯一约束不能 `DROP INDEX` | 会报 `cannot drop index ... because constraint requires it`，要 `ALTER TABLE DROP CONSTRAINT` |
| autogenerate 漏表 | `app/models/__init__.py` 必须 import 每张表，否则 `Base.metadata` 里没有 |

---

## 六、当前数据规模（造数后）

| 表 | 行数 |
|---|---|
| tenant | 3 |
| users | 3 |
| document | 600 |
| chunk | 48,000 |
| conversation | 2,000 |
| message | 200,100 |

复现：`psql -f sql/seed.sql`（脚本在 `D:\aistudy\sql\`）。