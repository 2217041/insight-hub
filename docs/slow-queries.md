# 慢查询与索引实验（W4）

> **方法**：对同一条查询，先删掉目标表上所有非主键索引测一遍，建回索引再测一遍。
> 每组跑 3 次取中位数，读的是 `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` 的 `Execution Time`。
>
> **为什么不用 `SET enable_indexscan=off` 模拟"没索引"**：那样只是让优化器不走索引，
> 执行计划仍受统计信息影响，测出来和真实"没有这个索引"不是一回事。宁愿真的删了再加回来。

- 环境：WSL2 Ubuntu 24.04 / PostgreSQL 16.15 / i5-10200H（4 核 8 线程）
- 数据：`message` 200,100 行、`chunk` 48,000 行、`document` 600 行、3 个租户
- 脚本：`apps/api/scripts/bench_indexes.py`（可重复运行，结束会自动恢复索引）

---

## 一、结果

| # | 场景 | 没有索引 | 加索引后 | 提升 | 执行计划变化 |
|---|---|---|---|---|---|
| 1 | 会话内最新 20 条 | 21.5 ms | 0.021 ms | **1025×** | Limit(Gather Merge) → Limit(Index Scan) |
| 2 | 深分页 OFFSET 100000 | 77.7 ms | 18.3 ms | 4.3× | Limit(Gather Merge) → Limit(Index Scan) |
| 3 | Keyset 分页（游标） | 21.3 ms | 0.022 ms | **967×** | Limit(Gather Merge) → Limit(Index Scan) |
| 4 | 按租户 + 状态查文档 | 0.074 ms | 0.055 ms | 1.3× | Seq Scan → Bitmap Heap Scan |
| 5 | 内容哈希查重 | 0.062 ms | 0.010 ms | 6.2× | Seq Scan → Index Scan |
| 6 | 按文档查块 | 5.283 ms | 0.072 ms | **73×** | Seq Scan → Bitmap Heap Scan |
| 7 | 最近 7 天消息数 | 27.6 ms | 14.0 ms | 2.0× | Aggregate(Gather) → Aggregate(Gather) |
| 8 | 按角色统计（2 种取值） | 18.2 ms | 17.4 ms | — | Aggregate(Gather) → Aggregate(Gather) |
| 9 | 不带条件的排序分页 | 18.5 ms | 20.4 ms | — | Limit(Gather Merge) → Limit(Gather Merge) |
| 10 | 关键词模糊搜索 `LIKE '%x%'` | 36.6 ms | 31.5 ms | — | Aggregate(Gather) → Aggregate(Gather) |

---

## 二、三类结果，三种结论

### A. 索引收益巨大的（1、3、6）

**`(conversation_id, created_at)` 是全局最重要的索引**，没有它对话页每次要扫 20 万行。

- #1 从 21.5 ms → 0.021 ms：计划从"并行全表扫 + 归并排序"变成"索引倒序扫描取前 20 条"。
- #3 Keyset 分页同样快：`created_at < 游标` 能直接定位到 B-tree 的位置。

**为什么能快 1000 倍**：查询只要 20 行，但没索引就要把所有 20 万行排一遍序。

### B. 收益有限的（2、4、7）

**#2 深分页只有 4.3 倍，而且仍然 18 ms** ——这是本实验最有价值的一条：

> OFFSET 100000 意味着数据库**必须先扫过前 10 万行再丢掉**，索引只让它扫得更快，
> 但"扫 10 万行"这件事本身没变。**OFFSET 深分页的复杂度是 O(offset)，加索引治不了根。**

对比 #3（Keyset）只要 0.022 ms——**差 800 倍，因为 Keyset 直接跳到位置**。

结论：**深分页必须改 Keyset**，不是加索引能解决的。

**#7 只有 2 倍**：`created_at > now() - 7 days` 命中了大部分行（20 万条消息是连续生成的），
扫都扫了 30 万行里的 25 万行，索引省不了多少。**选择性低时索引就是没用。**

**#4 几乎无差异**：`document` 只有 600 行，全表扫本来只要 0.07 ms。
**小表建索引没有意义**，反而占空间、拖慢写入。

### C. 加索引反而更慢的（8、9、10）

**#8 按角色统计**：`role` 只有 `user`/`assistant` 两个值，各占一半。
用索引要先扫索引再回表，比直接顺序扫还慢——优化器干脆不用它。

> **这是"索引不是越多越好"最直接的证据。** 低基数（distinct 值很少）的列不要建单列索引。

**#9 全局排序分页**：`ORDER BY created_at DESC LIMIT 20` 没有 `WHERE`，
复合索引 `(tenant_id, created_at)` 的第一列用不上，仍需全表排序。

> 想让这类查询走索引，需要建 `(created_at)` 单列索引。但**全局最近消息**是不是真需求？
> 大多数场景应该限定租户——那才是这个索引该服务的查询。

**#10 `LIKE '%关键词%'`**：前置通配符无法使用 B-tree（它只能按前缀定位）。
> 需要 GIN + `pg_trgm`，或者走全文检索——这正是 W11 混合检索要解决的问题。

---

## 三、三条可以带走的结论

1. **索引解决的是"定位"，不是"扫描量"**。
   深分页的问题在于要跳过的行数，加索引只能让跳过变快，不能让它变少。

2. **低选择性列不值得建索引**（#8）。
   判断标准：`count(distinct col) / count(*)` 太低（比如 < 5%）时，索引大概率用不上。

3. **顺序决定一切**（#9）。
   `(tenant_id, created_at)` 服务的是"某租户最近消息"；如果查询里没有 tenant_id，
   这个索引一行都用不上。**建索引前先想清楚查询长什么样。**

---

## 四、复现

```powershell
cd D:\aistudy\texun-project\repo\apps\api
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -m scripts.bench_indexes
```

脚本结束会调用 `ensure_schema()` 把索引恢复到与 Alembic 迁移一致的状态，
并打印每张表的索引数，**不会留下"少了索引"的脏状态**。

单独看某条查询的计划：

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM message WHERE conversation_id = '<uuid>' ORDER BY created_at DESC LIMIT 20;
```

看三个东西：`Node Type`（是不是 Index Scan）、`actual rows`（扫了多少）、`Execution Time`。