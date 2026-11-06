# 技术选型（v1 · W1 定稿）

> 规则：**半年内只允许增加，不允许更换**。反复换栈是这类项目最大的时间杀手。
> 每条都要能回答"为什么不用另一个"——这就是面试答案。

## 1. 选型表

| 层 | 选择 | 理由 | 放弃的备选及代价 |
|---|---|---|---|
| 前端 | Next.js（App Router）+ TS + Tailwind | 服务端组件减少往返；SSR/流式渲染天然适合 AI 对话 | Vue：AI 生态示例更少，且我 React 更熟 |
| 后端 | FastAPI + SQLAlchemy 2.0 | 与 AI 生态同栈；Pydantic 校验即文档；OpenAPI 可生成前端类型 | Spring Boot：多一门语言，Python 侧示例要翻译 |
| 向量存储 | pgvector（PostgreSQL 扩展） | 与业务同库：一个事务内完成写入 + 向量检索，元数据过滤下推 SQL，少运维一个组件 | Milvus / Qdrant：性能更好，但跨库一致性麻烦、运维成本高。**迁移时机：>500 万向量或检索 QPS 成为瓶颈** |
| 缓存 / 队列 | Redis 7 | 缓存、分布式锁、限流、Celery broker 一套搞定 | Kafka：当前消息量不需要，且运维重 |
| 异步任务 | Celery + Redis | 文档解析耗时长，必须移出请求链路，且需要重试与进度 | FastAPI BackgroundTasks：无重试、无状态、重启丢任务 |
| 运行环境 | WSL2 + Ubuntu 24.04 原生服务 | 见下方第 2 节（Docker Desktop 在本机不可行） | 见第 2 节 |
| 部署 | Linux 云服务器 + Docker Compose | W6 实施；服务器上是原生 Linux，没有家庭版限制 | K8s：对单体项目属过度设计 |

## 2. 为什么本地没用 Docker（重要取舍，面试必问）

本机是 **Windows 10 家庭版**，实测三条路都不通：

1. **Docker Desktop 官方不支持**：系统要求 Win10 **Pro/Enterprise/Education** 22H2，家庭版不在列表；且要求 WSL **2.1.5+**，本机是系统自带的 `10.0.19041.3636`。
2. **升级 WSL 失败**：WSL 2.x 安装包只在 GitHub Releases，本机访问返回 **403**。
3. **老版本已下架**：官方只保留最近 6 个月的 Docker Desktop 版本（原文："versions older than 6 months ... are not available for download"）。

**最终方案**：WSL2 内 `apt install postgresql-16 postgresql-16-pgvector redis-server`。

**收益**：
- 清华镜像 13 MB/s，装完不到 2 分钟；
- pgvector 有 Ubuntu 官方包（0.6.0），省掉自己编译；
- 无 Docker Hub 拉取风险（国内经常拉不动）。

**代价**：没有容器隔离；W6 部署时要另学 Docker Compose（在云服务器上，无此限制）。

## 3. 明确不引入（防止分心）

- 不加 GraphQL（REST + OpenAPI 够用）
- 不做微服务拆分（单体 + Worker，等有真实瓶颈再拆）
- 不上 K8s
- 不微调模型（优先 RAG；微调只在 W20 有余力时做一次 LoRA 体验）
- 不用 LangChain 全家桶（RAG 管道自研以便可控；Agent 只用 LangGraph）

## 4. 版本基线（W1 实测）

| 组件 | 版本 |
|---|---|
| Node / npm | 22.23.4 / 10.9.9 |
| Python（后端 venv） | 3.12（uv 管理） |
| uv | 0.12.3 |
| PostgreSQL | 16.15 |
| pgvector | 0.6.0 |
| Redis | 7.0.15 |
| Ubuntu（WSL2） | 24.04.5 LTS |