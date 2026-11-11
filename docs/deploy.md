# 部署指南（W6）

> 目标：在一台干净的 Linux 服务器上，用 `docker compose` 把整套服务跑起来。

---

## 零、服务器要什么配置

### 实测占用（本地 WSL 容器栈，空闲状态）

| 容器 | 内存 | 说明 |
|---|---|---|
| api | 196 MB | FastAPI + 2 worker |
| db | 101 MB | PostgreSQL 16 + pgvector（空库） |
| web | 69 MB | Next.js 生产模式 |
| worker | 57 MB | arq 解析进程 |
| redis | 5 MB | |
| nginx | 7 MB | |
| **合计** | **≈ 435 MB** | 磁盘：镜像 ~5 GB + 构建缓存 ~3 GB |

### 按阶段选配置

| 阶段 | 配置 | 月成本（腾讯云轻量） | 说明 |
|---|---|---|---|
| **当前（调 API）** | **2 核 4 G / 60 GB SSD / 3 Mbps** | ¥60–80（学生机更便宜） | 运行只要 0.5 G，但**构建要 2 G+**：`next build` + `pip install` 峰值会超 2 G，所以 2 G 内存必须加 swap |
| 加 RAG 后 | 4 核 8 G / 100 GB | ¥120–200 | 向量索引 + 并发检索；文档多了磁盘涨得快 |
| 自建推理（可选） | GPU 24 G（4090/A10）+ 16 G 内存 | 按小时 ¥2–5 | 只跑 7B int4；**日常别开着，按小时租** |

> **不要为"以后可能用"买大机器。** 云服务器随时能升配，先用 2C4G 把功能跑通。

### 软件与网络要求

| 项 | 要求 |
|---|---|
| 系统 | **Ubuntu 24.04 LTS**（与开发环境一致，少踩坑） |
| 架构 | x86_64（arm64 也能跑，但镜像要重新验证） |
| 端口 | 22（建议改端口）、80、443；**5432/6379 绝不外开** |
| 备案 | 用 **IP 访问不需要备案**；绑域名才需要 ICP |
| 带宽 | 3 Mbps 够演示；SSE 流式对带宽要求不高，对**延迟**更敏感 |

### 什么时候才需要 GPU

| 场景 | 需要 GPU 吗 |
|---|---|
| 调用外部大模型 API（本项目当前方案） | ❌ 不需要 |
| RAG 检索、Agent 编排 | ❌ 不需要（都是 CPU + 网络） |
| 本地跑 embedding 模型（bge-m3） | ⚠️ CPU 能跑，慢；量大时 1 张 4090 足够 |
| 自建 7B 推理（vLLM，W8 压测） | ✅ 需要 24 G 显存 |
| 自建 70B | ✅ 至少 2×A100 80G |

**结论**：这个项目的产品形态不需要 GPU；GPU 只在 W8 做推理实验时按小时租。

---

本方案需要 Linux。判别方法（从任意一台机器测）：

```
22 端口 → 拒绝（主机在线但没跑 SSH）   ← 说明不是 Linux
3389 → 开放且 RDP 握手成功            ← Windows 远程桌面
```

**推荐做法：在云控制台重装系统为 Ubuntu 24.04 LTS**（约 5–10 分钟，会清空磁盘）。
新机器没有数据，重装零风险。重装后按下面流程走，一条命令拉起。

---

## 零点五、如果是 Windows 服务器

本方案需要 Linux，**强烈建议重装为 Ubuntu**。判别方法（从任意机器测）：

```
22 端口 → 拒绝（主机在线但没跑 SSH）   ← 说明不是 Linux
3389 → 开放且 RDP 握手成功            ← Windows 远程桌面
```

---

## 零点六、上线前必须在控制台做的两件事

这两件事只能在云厂商控制台完成，命令行做不了：

| # | 操作 | 位置（腾讯云） | 验证方式 |
|---|---|---|---|
| 1 | **放行 80 端口**（可选 443） | 实例 → 安全组 → 入站规则 → 添加 TCP:80 | 部署后浏览器能打开 `http://<IP>/` |
| 2 | **确认 22 端口放行** | 同上 | `ssh root@<IP>` 能连上 |

> 安全组不放行时，表现是**超时**（数据包被丢弃），不是"拒绝"。
> "拒绝"说明主机在线、端口没监听——是服务没起，不是防火墙。

