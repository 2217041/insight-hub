| # | 场景 | 没有索引 | 加索引后 | 提升 | 执行计划变化 |
|---|---|---|---|---|---|
| 1 | 会话内最新 20 条 | 21.5 ms | 0.021 ms | 1025.5× | Limit(Gather Merge) → Limit(Index Scan) |
| 2 | 深分页 OFFSET 100000 | 77.7 ms | 18.3 ms | 4.3× | Limit(Gather Merge) → Limit(Index Scan) |
| 3 | Keyset 分页（游标） | 21.3 ms | 0.022 ms | 966.7× | Limit(Gather Merge) → Limit(Index Scan) |
| 4 | 按租户 + 状态查文档 | 0.074 ms | 0.055 ms | 1.3× | Seq Scan → Bitmap Heap Scan |
| 5 | 内容哈希查重（幂等上传） | 0.062 ms | 0.010 ms | 6.2× | Seq Scan → Index Scan |
| 6 | 按文档查块（回填父块） | 5.283 ms | 0.072 ms | 73.4× | Seq Scan → Bitmap Heap Scan |
| 7 | 最近 7 天消息数 | 27.6 ms | 14.0 ms | 2.0× | Aggregate(Gather) → Aggregate(Gather) |
| 8 | 按角色统计（低选择性） | 18.2 ms | 17.4 ms | — | Aggregate(Gather) → Aggregate(Gather) |
| 9 | 不带条件的排序分页 | 18.5 ms | 20.4 ms | — | Limit(Gather Merge) → Limit(Gather Merge) |
| 10 | 关键词模糊搜索 | 36.6 ms | 31.5 ms | 1.2× | Aggregate(Gather) → Aggregate(Gather) |

## 明细

- **1. 会话内最新 20 条**（对话页一打开就拉最近消息，最高频查询）：21.5 ms / Limit(Gather Merge) → 0.021 ms / Limit(Index Scan)
- **2. 深分页 OFFSET 100000**（用户翻到很后面的历史消息）：77.7 ms / Limit(Gather Merge) → 18.3 ms / Limit(Index Scan)
- **3. Keyset 分页（游标）**（用 created_at 游标代替 OFFSET，深翻页不变慢）：21.3 ms / Limit(Gather Merge) → 0.022 ms / Limit(Index Scan)
- **4. 按租户 + 状态查文档**（入库队列要捞 pending/parsing 的文档）：0.074 ms / Seq Scan → 0.055 ms / Bitmap Heap Scan
- **5. 内容哈希查重（幂等上传）**（同一文件重复上传时快速判重）：0.062 ms / Seq Scan → 0.010 ms / Index Scan
- **6. 按文档查块（回填父块）**（检索命中后要捞出同文档的块）：5.283 ms / Seq Scan → 0.072 ms / Bitmap Heap Scan
- **7. 最近 7 天消息数**（运营看板 / 成本统计）：27.6 ms / Aggregate(Gather) → 14.0 ms / Aggregate(Gather)
- **8. 按角色统计（低选择性）**（反例：只有 2 种取值，索引帮不上忙）：18.2 ms / Aggregate(Gather) → 17.4 ms / Aggregate(Gather)
- **9. 不带条件的排序分页**（全站最新消息，看复合索引能否直接用上）：18.5 ms / Limit(Gather Merge) → 20.4 ms / Limit(Gather Merge)
- **10. 关键词模糊搜索**（反例：LIKE '%x%' 用不上 B-tree，需要 GIN/全文索引（W11））：36.6 ms / Aggregate(Gather) → 31.5 ms / Aggregate(Gather)