另外强烈建议：
- 把密码登录换成**密钥登录**（`ssh-copy-id`），并在控制台禁用密码登录；
- 数据库 5432 / Redis 6379 **绝不要**对公网开放，本方案里它们只在 compose 内网。

---

## 一、架构

```
                 ┌──────────────┐
   公网 :80  ───▶│    nginx     │
                 └──┬────────┬──┘
          /api/*    │        │    /*
                    ▼        ▼
              ┌─────────┐  ┌─────────┐
              │   api   │  │   web   │   (Next.js, 仅内网)
              │ :8000   │  │ :3000   │
              └────┬────┘  └─────────┘
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
   ┌─────────┐          ┌──────────┐
   │   db    │          │  redis   │
   │pgvector │          │          │
   └─────────┘          └────┬─────┘
                             ▲
                       ┌─────┴─────┐
                       │  worker   │  (复用 api 镜像，换 command)
                       └───────────┘
```

**只有 nginx 暴露端口**，db/redis/api/web 都在 compose 内网里。

---

## 二、服务器准备

| 项 | 建议 |
|---|---|
| 规格 | 2 核 4 G（学生机/轻量应用服务器，¥10–30/月） |
| 系统 | Ubuntu 24.04 LTS |
| 安全组 | 放行 22（改端口更安全）、80；**5432 / 6379 绝不开公网** |
| 登录 | 只用 SSH 密钥，禁用密码登录 |

```bash
# 装 Docker + compose 插件
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER    # 重新登录生效
docker compose version
```

> 国内服务器拉镜像慢时，可配镜像加速器（阿里云/腾讯云控制台可拿专属地址），
> 写进 `/etc/docker/daemon.json` 的 `registry-mirrors`。

---

## 三、部署

```bash
git clone <你的仓库地址> insight-hub && cd insight-hub

# 1. 配置环境变量（JWT_SECRET 必须换）
cp .env.example .env
sed -i "s/^JWT_SECRET=$/JWT_SECRET=$(openssl rand -hex 32)/" .env
cat .env

# 2. 起服务（首次会构建镜像，约 5–10 分钟）
docker compose up -d --build

# 3. 看状态
docker compose ps
docker compose logs -f api
```

**迁移是自动的**：`api` 容器的启动命令是 `alembic upgrade head && uvicorn ...`，
保证表结构永远先于服务就绪。Alembic 升级幂等，重复执行安全。

验证：

```bash
curl -s http://127.0.0.1/api/health
# {"status":"ok","db":"ok","redis":"ok","version":"0.5.0"}
```

浏览器打开 `http://<服务器IP>/` 应该看到登录页。

---

## 四、日常运维

| 操作 | 命令 |
|---|---|
| 看日志 | `docker compose logs -f api` / `-f worker` |
| 重启单个服务 | `docker compose restart api` |
| 更新代码 | `git pull && docker compose up -d --build` |
| 停服务 | `docker compose down`（保留数据卷） |
| **清库重来** | `docker compose down -v`（**数据全丢**） |
| 备份数据库 | `docker compose exec db pg_dump -U insight insight > backup.sql` |
| 恢复 | `cat backup.sql \| docker compose exec -T db psql -U insight insight` |
| 进容器 | `docker compose exec api bash` |

---

## 五、上线检查清单

- [ ] `.env` 里的 `JWT_SECRET` 是随机生成的，不是默认值
- [ ] `POSTGRES_PASSWORD` 改过，且 5432 没有映射到宿主机
- [ ] `curl /api/health` 返回 `ok`
- [ ] 注册 → 登录 → 发消息 → 刷新页面，历史还在
- [ ] 上传一个 .md，进度从 pending 走到 ready
- [ ] **SSE 是逐段输出**（如果变成一次性蹦出来，是 Nginx 缓冲没关）
- [ ] 重启容器后数据还在（数据卷挂对了）
- [ ] `docker compose down && up -d` 后服务能自动恢复

---

## 六、踩过的坑（都在这周真实发生过）

| 坑 | 现象 | 解决 |
|---|---|---|
| **迁移没建 pgvector 扩展** | 全新库上 `type "vector" does not exist`，api 容器无限重启 | 迁移开头加 `CREATE EXTENSION IF NOT EXISTS vector` |
| 依赖没进 requirements | 重建环境后 `alembic` 找不到 | 手动装过的包必须回写依赖清单 |
| 前端请求地址写死 | 容器里 `localhost:8000` 指向容器自己 | `NEXT_PUBLIC_API_BASE=""` + Nginx 反代同源 `/api` |
| SSE 被缓冲 | 流式变一次性输出 | `proxy_buffering off` + `X-Accel-Buffering: no` |
| 裸 `depends_on` | api 先于 db 就绪，迁移连接失败 | `condition: service_healthy` |

---

## 七、HTTPS（可选）

有域名的话，用 certbot 申请证书：

```bash
sudo apt install -y certbot
sudo certbot certonly --standalone -d your-domain.com
```

然后把证书挂进 nginx 容器，并在 `docker/nginx.conf` 加 443 的 server 块（80 段加 301 跳转）。

**没有域名也能用**：直接用 `http://<IP>/`，只是没有 HTTPS。
ICP 备案要求只针对域名，IP 访问不需要——所以先用 IP 验证功能是可行的。
---

## 八、本地构建 + 传输镜像（无 Docker Hub 的服务器用这个）

有些云服务器访问不了 Docker Hub（`registry-1.docker.io` 超时），
或者内存太小（1 GB）根本跑不动 `next build`。这时在本地构建、只传镜像：

```powershell
# 1. 本地构建（在仓库根目录的 WSL 里）
docker build -t insight-hub-api:latest ./apps/api
docker build -t insight-hub-web:latest ./apps/web

# 2. 导出成压缩包（api 321MB + web 335MB -> 约 152MB）
docker save insight-hub-api:latest insight-hub-web:latest | gzip -1 > images.tar.gz
docker save pgvector/pgvector:pg16 redis:7-alpine nginx:1.27-alpine | gzip -1 > images2.tar.gz

# 3. 传到服务器（scp 会因 Windows 密钥权限报错，用 SFTP 或先 icacls 修权限）
python infra/tools/sftp_put.py images.tar.gz /tmp/images.tar.gz
```

```bash
# 4. 服务器上加载并启动（不构建）
gunzip -c /tmp/images.tar.gz | docker load
gunzip -c /tmp/images2.tar.gz | docker load
cd /opt/insight-hub && docker compose up -d --no-build
docker compose restart nginx     # 关键：见下面第 3 条
```

### 这条路踩过的三个坑

| # | 现象 | 原因 | 处理 |
|---|---|---|---|
| 1 | `No such image: insight-hub-worker:latest` | worker 只写了 `build:` 没写 `image:`，compose 按 `<项目>-<服务>` 推导镜像名 | 在 compose 里给 api/worker/web **显式写 `image:`** |
| 2 | api 无限重启，日志 `type "vector" does not exist` | 导出的镜像是在"迁移加扩展"那次修复**之前**构建的 | 改完迁移必须**重新构建镜像**，旧镜像里烤的是旧迁移 |
| 3 | `/` 正常但 `/api/*` 502 | nginx 启动时解析了一次 upstream IP；`--force-recreate` 换了容器 IP | `docker compose restart nginx` 让它重新解析 |

> 第 3 条只在"重建容器但不重启 nginx"时出现，很容易误判成后端挂了。

### 镜像大小对比

| 版本 | 大小 | 说明 |
|---|---|---|
| 优化前 web | 1.16 GB | 把 node_modules 整个拷进运行层 |
| **standalone 后** | **335 MB** | 只带运行期需要的依赖 |

同时 `next build` 的内存需求也降低了——这对 1–2 GB 的机器是决定性的。

---

## 九、当前线上环境（2026-11-12）

| 项 | 值 |
|---|---|
| 地址 | http://8.136.244.138/ |
| 实例 | 2 核 / 1736 MB / 40 GB（+2 GB swap） |
| 系统 | Ubuntu 22.04.5 LTS |
| Docker | 29.1.3 + Compose 2.40.3（apt 安装，非官方脚本） |
| 部署方式 | 本地构建 → 传镜像 → `up --no-build` |
| 已验证 | 健康检查、注册登录、文档上传解析、SSE 进度、会话落库、越权 404 |

**重启后自动恢复**：所有服务都是 `restart: unless-stopped`，机器重启会自动拉起。